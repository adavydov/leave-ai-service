import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import (
    _resolve_structured_fallback_model,
    _resolve_vision_fallback_model,
    _should_try_structured_parse_fallback,
    _should_try_vision_fallback,
)


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


def test_resolve_structured_prefers_configured_model_when_different():
    assert _resolve_structured_fallback_model('claude-opus-4-6', 'claude-sonnet-4-6') == 'claude-sonnet-4-6'


def test_resolve_structured_autofallback_for_opus_without_env():
    assert _resolve_structured_fallback_model('claude-opus-4-6', None) == 'claude-sonnet-4-6'


def test_resolve_structured_no_fallback_for_non_opus_without_env():
    assert _resolve_structured_fallback_model('claude-sonnet-4-6', None) is None


def test_structured_parse_fallback_enabled_on_timeout_for_opus():
    assert _should_try_structured_parse_fallback(TimeoutError('timed out'), 'claude-opus-4-6', None) is True


def test_structured_parse_fallback_disabled_for_non_opus_without_config():
    assert _should_try_structured_parse_fallback(TimeoutError('timed out'), 'claude-sonnet-4-6', None) is False


def test_structured_parse_fallback_enabled_with_configured_model_on_timeout():
    assert _should_try_structured_parse_fallback(TimeoutError('timed out'), 'claude-sonnet-4-6', 'claude-haiku-4-5') is True
