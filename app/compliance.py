from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .schemas import ComplianceIssue, LeaveRequestExtract


COMPLIANCE_RULES_VERSION = "1.1"


def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _text(v: Optional[str]) -> str:
    return (v or "").strip()


def run_compliance_checks(extract: LeaveRequestExtract) -> tuple[list[ComplianceIssue], bool]:
    issues: list[ComplianceIssue] = []

    def details(
        rule_id: str,
        law_ref: Optional[str] = None,
        expected: Optional[str | int | float] = None,
        actual: Optional[str | int | float] = None,
    ) -> dict[str, Optional[str | int | float]]:
        return {
            "rule_id": rule_id,
            "law_ref": law_ref,
            "expected": expected,
            "actual": actual,
        }

    def add(level: str, code: str, message: str, field: Optional[str] = None, details: Optional[dict[str, Any]] = None) -> None:
        issues.append(ComplianceIssue(level=level, code=code, field=field, message=message, details=details))

    try:
        # A) Required fields
        if not _text(extract.employer_name):
            add("error", "missing_employer_name", "Не указана организация работодателя.", "employer_name")
        if not _text(extract.employee.full_name):
            add("error", "missing_employee_name", "Не указано ФИО сотрудника.", "employee.full_name")
        if not _text(extract.manager.full_name):
            add("warn", "missing_manager_name", "Не указано ФИО руководителя/адресата заявления.", "manager.full_name")
        if not _text(extract.request_date):
            add("error", "missing_request_date", "Не указана дата заявления.", "request_date")
        if not _text(extract.leave.start_date):
            add("error", "missing_leave_start_date", "Не указана дата начала отпуска.", "leave.start_date")
        if not _text(extract.leave.end_date):
            add("error", "missing_leave_end_date", "Не указана дата окончания отпуска.", "leave.end_date")

        if extract.signature_present is False:
            add("error", "missing_signature", "В заявлении не обнаружена подпись сотрудника.", "signature_present")
        if extract.signature_present is True and extract.signature_confidence is not None and extract.signature_confidence < 0.6:
            add("warn", "low_signature_confidence", "Подпись найдена, но уверенность низкая. Желательна ручная проверка.", "signature_confidence")

        # B/C) Date logic and days count
        sd = _parse_iso(extract.leave.start_date)
        ed = _parse_iso(extract.leave.end_date)
        rd = _parse_iso(extract.request_date)

        if sd and ed and sd > ed:
            add("error", "invalid_date_range", "Дата начала отпуска позже даты окончания.", "leave")

        if rd and sd:
            if rd > sd:
                add("warn", "request_after_start", "Дата заявления позже даты начала отпуска.", "request_date")
            delta = (sd - rd).days
            if 0 <= delta < 14:
                add(
                    "info",
                    "short_notice",
                    "До начала отпуска меньше 14 дней. По практике/графику отпусков может потребоваться согласование.",
                    "request_date",
                    details(
                        rule_id="short_notice",
                        law_ref="ТК РФ ст. 123",
                        expected=14,
                        actual=delta,
                    ),
                )

        expected_days: Optional[int] = None
        if sd and ed:
            expected_days = (ed - sd).days + 1

        if extract.leave.days_count is not None:
            if extract.leave.days_count <= 0:
                add("error", "invalid_days_count", "Количество дней должно быть больше 0.", "leave.days_count")
            if expected_days is not None and expected_days != extract.leave.days_count:
                add(
                    "error",
                    "days_count_mismatch",
                    "Количество дней не совпадает с диапазоном дат (инклюзивно).",
                    "leave.days_count",
                    details(
                        rule_id="days_count_mismatch",
                        expected=expected_days,
                        actual=extract.leave.days_count,
                    ),
                )
        elif expected_days is not None:
            add(
                "warn",
                "missing_days_count",
                "Лучше указать количество календарных дней, чтобы не было разночтений.",
                "leave.days_count",
                details(
                    rule_id="missing_days_count",
                    expected=expected_days,
                ),
            )

        # D) TK-oriented hints
        if extract.leave.leave_type == "annual_paid" and extract.leave.days_count is not None and extract.leave.days_count < 14:
            add(
                "warn",
                "annual_paid_part_lt14",
                "Если ежегодный отпуск делится на части, одна часть должна быть не менее 14 календарных дней. Убедитесь, что в другом периоде есть 14+ дней.",
                "leave.days_count",
            )

        if extract.leave.leave_type == "unpaid":
            comment = _text(extract.leave.comment).lower()
            raw = _text(extract.raw_text).lower()
            markers = ["по семейным обстоятельствам", "по состоянию здоровья", "по уходу", "по причине"]
            if not comment and not any(m in raw for m in markers):
                add(
                    "info",
                    "unpaid_no_reason",
                    "Для отпуска без сохранения обычно указывают причину. Добавьте формулировку, если это необходимо.",
                    "leave.comment",
                )

        # E) quality hints
        notes = [n.lower() for n in (extract.quality.notes or []) if isinstance(n, str)]
        if any(("возможно искажение" in n) or ("требует уточнения" in n) for n in notes):
            add("info", "needs_human_check", "В распознавании есть неоднозначности. Рекомендуется ручная проверка полей.", "quality.notes")

    except Exception as e:  # noqa: BLE001
        add(
            "warn",
            "compliance_internal_error",
            f"Внутренняя ошибка проверки соответствия: {type(e).__name__}",
        )

    needs_rewrite = any(i.level == "error" for i in issues)
    return issues, needs_rewrite
