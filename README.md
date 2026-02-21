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


## Логи в проде (важно для диагностики)

Чтобы traceback и пошаговые логи не терялись в проде, запускайте через Gunicorn с конфигом:

```bash
gunicorn app.main:app -c gunicorn_conf.py
```

В `gunicorn_conf.py` включены:
- `accesslog = "-"`
- `errorlog = "-"`
- `capture_output = True`

Это гарантирует, что `logger.exception(...)` и stdout/stderr попадут в логи платформы (Render logs).

- `ANTHROPIC_VISION_TIMEOUT_S` — таймаут vision-запроса в секундах (по умолчанию 90)
- `ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S` — таймаут structured.parse в секундах (по умолчанию 15; быстрый оппортунистический parse, затем fallback)
- `ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S` — таймаут structured fallback create в секундах (по умолчанию 90)

- `ANTHROPIC_MAX_RETRIES` — количество SDK-ретраев. Рекомендуется `0` для прозрачной диагностики structured-ошибок.
- `ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS` — ограничение размера draft_text перед structured-шагом (по умолчанию 12000).

- `ANTHROPIC_HTTP_TIMEOUT_S` — явный HTTP timeout для Anthropic SDK (по умолчанию 60).

## GitHub Actions: авто-merge и деплой

В репозитории добавлены workflow:
- `.github/workflows/auto-merge.yml` — авто-approve и auto-merge PR от Codex-веток (`codex/*`).
- `.github/workflows/deploy-on-main.yml` — запуск деплоя при `push` в `main/master`.

Для деплоя через Render добавьте секрет репозитория:
- `RENDER_DEPLOY_HOOK_URL` — Deploy Hook URL из Render сервиса.

После этого каждый merge в `main` будет автоматически триггерить deploy.

## API: пример ответа `/api/extract`

Ниже пример сериализованного ответа. Поля `compliance_rules_version` и `compliance[].details` являются опциональными для обратной совместимости.

```json
{
  "extract": {
    "schema_version": "1.0",
    "employer_name": "ООО Ромашка",
    "employee": {
      "full_name": "Иванов Иван Иванович",
      "position": "Инженер",
      "department": "ИТ",
      "personnel_number": "1234"
    },
    "manager": {
      "full_name": "Петров Петр Петрович",
      "position": "Директор"
    },
    "request_date": "2026-01-10",
    "leave": {
      "leave_type": "annual_paid",
      "start_date": "2026-02-01",
      "end_date": "2026-02-14",
      "days_count": 14,
      "comment": "Согласно графику отпусков"
    },
    "signature_present": true,
    "signature_confidence": 0.92,
    "raw_text": "...",
    "quality": {
      "overall_confidence": 0.95,
      "missing_fields": [],
      "notes": []
    }
  },
  "validation": [],
  "compliance": [
    {
      "level": "warn",
      "code": "missing_days_count",
      "field": "leave.days_count",
      "message": "Лучше указать количество календарных дней, чтобы не было разночтений.",
      "details": {
        "rule_id": "missing_days_count",
        "law_ref": null,
        "expected": 14,
        "actual": null
      }
    }
  ],
  "needs_rewrite": false,
  "compliance_rules_version": "1.1",
  "debug_steps": [
    "..."
  ]
}
```
