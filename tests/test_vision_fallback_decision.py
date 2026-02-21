import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import _should_try_vision_fallback


class OverloadedError(Exception):
    pass


def test_fallback_enabled_only_for_overloaded_errors():
    assert _should_try_vision_fallback(OverloadedError('overloaded'), 'claude-opus-4-6', 'claude-sonnet-4-6') is True


def test_fallback_disabled_when_models_match():
    assert _should_try_vision_fallback(OverloadedError('overloaded'), 'claude-opus-4-6', 'claude-opus-4-6') is False


def test_fallback_disabled_when_not_overloaded():
    assert _should_try_vision_fallback(Exception('bad gateway'), 'claude-opus-4-6', 'claude-sonnet-4-6') is False
