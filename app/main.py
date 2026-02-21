from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
from typing import Any

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .ai_extract import UpstreamAIError, extract_leave_request_with_debug
from .compliance import COMPLIANCE_RULES_VERSION, run_compliance_checks
from .schemas import ApiResponse
from .validation import validate_extract

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Leave Request Parser (RU)")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    resp = templates.TemplateResponse(
        "index.html",
        {"request": request, "max_upload_mb": MAX_UPLOAD_MB, "mock_mode": os.getenv("MOCK_MODE", "0")},
    )
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


def _anthropic_probe() -> dict:
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=16,
        temperature=0,
        messages=[{"role": "user", "content": "Ответь одним словом: ok"}],
    )
    text = ""
    for block in (msg.content or []):
        if getattr(block, "type", None) == "text":
            text += getattr(block, "text", "")
    return {"status": "ok", "model": model, "reply": text.strip()[:80]}


@app.get("/api/health/anthropic")
async def api_health_anthropic():
    if os.getenv("MOCK_MODE", "0") == "1":
        return {"status": "ok", "mode": "mock"}

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY не задан в переменных окружения.")

    try:
        return await run_in_threadpool(_anthropic_probe)
    except anthropic.APIError as e:
        logger.exception("Anthropic health probe APIError")
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e}")
    except Exception:
        logger.exception("Unexpected anthropic health probe error")
        raise HTTPException(status_code=500, detail="Ошибка health-check Anthropic. Подробности в логах сервера.")


async def _read_pdf_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Пожалуйста, загрузите PDF файл.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой. Лимит: {MAX_UPLOAD_MB} MB.")
    return filename, data


def _sanitize_error_message(err: Exception) -> str:
    message = re.sub(r"<[^>]+>", " ", str(err or "")).strip()
    message = re.sub(r"\s+", " ", message).strip(" .,:;-")
    if not message:
        return f"Ошибка обработки: {type(err).__name__}"
    if message.lower() == "internal server error":
        return f"Internal Server Error ({type(err).__name__})"
    return message[:320]


def _build_error_payload(err: Exception, where: str) -> tuple[int, dict[str, Any]]:
    if isinstance(err, UpstreamAIError):
        logger.exception("UpstreamAIError in %s (step=%s, status=%s)", where, getattr(err, "step", "unknown"), err.status_code)
        status = err.status_code
        return status, {
            "error": "Ошибка при обработке PDF.",
            "status": status,
            "detail": _sanitize_error_message(err),
            "debug_steps": getattr(err, "debug_steps", []),
        }

    if isinstance(err, anthropic.APIError):
        logger.exception("Anthropic APIError in %s", where)
        return 502, {
            "error": "Ошибка при обработке PDF.",
            "status": 502,
            "detail": "AI-сервис временно недоступен. Повторите попытку позже.",
            "debug_steps": [f"Anthropic APIError в {where}: {type(err).__name__}", _sanitize_error_message(err)],
        }

    logger.exception("Unexpected error in %s", where)
    status = 502 if str(err).strip().lower() == "internal server error" else 500
    return status, {
        "error": "Ошибка при обработке PDF.",
        "status": status,
        "detail": _sanitize_error_message(err),
        "debug_steps": [f"Непредвиденная ошибка {where}: {type(err).__name__}", _sanitize_error_message(err)],
    }


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...)):
    filename, data = await _read_pdf_upload(file)
    try:
        extract, debug_steps = await run_in_threadpool(extract_leave_request_with_debug, data, filename)
        validation = validate_extract(extract)
        compliance, needs_rewrite = run_compliance_checks(extract)
        resp = ApiResponse(
            extract=extract,
            validation=validation,
            compliance=compliance,
            needs_rewrite=needs_rewrite,
            compliance_rules_version=COMPLIANCE_RULES_VERSION,
        ).model_dump()
        resp["debug_steps"] = debug_steps
        return resp
    except Exception as e:
        status, payload = _build_error_payload(e, "api_extract")
        return JSONResponse(status_code=status, content=payload)


@app.post("/api/extract/stream")
async def api_extract_stream(file: UploadFile = File(...)):
    filename, data = await _read_pdf_upload(file)
    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def _on_debug(step: str) -> None:
        events.put({"type": "step", "message": step})

    def _worker() -> None:
        try:
            extract, debug_steps = extract_leave_request_with_debug(data, filename, on_debug=_on_debug)
            validation = validate_extract(extract)
            compliance, needs_rewrite = run_compliance_checks(extract)
            resp = ApiResponse(
                extract=extract,
                validation=validation,
                compliance=compliance,
                needs_rewrite=needs_rewrite,
                compliance_rules_version=COMPLIANCE_RULES_VERSION,
            ).model_dump()
            resp["debug_steps"] = debug_steps
            events.put({"type": "result", "ok": True, "status": 200, "payload": resp})
        except Exception as e:
            status, payload = _build_error_payload(e, "api_extract_stream")
            events.put({"type": "result", "ok": False, "status": status, "payload": payload})

    threading.Thread(target=_worker, daemon=True).start()

    async def _stream_gen():
        while True:
            event = await run_in_threadpool(events.get)
            yield (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
            if event.get("type") == "result":
                break

    return StreamingResponse(_stream_gen(), media_type="application/x-ndjson")


@app.get("/api/version")
async def api_version():
    return {
        "RENDER_GIT_COMMIT": os.getenv("RENDER_GIT_COMMIT"),
        "RENDER_GIT_BRANCH": os.getenv("RENDER_GIT_BRANCH"),
        "RENDER_GIT_REPO_SLUG": os.getenv("RENDER_GIT_REPO_SLUG"),
        "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL"),
        "MOCK_MODE": os.getenv("MOCK_MODE"),
    }
