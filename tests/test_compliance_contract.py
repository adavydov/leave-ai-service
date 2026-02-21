import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.compliance import COMPLIANCE_RULES_VERSION, run_compliance_checks
from app.schemas import LeaveRequestExtract


def test_compliance_issue_details_has_rule_id():
    extract = LeaveRequestExtract.model_validate(
        {
            "employee": {"full_name": "Иванов И.И."},
            "manager": {"full_name": "Петров П.П."},
            "request_date": "2026-02-05",
            "leave": {"leave_type": "annual_paid", "start_date": "2026-02-10", "end_date": "2026-02-16", "days_count": 8},
            "signature_present": True,
        }
    )
    issues, _ = run_compliance_checks(extract)
    mismatch = next(i for i in issues if i.code == "days_count_mismatch")
    assert mismatch.details is not None
    assert mismatch.details.rule_id == "days_count_mismatch"


def test_ruleset_version_constant_present():
    assert COMPLIANCE_RULES_VERSION.startswith("tkrf-mvp-")
