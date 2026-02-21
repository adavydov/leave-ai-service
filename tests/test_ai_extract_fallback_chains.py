import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import ai_extract
from app.schemas import LeaveRequestExtract


class FakeAPIError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class FakeTimeoutError(TimeoutError):
    pass


class _Msg:
    def __init__(self, text: str, request_id: str = "req_ok"):
        self.content = [{"type": "text", "text": text}]
        self.request_id = request_id


class _ParseResult:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class FakeMessages:
    def __init__(self, plan: dict[str, list]):
        self.plan = {k: list(v) for k, v in plan.items()}
        self.calls = {"create": 0, "parse": 0}

    def create(self, **kwargs):
        self.calls["create"] += 1
        action = self.plan["create"].pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    def parse(self, **kwargs):
        self.calls["parse"] += 1
        action = self.plan["parse"].pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class FakeClient:
    def __init__(self, messages: FakeMessages):
        self.messages = messages

    def with_options(self, **kwargs):
        return self


def _valid_extract(raw_text: str = "ok"):
    return LeaveRequestExtract.model_validate(
        {
            "schema_version": "1.0",
            "employer_name": None,
            "employee": {"full_name": "Иванов Иван Иванович"},
            "manager": {"full_name": None, "position": None},
            "request_date": "2026-01-01",
            "leave": {"leave_type": "annual_paid", "start_date": "2026-02-01", "end_date": "2026-02-14", "days_count": 14},
            "signature_present": True,
            "signature_confidence": 0.8,
            "raw_text": raw_text,
            "quality": {"overall_confidence": 0.8, "missing_fields": [], "notes": []},
        }
    )


def _prepare(monkeypatch, plan):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_VISION_MODEL", "claude-opus-4-6")
    monkeypatch.setenv("ANTHROPIC_STRUCTURED_MODEL", "claude-opus-4-6")
    monkeypatch.delenv("ANTHROPIC_STRUCTURED_FALLBACK_MODEL", raising=False)

    monkeypatch.setattr(ai_extract.anthropic, "APIError", FakeAPIError)
    monkeypatch.setattr(ai_extract.anthropic, "APITimeoutError", FakeTimeoutError)

    fake_messages = FakeMessages(plan)
    fake_client = FakeClient(fake_messages)

    monkeypatch.setattr(ai_extract, "_create_anthropic_client", lambda **kwargs: fake_client)
    monkeypatch.setattr(
        ai_extract,
        "_render_pdf_to_image_blocks",
        lambda pdf_bytes, debug_steps, on_debug=None: ([{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}}], {"pages_sent": 1, "total_pages": 1, "target_long_edge": 1024, "approx_b64_chars": 1, "color_mode": "gray"}),
    )
    return fake_messages


def test_vision_529_then_fallback_success_and_structured_parse_success(monkeypatch):
    messages = _prepare(
        monkeypatch,
        {
            "create": [FakeAPIError("overloaded", 529), _Msg("TRANSCRIPTION: ok")],
            "parse": [_ParseResult(_valid_extract("parsed"))],
        },
    )

    parsed, _ = ai_extract.extract_leave_request_with_debug(b"%PDF-1.4", filename="x.pdf")

    assert parsed.raw_text == "parsed"
    assert messages.calls == {"create": 2, "parse": 1}


def test_structured_parse_timeout_then_parse_fallback_success(monkeypatch):
    messages = _prepare(
        monkeypatch,
        {
            "create": [_Msg("TRANSCRIPTION: ok")],
            "parse": [FakeTimeoutError("t1"), _ParseResult(_valid_extract("fallback-parse"))],
        },
    )

    parsed, _ = ai_extract.extract_leave_request_with_debug(b"%PDF-1.4", filename="x.pdf")

    assert parsed.raw_text == "fallback-parse"
    assert messages.calls == {"create": 1, "parse": 2}


def test_structured_parse_timeout_then_fallback_timeout_then_create_success(monkeypatch):
    payload_json = '{"schema_version":"1.0","employee":{"full_name":"Иванов Иван Иванович"},"manager":{"full_name":null,"position":null},"request_date":"2026-01-01","leave":{"leave_type":"annual_paid","start_date":"2026-02-01","end_date":"2026-02-14","days_count":14},"signature_present":true,"signature_confidence":0.9,"raw_text":"create-fallback","quality":{"overall_confidence":0.8,"missing_fields":[],"notes":[]}}'
    messages = _prepare(
        monkeypatch,
        {
            "create": [_Msg("TRANSCRIPTION: ok"), _Msg(payload_json)],
            "parse": [FakeTimeoutError("t1"), FakeTimeoutError("t2")],
        },
    )

    parsed, _ = ai_extract.extract_leave_request_with_debug(b"%PDF-1.4", filename="x.pdf")

    assert parsed.raw_text == "create-fallback"
    assert messages.calls == {"create": 2, "parse": 2}


def test_structured_parse_422_does_not_try_any_fallback(monkeypatch):
    messages = _prepare(
        monkeypatch,
        {
            "create": [_Msg("TRANSCRIPTION: ok")],
            "parse": [FakeAPIError("bad schema", 422)],
        },
    )

    try:
        ai_extract.extract_leave_request_with_debug(b"%PDF-1.4", filename="x.pdf")
    except ai_extract.UpstreamAIError as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("expected UpstreamAIError")

    assert messages.calls == {"create": 1, "parse": 1}


def test_structured_parse_529_then_parse_fallback_success(monkeypatch):
    messages = _prepare(
        monkeypatch,
        {
            "create": [_Msg("TRANSCRIPTION: ok")],
            "parse": [FakeAPIError("overloaded", 529), _ParseResult(_valid_extract("parse-fallback-529"))],
        },
    )

    parsed, _ = ai_extract.extract_leave_request_with_debug(b"%PDF-1.4", filename="x.pdf")

    assert parsed.raw_text == "parse-fallback-529"
    assert messages.calls == {"create": 1, "parse": 2}
