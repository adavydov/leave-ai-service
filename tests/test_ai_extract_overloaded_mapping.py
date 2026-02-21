import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import UpstreamAIError, _raise_upstream, _safe_anthropic_error_message


class OverloadedError(Exception):
    pass


class DummyErr(Exception):
    def __init__(self, msg: str, status_code: int):
        super().__init__(msg)
        self.status_code = status_code


def test_safe_message_for_overloaded_error():
    msg = _safe_anthropic_error_message(OverloadedError('server overloaded'))
    assert 'перегружен' in msg.lower()


def test_safe_message_for_401_mentions_api_key():
    msg = _safe_anthropic_error_message(DummyErr('unauthorized', 401))
    assert 'anthropic_api_key' in msg.lower()


def test_safe_message_for_403_or_404_mentions_access_or_model():
    msg_403 = _safe_anthropic_error_message(DummyErr('forbidden', 403))
    msg_404 = _safe_anthropic_error_message(DummyErr('not found', 404))
    assert 'доступ' in msg_403.lower()
    assert 'модель' in msg_404.lower()


def test_safe_message_for_413_mentions_size_limits():
    msg = _safe_anthropic_error_message(DummyErr('payload too large', 413))
    assert 'слишком большой' in msg.lower()


def test_safe_message_for_422_mentions_schema_or_content_rejection():
    msg = _safe_anthropic_error_message(DummyErr('unprocessable entity', 422))
    assert 'отклонил' in msg.lower()


def test_raise_upstream_maps_overloaded_to_503():
    with pytest.raises(UpstreamAIError) as exc:
        _raise_upstream('vision', OverloadedError('overloaded now'), [])
    assert exc.value.status_code == 503
    assert 'перегружен' in str(exc.value).lower()
