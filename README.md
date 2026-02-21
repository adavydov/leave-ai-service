# Leave Request Parser (RU) — MVP

Минимальный веб‑сервис на FastAPI:
- загружаешь PDF‑скан заявления на отпуск
- сервис дергает Anthropic Claude API (PDF input + structured output)
- возвращает JSON со структурированными полями + простые проверки

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# впиши ANTHROPIC_API_KEY (или включи MOCK_MODE=1)

uvicorn app.main:app --reload
чув3
mock
eof
