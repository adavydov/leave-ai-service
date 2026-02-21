import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool

from .ai_extract import extract_from_pdf_bytes

load_dotenv()

app = FastAPI(title="Leave AI Service")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health/openai")
async def openai_health():
    from openai import OpenAI
    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    try:
        r = client.responses.create(
            model=model,
            input="Say OK",
            max_output_tokens=5
        )
        return {"status": "ok", "model": model}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    result = await run_in_threadpool(extract_from_pdf_bytes, data)
    return result.model_dump()
