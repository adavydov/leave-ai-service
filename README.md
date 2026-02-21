# Leave Request Parser (RU) — MVP

Минимальный веб‑сервис на FastAPI:
- загружаешь PDF‑скан заявления на отпуск
- сервис отправляет документ в Anthropic Claude API
- возвращает JSON со структурированными полями + базовые проверки

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# укажи ANTHROPIC_API_KEY (или включи MOCK_MODE=1)

uvicorn app.main:app --reload
```

## Важные переменные окружения

- `ANTHROPIC_API_KEY` — ключ API Anthropic
- `ANTHROPIC_MODEL` — модель по умолчанию (например `claude-sonnet-4-6`)
- `ANTHROPIC_VISION_MODEL` — отдельная модель для OCR/vision шага (опционально)
- `ANTHROPIC_STRUCTURED_MODEL` — отдельная модель для structured шага (опционально)
- `MOCK_MODE=1` — выключает внешние вызовы и возвращает мок-ответ
- `MAX_UPLOAD_MB` — лимит размера PDF (по умолчанию 15)
- `PDF_MAX_PAGES` — число страниц PDF для обработки (по умолчанию 1)
