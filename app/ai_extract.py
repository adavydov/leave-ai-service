from __future__ import annotations

import base64
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import anthropic
import fitz  # PyMuPDF
from anthropic import Anthropic
from pydantic import ValidationError

from .schemas import LeaveRequestExtract


class UpstreamAIError(RuntimeError):
    def __init__(self, *, step: str, status_code: int, message: str, debug_steps: Optional[List[str]] = None):
        super().__init__(message)
        self.step = step
        self.status_code = status_code
        self.debug_steps = debug_steps or []


logger = logging.getLogger(__name__)


def _safe_log_debug_message(message: str) -> str:
    msg = re.sub(r"name=[^,]+", "name=<masked>", message)
    msg = re.sub(r'full_name[\'"]?:\s*[^,}]+', "full_name:<masked>", msg, flags=re.IGNORECASE)
    return msg


def _add_debug(debug_steps: List[str], message: str, on_debug: Optional[Callable[[str], None]] = None) -> None:
    debug_steps.append(message)
    logger.info("[extract] %s", _safe_log_debug_message(message))
    if on_debug:
        on_debug(message)


def _safe_anthropic_error_message(err: Exception) -> str:
    text = str(err or "").lower()
    status_code = int(getattr(err, "status_code", 502) or 502)

    if status_code == 429:
        return "AI-сервис временно перегружен (rate limit). Повторите попытку через минуту."
    if status_code in (400, 413, 422):
        return "AI-сервис отклонил запрос к документу. Попробуйте другой PDF или уменьшите его размер."
    if status_code >= 500 or "internal server error" in text or "bad gateway" in text:
        return "AI-сервис временно недоступен. Повторите попытку позже"
    return "Не удалось обработать документ во внешнем AI-сервисе."


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_int_min(name: str, default: int, minimum: int) -> int:
    return max(minimum, _env_int(name, default))


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()


def _env_int_min(name: str, default: int, minimum: int) -> int:
    return max(minimum, _env_int(name, default))


def _pix_to_png_bytes(pix) -> bytes:
    try:
        return pix.tobytes("png")
    except TypeError:
        return pix.tobytes(output="png")


def _extract_text_from_msg(msg) -> str:
    out = []
    for blk in getattr(msg, "content", []) or []:
        if getattr(blk, "type", None) == "text":
            out.append(getattr(blk, "text", ""))
        elif isinstance(blk, dict) and blk.get("type") == "text":
            out.append(blk.get("text", ""))
    return "\n".join([t for t in out if t]).strip()


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой ответ модели")

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1).strip())

    raise ValueError("В ответе модели не найден валидный JSON объект")


def _system_prompt_ru() -> str:
    return (
        "Ты — помощник кадровика. Тебе дают изображения страниц заявления на отпуск (скан, возможно рукописный).\n"
        "Нельзя выдумывать: если не видно/не уверен — null.\n"
        "Даты только YYYY-MM-DD. Если год не указан — null и отметь в quality.notes.\n"
    )


def _draft_prompt_ru() -> str:
    return (
        "Считай заявление по изображениям.\n"
        "Сделай:\n"
        "1) Блок TRANSCRIPTION: построчная расшифровка видимого текста (как есть).\n"
        "2) Блок CANDIDATE_FIELDS: key:value для полей employee.full_name, leave.start_date, leave.end_date, "
        "leave.days_count, leave.leave_type, request_date, manager.full_name, подпись.\n"
        "Если не уверен — null.\n"
    )


def _parse_prompt_ru_json_only(draft_text: str) -> str:
    return (
        "На основе распознанного текста верни ТОЛЬКО валидный JSON-объект без markdown и пояснений.\n"
        "Критично: поле leave.leave_type верни только одним из canonical значений: "
        "annual_paid | unpaid | study | maternity | childcare | other | unknown.\n"
        "Если поле не подтверждается текстом — null.\n"
        "Структура: schema_version, employer_name, employee, manager, request_date, leave, "
        "signature_present, signature_confidence, raw_text, quality.\n\n"
        "РАСПОЗНАННЫЙ ТЕКСТ:\n"
        f"{draft_text}\n"
    )


def _short_error(err: Exception) -> str:
    text = re.sub(r"\s+", " ", str(err or "")).strip()
    return text[:220] if text else type(err).__name__


def _normalize_leave_type(raw: Optional[str]) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return "unknown"

    aliases = {
        "annual_paid": "annual_paid",
        "ежегодный оплачиваемый отпуск": "annual_paid",
        "ежегодный оплачиваемый": "annual_paid",
        "оплачиваемый отпуск": "annual_paid",
        "unpaid": "unpaid",
        "без сохранения": "unpaid",
        "без сохранения заработной платы": "unpaid",
        "study": "study",
        "учебный": "study",
        "maternity": "maternity",
        "беременности и родам": "maternity",
        "childcare": "childcare",
        "по уходу за ребенком": "childcare",
        "по уходу за ребёнком": "childcare",
        "other": "other",
        "unknown": "unknown",
    }

    if value in aliases:
        return aliases[value]

    if "оплач" in value and "отпуск" in value:
        return "annual_paid"
    if "без сохран" in value:
        return "unpaid"
    if "учеб" in value:
        return "study"
    if "беремен" in value or "родам" in value:
        return "maternity"
    if "уход" in value and ("ребен" in value or "ребён" in value):
        return "childcare"
    return "unknown"


def _normalize_fallback_payload(raw_json: Dict[str, Any], debug_steps: List[str], on_debug: Optional[Callable[[str], None]]) -> Dict[str, Any]:
    payload = dict(raw_json)
    leave = payload.get("leave")
    if isinstance(leave, dict):
        original = leave.get("leave_type")
        normalized = _normalize_leave_type(original if isinstance(original, str) else None)
        if original != normalized:
            leave["leave_type"] = normalized
            _add_debug(debug_steps, f"Шаг structured.fallback.normalize: leave_type '{original}' -> '{normalized}'", on_debug)

    signature_confidence = payload.get("signature_confidence")
    if signature_confidence is not None:
        normalized_sc = signature_confidence
        if isinstance(signature_confidence, str):
            sv = signature_confidence.strip().lower()
            if sv in {"high", "высокая", "высокий"}:
                normalized_sc = 0.9
            elif sv in {"medium", "средняя", "средний"}:
                normalized_sc = 0.6
            elif sv in {"low", "низкая", "низкий"}:
                normalized_sc = 0.3
            else:
                try:
                    normalized_sc = float(sv.replace(",", "."))
                except ValueError:
                    normalized_sc = None
        elif isinstance(signature_confidence, (int, float)):
            normalized_sc = float(signature_confidence)
        else:
            normalized_sc = None

        if normalized_sc is None:
            _add_debug(
                debug_steps,
                f"Шаг structured.fallback.normalize: signature_confidence '{signature_confidence}' -> null",
                on_debug,
            )
            payload["signature_confidence"] = None
        else:
            clipped_sc = max(0.0, min(1.0, float(normalized_sc)))
            if clipped_sc != signature_confidence:
                _add_debug(
                    debug_steps,
                    f"Шаг structured.fallback.normalize: signature_confidence '{signature_confidence}' -> {clipped_sc}",
                    on_debug,
                )
            payload["signature_confidence"] = clipped_sc
    return payload


def _trim_draft_text(draft_text: str, max_chars: int, debug_steps: List[str], on_debug: Optional[Callable[[str], None]]) -> str:
    cleaned = (draft_text or "").replace("\x00", "").strip()
    if len(cleaned) <= max_chars:
        return cleaned

    head = max_chars * 2 // 3
    tail = max_chars - head
    trimmed = cleaned[:head] + "\n... [TRIMMED] ...\n" + cleaned[-tail:]
    _add_debug(
        debug_steps,
        f"Шаг structured.parse: draft_text обрезан (orig={len(cleaned)}, limit={max_chars}, head={head}, tail={tail})",
        on_debug,
    )
    return trimmed


def _run_with_timeout(fn: Callable[[], Any], timeout_s: int, label: str):
    timeout_s = max(1, int(timeout_s))
    result_q: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_q.put((True, fn()))
        except Exception as err:  # noqa: BLE001
            result_q.put((False, err))

    t = threading.Thread(target=_runner, daemon=True, name=f"timeout-{label}")
    t.start()

    try:
        ok, payload = result_q.get(timeout=timeout_s)
    except queue.Empty as e:
        raise TimeoutError(f"{label} timed out after {timeout_s}s") from e

    if ok:
        return payload
    raise payload


def _create_anthropic_client(api_key: str, max_retries: int, http_timeout_s: int) -> Anthropic:
    try:
        return Anthropic(api_key=api_key, max_retries=max_retries, timeout=max(5, int(http_timeout_s)))
    except TypeError:
        return Anthropic(api_key=api_key, max_retries=max_retries)


def _client_with_timeout(client: Anthropic, timeout_s: int):
    timeout_s = max(5, int(timeout_s))
    with_options = getattr(client, "with_options", None)
    if callable(with_options):
        try:
            return with_options(timeout=timeout_s)
        except TypeError:
            return client
    return client


def _request_id_of(obj: Any) -> Optional[str]:
    rid = getattr(obj, "_request_id", None) or getattr(obj, "request_id", None)
    if rid:
        return str(rid)
    return None


def _raise_timeout(step: str, err: TimeoutError, debug_steps: List[str]):
    raise UpstreamAIError(
        step=step,
        status_code=504,
        message="AI-сервис не ответил вовремя. Повторите попытку позже или уменьшите размер PDF.",
        debug_steps=debug_steps,
    ) from err


def _render_pdf_to_image_blocks(
    pdf_bytes: bytes,
    debug_steps: List[str],
    *,
    on_debug: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    max_pages = _env_int_min("PDF_MAX_PAGES", 1, 1)
    target_long_edge = _env_int_min("PDF_TARGET_LONG_EDGE", 1568, 512)
    max_b64_chars = _env_int("MAX_IMAGE_B64_CHARS", 4_000_000)
    color_mode = _env_str("PDF_COLOR_MODE", "gray").lower()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    pages_to_send = min(max_pages, total_pages)
    colorspace = fitz.csGRAY if color_mode == "gray" else fitz.csRGB

    blocks: List[Dict[str, Any]] = []
    page_stats: List[Dict[str, Any]] = []

    _add_debug(debug_steps, f"PDF открыт: pages_total={total_pages}, pages_to_send={pages_to_send}, color_mode={color_mode}", on_debug)

    try:
        for i in range(pages_to_send):
            page = doc.load_page(i)
            rect = page.rect
            long_edge_pts = max(rect.width, rect.height) or 1.0
            zoom = max(0.5, min(float(target_long_edge) / float(long_edge_pts), 4.0))

            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, colorspace=colorspace, alpha=False)

            if pix.width > 8000 or pix.height > 8000:
                scale = min(8000 / pix.width, 8000 / pix.height)
                mat = fitz.Matrix(zoom * scale, zoom * scale)
                pix = page.get_pixmap(matrix=mat, colorspace=colorspace, alpha=False)

            png_bytes = _pix_to_png_bytes(pix)
            b64 = base64.b64encode(png_bytes).decode("ascii")

            blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
            page_stats.append({"page": i, "w_px": pix.width, "h_px": pix.height, "png_bytes": len(png_bytes), "b64_chars": len(b64)})

        approx_b64_chars = sum(p["b64_chars"] for p in page_stats)
        if approx_b64_chars > max_b64_chars:
            raise RuntimeError(f"Rendered images too large for request: approx_b64_chars={approx_b64_chars} > {max_b64_chars}.")

        info = {
            "total_pages": total_pages,
            "pages_sent": pages_to_send,
            "target_long_edge": target_long_edge,
            "color_mode": color_mode,
            "approx_b64_chars": approx_b64_chars,
            "page_stats": page_stats,
        }
        _add_debug(
            debug_steps,
            f"PDF->PNG ок: pages_sent={pages_to_send}, approx_b64_chars={approx_b64_chars}, page0={page_stats[0] if page_stats else None}",
            on_debug,
        )
        return blocks, info
    finally:
        doc.close()


def _raise_upstream(step: str, err: Exception, debug_steps: List[str]):
    status = int(getattr(err, "status_code", 502) or 502)
    raise UpstreamAIError(
        step=step,
        status_code=status if status >= 400 else 502,
        message=_safe_anthropic_error_message(err),
        debug_steps=debug_steps,
    ) from err


def extract_leave_request_with_debug(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
    *,
    model: Optional[str] = None,
    on_debug: Optional[Callable[[str], None]] = None,
) -> Tuple[LeaveRequestExtract, List[str]]:
    debug_steps: List[str] = []
    _add_debug(debug_steps, f"Файл загружен: name={filename}, bytes={len(pdf_bytes)}", on_debug)

    if os.getenv("MOCK_MODE", "0").strip() == "1":
        _add_debug(debug_steps, "MOCK_MODE=1, внешний AI не вызывается", on_debug)
        parsed = LeaveRequestExtract.model_validate(
            {
                "schema_version": "1.0",
                "employer_name": None,
                "employee": {"full_name": "Иванов Иван Иванович", "position": "Инженер", "department": "ИТ"},
                "manager": {"full_name": None, "position": None},
                "request_date": "2026-02-21",
                "leave": {
                    "leave_type": "annual_paid",
                    "start_date": "2026-03-01",
                    "end_date": "2026-03-14",
                    "days_count": 14,
                    "comment": None,
                },
                "signature_present": True,
                "signature_confidence": 0.8,
                "raw_text": "Прошу предоставить ежегодный оплачиваемый отпуск",
                "quality": {"overall_confidence": 0.8, "missing_fields": [], "notes": ["MOCK_MODE=1"]},
            }
        )
        return parsed, debug_steps

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        _add_debug(debug_steps, "Ошибка: ANTHROPIC_API_KEY отсутствует", on_debug)
        raise UpstreamAIError(
            step="config",
            status_code=500,
            message="ANTHROPIC_API_KEY не задан (Render env vars / .env).",
            debug_steps=debug_steps,
        )

    vision_model = model or os.getenv("ANTHROPIC_VISION_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    structured_model = os.getenv("ANTHROPIC_STRUCTURED_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_retries = _env_int("ANTHROPIC_MAX_RETRIES", 0)
    anthropic_http_timeout_s = _env_int_min("ANTHROPIC_HTTP_TIMEOUT_S", 60, 10)
    draft_max_tokens = _env_int_min("ANTHROPIC_DRAFT_MAX_TOKENS", 1024, 256)
    out_max_tokens = _env_int_min("ANTHROPIC_MAX_TOKENS", 1024, 512)
    vision_timeout_s = _env_int_min("ANTHROPIC_VISION_TIMEOUT_S", 90, 15)
    structured_parse_timeout_s = _env_int_min("ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S", 15, 10)
    structured_fallback_timeout_s = _env_int_min("ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S", 90, 15)
    structured_draft_max_chars = _env_int_min("ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS", 12000, 2000)

    min_required_sdk_timeout = max(vision_timeout_s, structured_parse_timeout_s, structured_fallback_timeout_s) + 5
    effective_http_timeout_s = max(anthropic_http_timeout_s, min_required_sdk_timeout)
    if effective_http_timeout_s != anthropic_http_timeout_s:
        _add_debug(
            debug_steps,
            f"Конфиг AI: sdk_http_timeout_s повышен с {anthropic_http_timeout_s} до {effective_http_timeout_s} "
            f"(>= max step timeout + 5s)",
            on_debug,
        )

    client = _create_anthropic_client(api_key=api_key, max_retries=max_retries, http_timeout_s=effective_http_timeout_s)

    _add_debug(
        debug_steps,
        f"Конфиг AI: vision_model={vision_model}, structured_model={structured_model}, retries={max_retries}, "
        f"sdk_http_timeout_s={effective_http_timeout_s}, vision_timeout_s={vision_timeout_s}, "
        f"structured_parse_timeout_s={structured_parse_timeout_s}, structured_fallback_timeout_s={structured_fallback_timeout_s}, "
        f"structured_draft_max_chars={structured_draft_max_chars}",
        on_debug,
    )

    try:
        image_blocks, render_info = _render_pdf_to_image_blocks(pdf_bytes, debug_steps, on_debug=on_debug)
    except Exception as e:
        _add_debug(debug_steps, f"Шаг PDF->PNG: ошибка: {type(e).__name__}", on_debug)
        raise UpstreamAIError(
            step="render",
            status_code=422,
            message="Не удалось обработать PDF перед отправкой в AI.",
            debug_steps=debug_steps,
        ) from e

    try:
        _add_debug(debug_steps, "Шаг vision: отправка PNG в Anthropic", on_debug)

        def _vision_call():
            scoped = _client_with_timeout(client, vision_timeout_s + 5)
            return scoped.messages.create(
                model=vision_model,
                max_tokens=draft_max_tokens,
                temperature=0,
                system=_system_prompt_ru(),
                messages=[{"role": "user", "content": image_blocks + [{"type": "text", "text": _draft_prompt_ru()}]}],
            )

        draft_msg = _run_with_timeout(_vision_call, vision_timeout_s, "vision")
        draft_text = _extract_text_from_msg(draft_msg)
        _add_debug(debug_steps, f"Шаг vision: ответ получен, chars={len(draft_text)}", on_debug)
        rid = _request_id_of(draft_msg)
        if rid:
            _add_debug(debug_steps, f"Шаг vision: request_id={rid}", on_debug)
    except TimeoutError as e:
        _add_debug(debug_steps, "Шаг vision: timeout", on_debug)
        _raise_timeout("vision", e, debug_steps)
    except anthropic.APIError as e:
        _add_debug(debug_steps, f"Шаг vision: ошибка API: {type(e).__name__}", on_debug)
        rid = _request_id_of(e)
        if rid:
            _add_debug(debug_steps, f"Шаг vision: error_request_id={rid}", on_debug)
        _raise_upstream("vision", e, debug_steps)

    if not draft_text:
        draft_text = "TRANSCRIPTION:\n(null)\nCANDIDATE_FIELDS:\n(null)"
        _add_debug(debug_steps, "Шаг vision: пустой ответ, подставлен дефолтный draft", on_debug)

    draft_text = _trim_draft_text(draft_text, structured_draft_max_chars, debug_steps, on_debug)
    if "base64" in draft_text.lower() and len(draft_text) > 4000:
        _add_debug(debug_steps, "Шаг structured.parse: предупреждение — в draft_text есть маркеры base64", on_debug)
    _add_debug(debug_steps, f"Шаг structured.parse: draft_chars={len(draft_text)}", on_debug)

    try:
        _add_debug(debug_steps, "Шаг structured.parse: отправка draft на структуризацию", on_debug)

        def _structured_parse_call():
            scoped = _client_with_timeout(client, structured_parse_timeout_s + 5)
            return scoped.messages.parse(
                model=structured_model,
                max_tokens=out_max_tokens,
                temperature=0,
                system=_system_prompt_ru(),
                messages=[{"role": "user", "content": _parse_prompt_ru_json_only(draft_text)}],
                output_format=LeaveRequestExtract,
            ).parsed_output

        parsed = _run_with_timeout(_structured_parse_call, structured_parse_timeout_s, "structured.parse")
        _add_debug(debug_steps, "Шаг structured.parse: успешно", on_debug)
    except Exception as e:
        _add_debug(debug_steps, f"Шаг structured.parse: ошибка {type(e).__name__}: {_short_error(e)}; пробуем fallback через messages.create", on_debug)
        rid = _request_id_of(e)
        if rid:
            _add_debug(debug_steps, f"Шаг structured.parse: error_request_id={rid}", on_debug)
        try:
            def _structured_fallback_call():
                scoped = _client_with_timeout(client, structured_fallback_timeout_s + 5)
                return scoped.messages.create(
                    model=structured_model,
                    max_tokens=out_max_tokens,
                    temperature=0,
                    system=_system_prompt_ru(),
                    messages=[{"role": "user", "content": _parse_prompt_ru_json_only(draft_text)}],
                )

            raw_msg = _run_with_timeout(_structured_fallback_call, structured_fallback_timeout_s, "structured.fallback.create")
            raw_text = _extract_text_from_msg(raw_msg)
            _add_debug(debug_steps, f"Шаг structured.fallback.create: ответ chars={len(raw_text)}", on_debug)
            rid = _request_id_of(raw_msg)
            if rid:
                _add_debug(debug_steps, f"Шаг structured.fallback.create: request_id={rid}", on_debug)
            raw_json = _extract_first_json_object(raw_text)
            normalized_json = _normalize_fallback_payload(raw_json, debug_steps, on_debug)
            parsed = LeaveRequestExtract.model_validate(normalized_json)
            parsed.quality.notes.append("structured_fallback=create+json")
            _add_debug(debug_steps, "Шаг structured.fallback.validate: JSON валиден", on_debug)
        except Exception as fallback_err:
            _add_debug(debug_steps, f"Шаг structured.fallback: ошибка {type(fallback_err).__name__}: {_short_error(fallback_err)}", on_debug)
            rid = _request_id_of(fallback_err)
            if rid:
                _add_debug(debug_steps, f"Шаг structured.fallback: error_request_id={rid}", on_debug)
            if isinstance(fallback_err, ValidationError):
                raise UpstreamAIError(
                    step="structured",
                    status_code=422,
                    message="Ответ AI получен, но не соответствует схеме данных. Проверьте тип отпуска/даты в документе.",
                    debug_steps=debug_steps,
                ) from fallback_err
            source_err = fallback_err if isinstance(fallback_err, (anthropic.APIError, TimeoutError)) else e
            if isinstance(source_err, TimeoutError):
                _raise_timeout("structured", source_err, debug_steps)
            if isinstance(source_err, anthropic.APIError):
                _raise_upstream("structured", source_err, debug_steps)
            raise UpstreamAIError(
                step="structured",
                status_code=500,
                message="Ошибка структуризации ответа AI-сервиса.",
                debug_steps=debug_steps,
            ) from source_err

    try:
        parsed.quality.notes.append(
            f"render: pages_sent={render_info['pages_sent']}/{render_info['total_pages']}, "
            f"target_long_edge={render_info['target_long_edge']}, approx_b64_chars={render_info['approx_b64_chars']}, "
            f"color_mode={render_info['color_mode']}"
        )
    except Exception:
        pass

    _add_debug(debug_steps, "Готово: extraction успешно завершён", on_debug)
    return parsed, debug_steps


def extract_leave_request_from_pdf_bytes(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
    *,
    model: Optional[str] = None,
) -> LeaveRequestExtract:
    parsed, _ = extract_leave_request_with_debug(pdf_bytes, filename, model=model)
    return parsed


def _trace_from_debug(debug_steps: List[str], total_ms: int) -> dict[str, Any]:
    upstream_request_ids: dict[str, str] = {}
    for line in debug_steps:
        m = re.search(r"Шаг ([^:]+): request_id=([A-Za-z0-9_\-]+)", line)
        if m:
            upstream_request_ids[m.group(1)] = m.group(2)
    timings_ms = {"total_ms": int(total_ms)}
    return {"upstream_request_ids": upstream_request_ids, "timings_ms": timings_ms}


def extract_leave_request_with_meta(
    pdf_bytes: bytes,
    filename: str,
    model: Optional[str] = None,
    on_debug: Optional[Callable[[str], None]] = None,
) -> tuple[LeaveRequestExtract, List[str], dict[str, Any]]:
    started = time.perf_counter()
    parsed, debug_steps = extract_leave_request_with_debug(pdf_bytes, filename, model=model, on_debug=on_debug)
    total_ms = int((time.perf_counter() - started) * 1000)
    return parsed, debug_steps, _trace_from_debug(debug_steps, total_ms)
