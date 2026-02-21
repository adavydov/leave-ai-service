from __future__ import annotations

from .types import Rule


RULES = {
    "missing_employer_name": Rule("CR-001", "error", "missing_employer_name"),
    "missing_employee_name": Rule("CR-002", "error", "missing_employee_name"),
    "missing_manager_name": Rule("CR-003", "warn", "missing_manager_name"),
    "missing_request_date": Rule("CR-004", "error", "missing_request_date"),
    "missing_leave_start_date": Rule("CR-005", "error", "missing_leave_start_date"),
    "missing_leave_end_date": Rule("CR-006", "error", "missing_leave_end_date"),
    "missing_signature": Rule("CR-007", "error", "missing_signature"),
    "low_signature_confidence": Rule("CR-008", "warn", "low_signature_confidence"),
    "invalid_date_range": Rule("CR-009", "error", "invalid_date_range"),
    "request_after_start": Rule("CR-010", "warn", "request_after_start"),
    "short_notice": Rule("CR-011", "info", "short_notice"),
    "invalid_days_count": Rule("CR-012", "error", "invalid_days_count"),
    "days_count_mismatch": Rule("CR-013", "error", "days_count_mismatch"),
    "missing_days_count": Rule("CR-014", "warn", "missing_days_count"),
    "annual_paid_part_lt14": Rule("CR-015", "warn", "annual_paid_part_lt14"),
    "unpaid_no_reason": Rule("CR-016", "info", "unpaid_no_reason"),
    "needs_human_check": Rule("CR-017", "info", "needs_human_check"),
    "compliance_internal_error": Rule("CR-018", "warn", "compliance_internal_error"),
}
