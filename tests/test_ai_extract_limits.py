import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import _render_pdf_to_image_blocks


class _Rect:
    width = 1000
    height = 1000


class _Pix:
    width = 100
    height = 100

    def tobytes(self, *args, **kwargs):
        return b"abcd"


class _Page:
    rect = _Rect()

    def get_pixmap(self, **kwargs):
        return _Pix()


class _Doc:
    page_count = 1

    def load_page(self, _index):
        return _Page()

    def close(self):
        return None


def test_render_pdf_uses_max_image_b64_chars(monkeypatch):
    monkeypatch.setenv("MAX_IMAGE_B64_CHARS", "3")
    monkeypatch.setattr("app.ai_extract.fitz.open", lambda **kwargs: _Doc())

    with pytest.raises(RuntimeError, match="approx_b64_chars"):
        _render_pdf_to_image_blocks(b"dummy", [])
