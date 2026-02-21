from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from typing import Any

import anthropic
from anthropic import Anthropic
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .ai_extract import UpstreamAIError, extract_leave_request_with_meta
from .compliance import run_compliance_checks
from .issues import build_decision, build_trace, from_compliance, from_validation, make_upstream_issue
from .schemas import ApiResponse
from .settings import get_settings
from .validation import validate_extract

settings = get_settings()
logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Leave Request Parser (RU)")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    resp = FileResponse("static/index.html")
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


def _anthropic_probe() -> dict:
    model = settings.ANTHROPIC_MODEL
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    msg = client.messages.create(model=model, max_tokens=16, temperature=0, messages=[{"role": "user", "content": "Ответь одним словом: ok"}])
    text = ""
    for block in (msg.content or []):
        if getattr(block, "type", None) == "text":
            text += getattr(block, "text", "")
    return {"status": "ok", "model": model, "reply": text.strip()[:80]}


@app.get("/api/health/anthropic")
async def api_health_anthropic():
    if settings.APP_ENV == "dev" and not settings.ANTHROPIC_API_KEY:
        return {"status": "ok", "mode": "dev-no-key"}
    try:
        return await run_in_threadpool(_anthropic_probe)
    except anthropic.APIError as e:
        logger.exception("Anthropic health probe APIError")
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e}")
    except Exception:
        raise HTTPException(status_code=500, detail='Ошибка health-check Anthropic.')


async def _read_pdf_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Пожалуйста, загрузите PDF файл.")
    data = await file.read()
    if len(data) > settings.MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой. Лимит: {settings.MAX_UPLOAD_MB} MB.")
    return filename, data


def _sanitize_error_message(err: Exception) -> str:
    message = re.sub(r"<[^>]+>", " ", str(err or "")).strip()
    message = re.sub(r"\s+", " ", message).strip(" .,:;-")
    return message[:320] if message else f"Ошибка обработки: {type(err).__name__}"


def _upstream_error_to_issue_and_status(err: Exception, where: str):
    status_code = int(getattr(err, 'status_code', 0) or 0)
    if isinstance(err, TimeoutError) or 'timeout' in str(err).lower():
        return 504, make_upstream_issue(code='anthropic_timeout', category='timeouts', source=where, message='Внешний AI не успел ответить в отведённый таймаут.', hint='Повторите попытку позже или уменьшите размер PDF.')
    if status_code == 429:
        return 503, make_upstream_issue(code='anthropic_rate_limited', category='network', source=where, message='Внешний AI временно перегружен.', hint='Повторите попытку через 1-2 минуты.')
    if status_code in (401, 403):
        return 502, make_upstream_issue(code='anthropic_auth', category='network', source=where, message='Ошибка авторизации во внешнем AI.', hint='Проверьте ANTHROPIC_API_KEY в Render.')
    if status_code >= 500:
        return 502, make_upstream_issue(code='anthropic_upstream_error', category='network', source=where, message='Внешний AI временно недоступен.', hint='Повторите попытку позже.')
    return 502, make_upstream_issue(code='upstream_unknown', category='unknown', source=where, message='Ошибка внешнего AI сервиса.', hint='Повторите попытку позже.')




def _http_exception_to_issue_and_status(err: HTTPException, where: str):
    status = int(err.status_code)
    detail = str(err.detail or '')
    if status == 413:
        issue = make_upstream_issue(
            code='pdf_too_large',
            category='validation',
            source=where,
            severity='error',
            message='Файл слишком большой для обработки.',
            hint='Сожмите PDF или загрузите 1 страницу.',
        )
        issue.domain = 'system'
        return status, issue
    if status == 400 and 'pdf' in detail.lower():
        issue = make_upstream_issue(
            code='pdf_invalid_type',
            category='validation',
            source=where,
            severity='error',
            message='Загружен файл неподдерживаемого формата.',
            hint='Загрузите PDF файл.',
        )
        issue.domain = 'system'
        return status, issue
    issue = make_upstream_issue(
        code='request_validation_error',
        category='validation',
        source=where,
        severity='error',
        message='Ошибка валидации входного запроса.',
        hint='Проверьте файл и повторите попытку.',
    )
    issue.domain = 'system'
    return status, issue

def _build_error_payload(err: Exception, where: str, request_id: str) -> tuple[int, dict[str, Any]]:
    debug_steps = getattr(err, 'debug_steps', []) if settings.DEBUG_STEPS else []
    if isinstance(err, HTTPException):
        status, issue = _http_exception_to_issue_and_status(err, where)
        issues = [issue]
    elif isinstance(err, UpstreamAIError):
        status, upstream_issue = _upstream_error_to_issue_and_status(err, where)
        issues = [upstream_issue]
    elif isinstance(err, anthropic.APIError):
        status, upstream_issue = _upstream_error_to_issue_and_status(err, where)
        issues = [upstream_issue]
    else:
        status = 500
        issues = [make_upstream_issue(code='internal_error', category='unknown', source=where, message='Внутренняя ошибка сервиса.', hint='Повторите попытку. Если ошибка повторяется — передайте request_id в поддержку.')]

    decision = build_decision(issues)
    trace = build_trace(request_id=request_id, timings_ms={}, upstream_request_ids={}).model_dump()
    return status, {
        'error': 'Ошибка при обработке PDF.',
        'status': status,
        'detail': _sanitize_error_message(err),
        'issues': [i.model_dump() for i in issues],
        'decision': decision.model_dump(),
        'trace': trace,
        'debug_steps': debug_steps,
    }


@app.post('/api/extract')
async def api_extract(request: Request, file: UploadFile = File(...)):
    started = time.perf_counter()
    try:
        filename, data = await _read_pdf_upload(file)
        extract, debug_steps, meta = await run_in_threadpool(extract_leave_request_with_meta, data, filename)
        validation = validate_extract(extract)
        compliance, needs_rewrite = run_compliance_checks(extract)
        issues = [*from_validation(validation), *from_compliance(compliance)]
        decision = build_decision(issues)
        decision.needs_rewrite = needs_rewrite or decision.needs_rewrite
        meta_timings = dict(meta.get('timings_ms') or {})
        meta_timings.setdefault('total_ms', int((time.perf_counter() - started) * 1000))
        trace = build_trace(request_id=request.state.request_id, timings_ms=meta_timings, upstream_request_ids=meta.get('upstream_request_ids') or {})

        resp = ApiResponse(
            extract=extract,
            validation=validation,
            compliance=compliance,
            needs_rewrite=needs_rewrite,
            issues=issues,
            decision=decision,
            trace=trace,
        ).model_dump()
        if settings.DEBUG_STEPS:
            resp['debug_steps'] = debug_steps
        return resp
    except Exception as e:
        status, payload = _build_error_payload(e, 'api_extract', request.state.request_id)
        return JSONResponse(status_code=status, content=payload)


@app.post('/api/extract/stream')
async def api_extract_stream(request: Request, file: UploadFile = File(...)):
    try:
        filename, data = await _read_pdf_upload(file)
    except Exception as e:
        status, payload = _build_error_payload(e, 'api_extract_stream', request.state.request_id)
        return JSONResponse(status_code=status, content=payload)

    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def _on_debug(step: str) -> None:
        if settings.DEBUG_STEPS:
            events.put({'type': 'step', 'message': step})

    def _worker() -> None:
        try:
            extract, debug_steps, meta = extract_leave_request_with_meta(data, filename, on_debug=_on_debug)
            validation = validate_extract(extract)
            compliance, needs_rewrite = run_compliance_checks(extract)
            issues = [*from_validation(validation), *from_compliance(compliance)]
            decision = build_decision(issues)
            decision.needs_rewrite = needs_rewrite or decision.needs_rewrite
            trace = build_trace(request_id=request.state.request_id, timings_ms=meta.get('timings_ms') or {}, upstream_request_ids=meta.get('upstream_request_ids') or {})

            resp = ApiResponse(
                extract=extract,
                validation=validation,
                compliance=compliance,
                needs_rewrite=needs_rewrite,
                issues=issues,
                decision=decision,
                trace=trace,
            ).model_dump()
            if settings.DEBUG_STEPS:
                resp['debug_steps'] = debug_steps
            events.put({'type': 'result', 'ok': True, 'status': 200, 'payload': resp})
        except Exception as e:
            status, payload = _build_error_payload(e, 'api_extract_stream', request.state.request_id)
            events.put({'type': 'result', 'ok': False, 'status': status, 'payload': payload})

    threading.Thread(target=_worker, daemon=True).start()

    async def _stream_gen():
        while True:
            event = await run_in_threadpool(events.get)
            yield (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
            if event.get('type') == 'result':
                break

    resp = StreamingResponse(_stream_gen(), media_type='application/x-ndjson')
    resp.headers['X-Request-Id'] = request.state.request_id
    return resp


@app.get('/api/version')
async def api_version():
    return {
        'APP_ENV': settings.APP_ENV,
        'ANTHROPIC_MODEL': settings.ANTHROPIC_MODEL,
    }
