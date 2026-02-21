from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from anthropic import Anthropic
import fitz  # PyMuPDF

from .schemas import LeaveRequestExtract


class UpstreamAIError(RuntimeError):
    def __init__(self, *, step: str, status_code: int, message: str):
        super().__init__(message)
        self.step = step
        self.status_code = status_code


def _safe_anthropic_error_message(err: Exception) -> str:
    text = str(err or "").lower()
    status_code = int(getattr(err, "status_code", 502) or 502)

    if status_code == 429:
        return "AI-сервис временно перегружен (rate limit). Повторите попытку через минуту."
    if status_code in (400, 413, 422):
        return "AI-сервис отклонил запрос к документу. Попробуйте другой PDF или уменьшите его размер."
    if status_code >= 500 or "internal server error" in text or "bad gateway" in text:
        return "AI-сервис временно недоступен. Повторите попытку позже."

    return "Не удалось обработать документ во внешнем AI-сервисе."


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()


def _env_int_min(name: str, default: int, minimum: int) -> int:
    return max(minimum, _env_int(name, default))


def _pix_to_png_bytes(pix) -> bytes:
    # PyMuPDF в разных версиях принимает разные сигнатуры.
    try:
        return pix.tobytes("png")
    except TypeError:
        return pix.tobytes(output="png")


def _render_pdf_to_image_blocks(pdf_bytes: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Рендерим PDF в PNG и возвращаем список content-blocks для Claude Vision.
    Ограничиваемся первыми PDF_MAX_PAGES страницами, чтобы не улететь в лимиты.
    """
    max_pages = _env_int_min("PDF_MAX_PAGES", 1, 1)
    target_long_edge = _env_int_min("PDF_TARGET_LONG_EDGE", 1568, 512)
    max_b64_bytes = _env_int("PDF_MAX_B64_BYTES", 30 * 1024 * 1024)  # запас под 32MB limit :contentReference[oaicite:4]{index=4}
    color_mode = _env_str("PDF_COLOR_MODE", "gray").lower()  # "gray" или "rgb"

    # Открываем PDF из bytes
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = doc.page_count
    pages_to_send = min(max_pages, total_pages)

    colorspace = fitz.csGRAY if color_mode == "gray" else fitz.csRGB

    blocks: List[Dict[str, Any]] = []
    page_stats: List[Dict[str, Any]] = []

    try:
        for i in range(pages_to_send):
            page = doc.load_page(i)
            rect = page.rect
            long_edge_pts = max(rect.width, rect.height) or 1.0

            # Масштаб так, чтобы длинная сторона была ~target_long_edge px
            zoom = float(target_long_edge) / float(long_edge_pts)
            zoom = max(0.5, min(zoom, 4.0))  # разумные границы

            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, colorspace=colorspace, alpha=False)

            # Жёсткий лимит 8000x8000 на vision :contentReference[oaicite:5]{index=5}
            if pix.width > 8000 or pix.height > 8000:
                scale = min(8000 / pix.width, 8000 / pix.height)
                mat = fitz.Matrix(zoom * scale, zoom * scale)
                pix = page.get_pixmap(matrix=mat, colorspace=colorspace, alpha=False)

            png_bytes = _pix_to_png_bytes(pix)
            b64 = base64.b64encode(png_bytes).decode("ascii")

            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                }
            )

            page_stats.append(
                {
                    "page": i,
                    "w_px": pix.width,
                    "h_px": pix.height,
                    "png_bytes": len(png_bytes),
                    "b64_chars": len(b64),
                }
            )

        approx_b64_bytes = sum(p["b64_chars"] for p in page_stats)
        if approx_b64_bytes > max_b64_bytes:
            raise RuntimeError(
                f"Rendered images too large for request: approx_b64_bytes={approx_b64_bytes} > {max_b64_bytes}. "
                f"Reduce PDF_MAX_PAGES or PDF_TARGET_LONG_EDGE."
            )

        info = {
            "total_pages": total_pages,
            "pages_sent": pages_to_send,
            "target_long_edge": target_long_edge,
            "color_mode": color_mode,
            "approx_b64_bytes": approx_b64_bytes,
            "page_stats": page_stats,
        }
        return blocks, info
    finally:
        doc.close()


def _system_prompt_ru() -> str:
    return (
        "Ты — помощник кадровика. Тебе дают изображения страниц заявления на отпуск (скан, возможно рукописный).\n"
        "Нельзя выдумывать: если не видно/не уверен — null.\n"
        "Даты только YYYY-MM-DD. Если год не указан — null и отметь в quality.notes.\n"
    )


def _draft_prompt_ru() -> str:
    # Первый шаг: “увидеть” и выписать факты как текст.
    return (
        "Считай заявление по изображениям.\n"
        "Сделай:\n"
        "1) Блок TRANSCRIPTION: построчная расшифровка видимого текста (как есть).\n"
        "2) Блок CANDIDATE_FIELDS: перечисли возможные поля (employee.full_name, leave.start_date, leave.end_date, "
        "leave.days_count, leave.leave_type, request_date, manager.full_name, подпись) в формате key: value.\n"
        "Если не уверен — пиши null.\n"
        "Важно: НЕ добавляй ничего, чего нет на изображении.\n"
    )


def _parse_prompt_ru(draft_text: str) -> str:
    # Второй шаг: строгая структура.
    return (
        "На основе распознанного текста ниже заполни JSON строго по схеме.\n"
        "Правила:\n"
        "- Если поле не подтверждается текстом — null.\n"
        "- raw_text: дай 2–6 строк (фрагменты), подтверждающих ключевые поля (ФИО, даты, тип).\n\n"
        "РАСПОЗНАННЫЙ ТЕКСТ:\n"
        f"{draft_text}\n"
    )




def _parse_prompt_ru_json_only(draft_text: str) -> str:
    return (
        "На основе распознанного текста ниже верни ТОЛЬКО валидный JSON без markdown и комментариев.\n"
        "Если поле не подтверждается текстом — null.\n"
        "Обязательная структура: schema_version, employer_name, employee, manager, request_date, leave, signature_present, signature_confidence, raw_text, quality.\n\n"
        "РАСПОЗНАННЫЙ ТЕКСТ:\n"
        f"{draft_text}\n"
    )


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой ответ модели")

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        try:
            obj = json.loads(fenced.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    raise ValueError("В ответе модели не найден валидный JSON объект")

def _extract_text_from_msg(msg) -> str:
    # msg.content — список блоков; берём все text блоки.
    out = []
    for blk in getattr(msg, "content", []) or []:
        if getattr(blk, "type", None) == "text":
            out.append(getattr(blk, "text", ""))
        elif isinstance(blk, dict) and blk.get("type") == "text":
            out.append(blk.get("text", ""))
    return "\n".join([t for t in out if t]).strip()




def _parse_structured_with_fallback(
    *,
    client: Anthropic,
    model: str,
    max_tokens: int,
    draft_text: str,
) -> LeaveRequestExtract:
    try:
        return client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=_system_prompt_ru(),
            messages=[{"role": "user", "content": _parse_prompt_ru(draft_text)}],
            output_format=LeaveRequestExtract,
        ).parsed_output
    except anthropic.APIError as e:
        # Фолбэк: parse API иногда отдает 5xx, хотя обычный messages.create работает.
        try:
            raw_msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=_system_prompt_ru(),
                messages=[{"role": "user", "content": _parse_prompt_ru_json_only(draft_text)}],
            )
            raw_text = _extract_text_from_msg(raw_msg)
            raw_json = _extract_first_json_object(raw_text)
            parsed = LeaveRequestExtract.model_validate(raw_json)
            parsed.quality.notes.append("structured_fallback=create+json")
            return parsed
        except Exception as fallback_err:
            source_err = fallback_err if isinstance(fallback_err, anthropic.APIError) else e
            status = int(getattr(source_err, "status_code", 502) or 502)
            raise UpstreamAIError(
                step="structured",
                status_code=status if status >= 400 else 502,
                message=_safe_anthropic_error_message(source_err),
            ) from source_err

def extract_leave_request_from_pdf_bytes(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
    *,
    model: Optional[str] = None,
) -> LeaveRequestExtract:
    if os.getenv("MOCK_MODE", "0").strip() == "1":
        return LeaveRequestExtract.model_validate(
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
                "raw_text": "Прошу предоставить ежегодный оплачиваемый отпуск\nс 01.03.2026 по 14.03.2026\nИванов И.И.",
                "quality": {"overall_confidence": 0.8, "missing_fields": [], "notes": ["MOCK_MODE=1"]},
            }
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY не задан (Render env vars / .env).")

    vision_model = model or os.getenv("ANTHROPIC_VISION_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    structured_model = os.getenv("ANTHROPIC_STRUCTURED_MODEL") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    max_retries = _env_int("ANTHROPIC_MAX_RETRIES", 2)
    draft_max_tokens = _env_int_min("ANTHROPIC_DRAFT_MAX_TOKENS", 1024, 256)
    out_max_tokens = _env_int_min("ANTHROPIC_MAX_TOKENS", 1024, 512)

    client = Anthropic(api_key=api_key, max_retries=max_retries)

    # 1) PDF -> image blocks
    image_blocks, render_info = _render_pdf_to_image_blocks(pdf_bytes)

    # 2) Vision step: images -> text
    try:
        draft_msg = client.messages.create(
            model=vision_model,
            max_tokens=draft_max_tokens,
            temperature=0,
            system=_system_prompt_ru(),
            messages=[
                {
                    "role": "user",
                    "content": image_blocks + [{"type": "text", "text": _draft_prompt_ru()}],  # images before text :contentReference[oaicite:6]{index=6}
                }
            ],
        )
        draft_text = _extract_text_from_msg(draft_msg)
    except anthropic.APIError as e:
        status = int(getattr(e, "status_code", 502) or 502)
        raise UpstreamAIError(
            step="vision",
            status_code=status if status >= 400 else 502,
            message=_safe_anthropic_error_message(e),
        ) from e

    if not draft_text:
        draft_text = "TRANSCRIPTION:\n(null)\nCANDIDATE_FIELDS:\n(null)"

    # 3) Structured step: text -> schema
    parsed = _parse_structured_with_fallback(
        client=client,
        model=structured_model,
        max_tokens=out_max_tokens,
        draft_text=draft_text,
    )

    # Мягко добавим заметку о рендере (полезно для дебага, без секретов)
    try:
        parsed.quality.notes.append(
            f"render: pages_sent={render_info['pages_sent']}/{render_info['total_pages']}, "
            f"target_long_edge={render_info['target_long_edge']}, "
            f"approx_b64_bytes={render_info['approx_b64_bytes']}, "
            f"color_mode={render_info['color_mode']}"
        )
    except Exception:
        pass

    return parsed
