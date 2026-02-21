import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import _upstream_error_to_issue_and_status


class DummyErr(Exception):
    def __init__(self, message, status_code=0):
        super().__init__(message)
        self.status_code = status_code


def test_timeout_mapping():
    status, issue = _upstream_error_to_issue_and_status(DummyErr('timeout happened'), 'structured.parse')
    assert status == 504
    assert issue.code == 'anthropic_timeout'


def test_rate_limit_mapping():
    status, issue = _upstream_error_to_issue_and_status(DummyErr('rate', 429), 'structured.parse')
    assert status == 503
    assert issue.code == 'anthropic_rate_limited'
