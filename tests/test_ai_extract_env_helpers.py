import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import _max_image_b64_chars_limit, _resolve_structured_model


def test_prefers_canonical_max_image_b64_chars(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_B64_CHARS', '12345')
    monkeypatch.setenv('PDF_MAX_B64_BYTES', '999')
    assert _max_image_b64_chars_limit() == 12345


def test_falls_back_to_legacy_pdf_max_b64_bytes(monkeypatch):
    monkeypatch.delenv('MAX_IMAGE_B64_CHARS', raising=False)
    monkeypatch.setenv('PDF_MAX_B64_BYTES', '54321')
    assert _max_image_b64_chars_limit() == 54321


def test_invalid_env_uses_default(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_B64_CHARS', 'abc')
    monkeypatch.delenv('PDF_MAX_B64_BYTES', raising=False)
    assert _max_image_b64_chars_limit() == 4_000_000


def test_resolve_structured_model_defaults_to_sonnet():
    assert _resolve_structured_model(None) == "claude-sonnet-4-6"


def test_resolve_structured_model_uses_explicit_model():
    assert _resolve_structured_model("claude-opus-4-6") == "claude-opus-4-6"
