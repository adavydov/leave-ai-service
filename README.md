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
- `.github/workflows/auto-merge.yml` — авто-approve и merge PR только от доверенных Codex-ботов в этом же репозитории (с fallback на обычный squash merge, если auto-merge недоступен).
- `.github/workflows/deploy-on-main.yml` — запуск деплоя при `push` в `main/master`.

Для деплоя через Render добавьте секрет репозитория:
- `RENDER_DEPLOY_HOOK_URL` — Deploy Hook URL из Render сервиса.

После этого каждый merge в `main` будет автоматически триггерить deploy.

## Hardening v2 contract

API response now includes additive fields:
- `issues`: unified issue list (`severity/domain/category/code/message/hint/...`)
- `decision`: `{status, needs_rewrite, summary}`
- `trace`: `{request_id, upstream_request_ids, timings_ms}`

Backward-compatible fields remain available: `extract`, `validation`, `debug_steps` (shown when `DEBUG_STEPS=1`).

### Key env vars
- `APP_ENV=dev|prod`
- `DEBUG_STEPS=0|1`
- `LOG_LEVEL=INFO`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_VISION_MODEL`, `ANTHROPIC_STRUCTURED_MODEL`
- `ANTHROPIC_HTTP_TIMEOUT_S`, `ANTHROPIC_VISION_TIMEOUT_S`, `ANTHROPIC_STRUCTURED_PARSE_TIMEOUT_S`, `ANTHROPIC_STRUCTURED_FALLBACK_TIMEOUT_S`
- `MAX_UPLOAD_MB`, `PDF_MAX_PAGES`, `MAX_IMAGE_B64_CHARS` (legacy alias: `PDF_MAX_B64_BYTES`), `ANTHROPIC_STRUCTURED_DRAFT_MAX_CHARS`

Use `trace.request_id` when searching logs in Render.


### Конфигурация окружения
Сервис читает настройки из переменных процесса и из `.env` (через `python-dotenv`).
Приоритет: переменные окружения процесса выше значений из `.env`.


## UI (static) quick start
- Open `/` in browser after starting FastAPI.
- UI supports both JSON and NDJSON streaming responses.
- `needs_rewrite=true` means заявление нужно переписать/исправить перед подачей.

### Privacy of UI history
- UI stores last 10 results in localStorage **without PDF**.
- Stored fields are sanitized: `extract` without `raw_text`, issues metadata, request_id/timings/decision.
- PDF bytes are never stored in localStorage/IndexedDB.


### UX concept doc
- Detailed IA/UX spec for the static frontend is available at `static/ux_spec.md`.
- The interface is designed as an issues-first document checker with inspector-based fixing and hidden diagnostics drawer.
