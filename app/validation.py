from __future__ import annotations

from datetime import date
from typing import List

from .schemas import LeaveRequestExtract, ValidationIssue


def _parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def validate_extract(ex: LeaveRequestExtract) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    def add(level: str, code: str, message: str):
        issues.append(ValidationIssue(level=level, code=code, message=message))

    # минимальный sanity-check (не ТК РФ, просто чтобы не вылететь в прод с мусором)
    if not ex.employee.full_name:
        add("error", "missing_employee_full_name", "Не найдено ФИО сотрудника.")
    if not ex.leave.start_date:
        add("error", "missing_leave_start_date", "Не найдена дата начала отпуска.")
    if not ex.leave.end_date and ex.leave.days_count is None:
        add("warn", "missing_end_or_days", "Нет даты окончания и нет количества дней (нужно хотя бы одно).")

    sd = _parse_iso(ex.leave.start_date)
    ed = _parse_iso(ex.leave.end_date)
    if ex.leave.start_date and not sd:
        add("error", "bad_start_date", "start_date не в формате YYYY-MM-DD.")
    if ex.leave.end_date and not ed:
        add("error", "bad_end_date", "end_date не в формате YYYY-MM-DD.")
    if sd and ed and ed < sd:
        add("error", "dates_inverted", "Дата окончания раньше даты начала.")

    if ex.quality.overall_confidence < 0.6:
        add("warn", "low_confidence", f"Низкая уверенность распознавания: {ex.quality.overall_confidence:.2f}")

    return issues
