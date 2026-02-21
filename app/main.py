from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import hashlib

app = FastAPI(title="Leave AI Service (MVP)")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        return JSONResponse({"error": "Empty file"}, status_code=400)

    if (file.content_type or "").lower() not in ("application/pdf", "application/x-pdf", ""):
        # Некоторые браузеры/сканеры присылают пустой content-type. Не драматизируем.
        pass

    sha256 = hashlib.sha256(data).hexdigest()

    return {
        "file_name": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(data),
        "sha256": sha256,
        "note": "MVP: загрузка работает. Следующий шаг: отправить PDF в OpenAI и вернуть структурированный JSON по схеме."
    }
