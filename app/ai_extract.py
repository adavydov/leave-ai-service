import os
import tempfile
from openai import OpenAI
from .schemas import LeaveRequestExtract

client = OpenAI()

def extract_from_pdf_bytes(pdf_bytes: bytes) -> LeaveRequestExtract:
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="user_data")

    response = client.responses.parse(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": uploaded.id},
                    {"type": "input_text", "text": "Извлеки данные заявления на отпуск строго по схеме."}
                ]
            }
        ],
        text_format=LeaveRequestExtract
    )

    return response.output_parsed
