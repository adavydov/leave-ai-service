from __future__ import annotations

import os
import re

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .ai_extract import UpstreamAIError, extract_leave_request_from_pdf_bytes
from .schemas import ApiResponse
from .validation import validate_extract

# Load .env for local dev (Render uses env vars)
load_dotenv()

app = FastAPI(title="Leave Request Parser (RU)")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "max_upload_mb": MAX_UPLOAD_MB, "mock_mode": os.getenv("MOCK_MODE", "0")},
    )


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


def _anthropic_probe() -> dict:
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = Anthropic()  # берет ANTHROPIC_API_KEY из env по умолчанию
    msg = client.messages.create(
        model=model,
        max_tokens=16,
        temperature=0,
        messages=[{"role": "user", "content": "Ответь одним словом: ok"}],
    )
    # msg.content — список блоков; достанем текст
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
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {type(e).__name__}: {e}")


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...)):
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Пожалуйста, загрузите PDF файл.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Файл слишком большой. Лимит: {MAX_UPLOAD_MB} MB.")

    try:
        extract = await run_in_threadpool(extract_leave_request_from_pdf_bytes, data, filename)
        validation = validate_extract(extract)
        resp = ApiResponse(extract=extract, validation=validation)
        return resp.model_dump()
    except UpstreamAIError as e:
        raise HTTPException(status_code=e.status_code, detail=_sanitize_error_message(e))
    except Exception as e:
        status = 502 if _is_upstream_ai_error(e) else 500
        raise HTTPException(status_code=status, detail=_sanitize_upstream_error(e))


def _is_upstream_ai_error(err: Exception) -> bool:
    message = str(err or "").lower()
    markers = (
        "anthropic",
        "structured step failed",
        "vision step failed",
        "api_error",
        "internal server error",
        "gateway",
        "bad gateway",
        "upstream",
    )
    return isinstance(err, anthropic.APIError) or any(marker in message for marker in markers)


def _sanitize_upstream_error(err: Exception) -> str:
    """Убираем HTML/технические детали и отдаём безопасный текст ошибки."""
    message = str(err or "").strip()
    if not message:
        return f"Ошибка обработки: {type(err).__name__}"

    message = re.sub(r"render_info\s*=\s*\{.*", "", message, flags=re.IGNORECASE)
    message = re.sub(r'request_id[\'"]?\s*[:=]\s*[\'"][^\'"]+[\'"]', "", message, flags=re.IGNORECASE)
    message = re.sub(r"<[^>]+>", " ", message)
    message = re.sub(r"\s+", " ", message).strip(" .,:;-")

    if _is_upstream_ai_error(err):
        return "Ошибка внешнего AI-сервиса. Повторите попытку позже."

    return f"Ошибка обработки: {type(err).__name__}: {message[:220]}"

@app.get("/api/version")
async def api_version():
    import os
    return {
        "RENDER_GIT_COMMIT": os.getenv("RENDER_GIT_COMMIT"),
        "RENDER_GIT_BRANCH": os.getenv("RENDER_GIT_BRANCH"),
        "RENDER_GIT_REPO_SLUG": os.getenv("RENDER_GIT_REPO_SLUG"),
        "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL"),
        "MOCK_MODE": os.getenv("MOCK_MODE"),
    }
