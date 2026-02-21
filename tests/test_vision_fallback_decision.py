import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import _resolve_vision_fallback_model, _should_try_vision_fallback


class OverloadedError(Exception):
    pass


def test_resolve_prefers_configured_model_when_different():
    assert _resolve_vision_fallback_model('claude-opus-4-6', 'claude-sonnet-4-6') == 'claude-sonnet-4-6'


def test_resolve_autofallback_for_opus_without_env():
    assert _resolve_vision_fallback_model('claude-opus-4-6', None) == 'claude-sonnet-4-6'


def test_resolve_no_fallback_for_non_opus_without_env():
    assert _resolve_vision_fallback_model('claude-sonnet-4-6', None) is None


def test_fallback_enabled_only_for_overloaded_errors():
    assert _should_try_vision_fallback(OverloadedError('overloaded'), 'claude-opus-4-6', 'claude-sonnet-4-6') is True


def test_fallback_disabled_when_not_overloaded():
    assert _should_try_vision_fallback(Exception('bad gateway'), 'claude-opus-4-6', 'claude-sonnet-4-6') is False


def test_fallback_enabled_for_opus_even_without_env_when_overloaded():
    assert _should_try_vision_fallback(OverloadedError('overloaded'), 'claude-opus-4-6', None) is True
