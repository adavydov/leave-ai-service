import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import UpstreamAIError, _raise_upstream, _safe_anthropic_error_message


class OverloadedError(Exception):
    pass


def test_safe_message_for_overloaded_error():
    msg = _safe_anthropic_error_message(OverloadedError('server overloaded'))
    assert 'перегружен' in msg.lower()


def test_raise_upstream_maps_overloaded_to_503():
    with pytest.raises(UpstreamAIError) as exc:
        _raise_upstream('vision', OverloadedError('overloaded now'), [])
    assert exc.value.status_code == 503
    assert 'перегружен' in str(exc.value).lower()
