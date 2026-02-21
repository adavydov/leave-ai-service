import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.compliance import run_compliance_checks
from app.schemas import LeaveRequestExtract


def _base_extract(**kwargs):
    payload = {
        "employer_name": "ООО Ромашка",
        "employee": {"full_name": "Иванов И.И."},
        "manager": {"full_name": "Петров П.П."},
        "request_date": "2026-02-01",
        "leave": {
            "leave_type": "annual_paid",
            "start_date": "2026-02-10",
            "end_date": "2026-02-16",
            "days_count": 7,
        },
        "signature_present": True,
        "signature_confidence": 0.9,
    }
    payload.update(kwargs)
    return LeaveRequestExtract.model_validate(payload)


def _codes(issues):
    return {i.code: i for i in issues}


def test_invalid_date_range_error():
    ex = _base_extract(leave={"leave_type": "annual_paid", "start_date": "2026-02-20", "end_date": "2026-02-10", "days_count": 11})
    issues, needs_rewrite = run_compliance_checks(ex)
    codes = _codes(issues)
    assert "invalid_date_range" in codes
    assert codes["invalid_date_range"].level == "error"
    assert needs_rewrite is True


def test_days_count_mismatch_error_with_explainable_fields():
    ex = _base_extract(leave={"leave_type": "annual_paid", "start_date": "2026-02-10", "end_date": "2026-02-16", "days_count": 8})
    issues, _ = run_compliance_checks(ex)
    codes = _codes(issues)
    assert "days_count_mismatch" in codes
    assert codes["days_count_mismatch"].details == {"expected": 7, "actual": 8}
    assert codes["days_count_mismatch"].rule_id == "COUNT-002"
    assert "дней" in (codes["days_count_mismatch"].action_hint or "")


def test_annual_paid_part_lt14_warn_not_error():
    ex = _base_extract(leave={"leave_type": "annual_paid", "start_date": "2026-02-10", "end_date": "2026-02-16", "days_count": 7})
    issues, _ = run_compliance_checks(ex)
    codes = _codes(issues)
    assert "annual_paid_part_lt14" in codes
    assert codes["annual_paid_part_lt14"].level == "warn"
    assert codes["annual_paid_part_lt14"].rule_id == "LAW-122-001"


def test_missing_signature_error():
    ex = _base_extract(signature_present=False)
    issues, needs_rewrite = run_compliance_checks(ex)
    codes = _codes(issues)
    assert "missing_signature" in codes
    assert codes["missing_signature"].level == "error"
    assert needs_rewrite is True


def test_unpaid_without_reason_info():
    ex = _base_extract(
        leave={"leave_type": "unpaid", "start_date": "2026-02-10", "end_date": "2026-02-12", "days_count": 3, "comment": None},
        raw_text="Прошу предоставить отпуск без сохранения",
    )
    issues, _ = run_compliance_checks(ex)
    codes = _codes(issues)
    assert "unpaid_no_reason" in codes
    assert codes["unpaid_no_reason"].level == "info"
