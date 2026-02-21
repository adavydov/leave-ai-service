import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


def test_extract_invalid_file_returns_contract():
    client = TestClient(app)
    files = {'file': ('note.txt', b'hello', 'text/plain')}
    r = client.post('/api/extract', files=files)
    assert r.status_code == 400
    js = r.json()
    assert 'issues' in js
    assert 'decision' in js
    assert 'trace' in js
    assert js['issues'][0]['code'] == 'pdf_invalid_type'


def test_extract_too_large_returns_contract():
    client = TestClient(app)
    big = b'%' + b'a' * (16 * 1024 * 1024)
    files = {'file': ('a.pdf', big, 'application/pdf')}
    r = client.post('/api/extract', files=files)
    assert r.status_code == 413
    js = r.json()
    assert js['issues'][0]['code'] == 'pdf_too_large'
