from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import anthropic
import fitz  # PyMuPDF
from anthropic import Anthropic

from .schemas import LeaveRequestExtract


class UpstreamAIError(RuntimeError):
    def __init__(self, *, step: str, status_code: int, message: str, debug_steps: Optional[List[str]] = None):
        super().__init__(message)
        self.step = step
        self.status_code = status_code
        self.debug_steps = debug_steps or []


logger = logging.getLogger(__name__)


def _add_debug(debug_steps: List[str], message: str, on_debug: Optional[Callable[[str], None]] = None) -> None:
    debug_steps.append(message)
    logger.info("[extract] %s", message)
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
        "Если поле не подтверждается текстом — null.\n"
        "Структура: schema_version, employer_name, employee, manager, request_date, leave, "
        "signature_present, signature_confidence, raw_text, quality.\n\n"
        "РАСПОЗНАННЫЙ ТЕКСТ:\n"
        f"{draft_text}\n"
    )


def _render_pdf_to_image_blocks(
    pdf_bytes: bytes,
    debug_steps: List[str],
    *,
    on_debug: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    max_pages = _env_int_min("PDF_MAX_PAGES", 1, 1)
    target_long_edge = _env_int_min("PDF_TARGET_LONG_EDGE", 1568, 512)
    max_b64_bytes = _env_int("PDF_MAX_B64_BYTES", 30 * 1024 * 1024)
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

            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": b64},
                }
            )
            page_stats.append({"page": i, "w_px": pix.width, "h_px": pix.height, "png_bytes": len(png_bytes), "b64_chars": len(b64)})

        approx_b64_bytes = sum(p["b64_chars"] for p in page_stats)
        if approx_b64_bytes > max_b64_bytes:
            raise RuntimeError(f"Rendered images too large for request: approx_b64_bytes={approx_b64_bytes} > {max_b64_bytes}.")

        info = {
            "total_pages": total_pages,
            "pages_sent": pages_to_send,
            "target_long_edge": target_long_edge,
            "color_mode": color_mode,
            "approx_b64_bytes": approx_b64_bytes,
            "page_stats": page_stats,
        }
        _add_debug(
            debug_steps,
            f"PDF->PNG ок: pages_sent={pages_to_send}, approx_b64_bytes={approx_b64_bytes}, page0={page_stats[0] if page_stats else None}",
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
    max_retries = _env_int("ANTHROPIC_MAX_RETRIES", 2)
    draft_max_tokens = _env_int_min("ANTHROPIC_DRAFT_MAX_TOKENS", 1024, 256)
    out_max_tokens = _env_int_min("ANTHROPIC_MAX_TOKENS", 1024, 512)

    client = Anthropic(api_key=api_key, max_retries=max_retries)

    _add_debug(debug_steps, f"Конфиг AI: vision_model={vision_model}, structured_model={structured_model}, retries={max_retries}", on_debug)

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
        draft_msg = client.messages.create(
            model=vision_model,
            max_tokens=draft_max_tokens,
            temperature=0,
            system=_system_prompt_ru(),
            messages=[{"role": "user", "content": image_blocks + [{"type": "text", "text": _draft_prompt_ru()}]}],
        )
        draft_text = _extract_text_from_msg(draft_msg)
        _add_debug(debug_steps, f"Шаг vision: ответ получен, chars={len(draft_text)}", on_debug)
    except anthropic.APIError as e:
        _add_debug(debug_steps, f"Шаг vision: ошибка API: {type(e).__name__}", on_debug)
        _raise_upstream("vision", e, debug_steps)

    if not draft_text:
        draft_text = "TRANSCRIPTION:\n(null)\nCANDIDATE_FIELDS:\n(null)"
        _add_debug(debug_steps, "Шаг vision: пустой ответ, подставлен дефолтный draft", on_debug)

    try:
        _add_debug(debug_steps, "Шаг structured.parse: отправка draft на структуризацию", on_debug)
        parsed = client.messages.parse(
            model=structured_model,
            max_tokens=out_max_tokens,
            temperature=0,
            system=_system_prompt_ru(),
            messages=[{"role": "user", "content": _parse_prompt_ru_json_only(draft_text)}],
            output_format=LeaveRequestExtract,
        ).parsed_output
        _add_debug(debug_steps, "Шаг structured.parse: успешно", on_debug)
    except anthropic.APIError as e:
        _add_debug(debug_steps, "Шаг structured.parse: ошибка, пробуем fallback через messages.create", on_debug)
        try:
            raw_msg = client.messages.create(
                model=structured_model,
                max_tokens=out_max_tokens,
                temperature=0,
                system=_system_prompt_ru(),
                messages=[{"role": "user", "content": _parse_prompt_ru_json_only(draft_text)}],
            )
            raw_text = _extract_text_from_msg(raw_msg)
            _add_debug(debug_steps, f"Шаг structured.fallback.create: ответ chars={len(raw_text)}", on_debug)
            raw_json = _extract_first_json_object(raw_text)
            parsed = LeaveRequestExtract.model_validate(raw_json)
            parsed.quality.notes.append("structured_fallback=create+json")
            _add_debug(debug_steps, "Шаг structured.fallback.validate: JSON валиден", on_debug)
        except Exception as fallback_err:
            _add_debug(debug_steps, f"Шаг structured.fallback: ошибка: {type(fallback_err).__name__}", on_debug)
            source_err = fallback_err if isinstance(fallback_err, anthropic.APIError) else e
            _raise_upstream("structured", source_err, debug_steps)
    except Exception as e:
        _add_debug(debug_steps, f"Шаг structured.parse: не-API ошибка: {type(e).__name__}", on_debug)
        raise UpstreamAIError(
            step="structured",
            status_code=500,
            message="Ошибка структуризации ответа AI-сервиса.",
            debug_steps=debug_steps,
        ) from e

    try:
        parsed.quality.notes.append(
            f"render: pages_sent={render_info['pages_sent']}/{render_info['total_pages']}, "
            f"target_long_edge={render_info['target_long_edge']}, approx_b64_bytes={render_info['approx_b64_bytes']}, "
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
