import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.issues import build_decision, build_trace, from_compliance, from_validation
from app.schemas import ComplianceIssue, Issue, ValidationIssue


def test_contract_issue_and_decision_and_trace():
    validation = [ValidationIssue(level='warn', code='bad_end_date', message='bad end')]
    compliance = [ComplianceIssue(level='error', code='missing_signature', field='signature_present', message='no sign')]

    issues = [*from_validation(validation), *from_compliance(compliance)]
    decision = build_decision(issues)
    trace = build_trace('req-1', {'total_ms': 100}, {'vision': 'msg_1'})

    assert isinstance(issues, list)
    assert decision.status == 'error'
    assert decision.needs_rewrite is True
    assert trace.request_id == 'req-1'


def test_decision_marks_upstream_errors_as_error():
    issues = [
        Issue(
            severity='error',
            domain='upstream',
            category='network',
            code='anthropic_timeout',
            message='timeout',
        )
    ]
    decision = build_decision(issues)
    assert decision.status == 'error'
    assert decision.needs_rewrite is True
