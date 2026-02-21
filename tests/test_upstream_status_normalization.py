import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.ai_extract import UpstreamAIError
from app.main import _build_error_payload, _normalize_upstream_http_status


def test_normalize_nonstandard_529_to_503():
    assert _normalize_upstream_http_status(529) == 503


def test_build_error_payload_normalizes_529_and_exposes_request_id():
    err = UpstreamAIError(
        step='vision',
        status_code=529,
        message='AI-сервис временно недоступен. Повторите попытку позже',
        debug_steps=['Шаг vision: error_request_id=req_123ABC'],
    )
    status, payload = _build_error_payload(err, 'api_extract_stream')

    assert status == 503
    assert payload['status'] == 503
    assert payload['upstream_request_id'] == 'req_123ABC'

