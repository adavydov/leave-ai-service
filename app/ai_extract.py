from __future__ import annotations

import base64
import os
from typing import Optional

import anthropic
from anthropic import Anthropic

from .schemas import LeaveRequestExtract


def _leave_prompt_ru() -> str:
    # Держим инструкцию короткой: меньше слов -> меньше фантазий модели.
    return (
        "Ты извлекаешь данные из скана рукописного заявления на отпуск (Россия).\n"
        "Верни данные строго по схеме.\n"
        "Правила:\n"
        "1) Если поле не видно или не уверен(а) — ставь null (не выдумывай).\n"
        "2) Даты — строго YYYY-MM-DD. Если дата дана как '01.03.26' -> '2026-03-01'.\n"
        "3) leave.leave_type: 'annual_paid' для 'ежегодный оплачиваемый', 'unpaid' для 'без сохранения',\n"
        "   'study' для 'учебный', 'maternity'/'childcare' для соответствующих. Иначе 'other'.\n"
        "4) days_count — календарные дни. Если есть start_date и end_date, можешь вычислить days_count.\n"
        "5) raw_text — 2-6 строк, которые подтверждают ключевые поля (ФИО, даты, тип).\n"
    )


def extract_leave_request_from_pdf_bytes(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
    *,
    model: Optional[str] = None,
) -> LeaveRequestExtract:
    """
    Отправляет PDF (base64) в Claude Messages API и получает структурированный JSON
    по Pydantic-схеме LeaveRequestExtract через messages.parse().
    """

    if os.getenv("MOCK_MODE", "0") == "1":
        return LeaveRequestExtract.model_validate(
            {
                "schema_version": "1.0",
                "employer_name": "ООО Ромашка",
                "employee": {"full_name": "Иванов Иван Иванович", "position": "Инженер", "department": "ИТ"},
                "manager": {"full_name": "Петров Петр Петрович"},
                "request_date": "2026-02-21",
                "leave": {
                    "leave_type": "annual_paid",
                    "start_date": "2026-03-02",
                    "end_date": "2026-03-15",
                    "days_count": 14,
                    "comment": None,
                },
                "signature_present": True,
                "signature_confidence": 0.9,
                "raw_text": "Прошу предоставить мне ежегодный оплачиваемый отпуск\n"
                            "с 02.03.2026 по 15.03.2026\n"
                            "Иванов И.И. 21.02.2026",
                "quality": {"overall_confidence": 0.75, "missing_fields": [], "notes": []},
            }
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY не задан (ни в .env, ни в переменных окружения хоста).")

    model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # max_tokens — это лимит генерируемого ответа (structured JSON обычно короткий).
    # Можно поднять через env, но для MVP 1024 более чем.
    max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))

    client = Anthropic(api_key=api_key)

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system="Ты аккуратный парсер документов. Не выдумывай данные. Если сомневаешься — null.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {"type": "text", "text": _leave_prompt_ru()},
                    ],
                }
            ],
            output_format=LeaveRequestExtract,
        )
    except anthropic.APIError as e:
        # Тут будут и 401/403 (ключ), и 429 (лимиты/кредиты), и 5xx.
        raise RuntimeError(f"Anthropic API error: {e}") from e

    out = getattr(resp, "parsed_output", None)
    if out is None:
        stop_reason = getattr(resp, "stop_reason", None)
        raise RuntimeError(f"Claude не вернул структурированный ответ. stop_reason={stop_reason}")

    return out
