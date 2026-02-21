from __future__ import annotations

from datetime import date
from typing import Any, Optional

from ..schemas import ComplianceIssue, LeaveRequestExtract
from .rules_catalog import RULES


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

    def add(
        rule_key: str,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        rule = RULES[rule_key]
        payload_details = dict(details or {})
        payload_details.setdefault("rule_id", rule.rule_id)
        payload_details.setdefault("severity", rule.severity)
        issues.append(
            ComplianceIssue(
                level=rule.severity,
                code=rule.code,
                field=field,
                message=message,
                details=payload_details or None,
            )
        )

    try:
        if not _text(extract.employer_name):
            add("missing_employer_name", "Не указана организация работодателя.", "employer_name")
        if not _text(extract.employee.full_name):
            add("missing_employee_name", "Не указано ФИО сотрудника.", "employee.full_name")
        if not _text(extract.manager.full_name):
            add("missing_manager_name", "Не указано ФИО руководителя/адресата заявления.", "manager.full_name")
        if not _text(extract.request_date):
            add("missing_request_date", "Не указана дата заявления.", "request_date")
        if not _text(extract.leave.start_date):
            add("missing_leave_start_date", "Не указана дата начала отпуска.", "leave.start_date")
        if not _text(extract.leave.end_date):
            add("missing_leave_end_date", "Не указана дата окончания отпуска.", "leave.end_date")

        if extract.signature_present is False:
            add("missing_signature", "В заявлении не обнаружена подпись сотрудника.", "signature_present")
        if extract.signature_present is True and extract.signature_confidence is not None and extract.signature_confidence < 0.6:
            add(
                "low_signature_confidence",
                "Подпись найдена, но уверенность низкая. Желательна ручная проверка.",
                "signature_confidence",
            )

        sd = _parse_iso(extract.leave.start_date)
        ed = _parse_iso(extract.leave.end_date)
        rd = _parse_iso(extract.request_date)

        if sd and ed and sd > ed:
            add("invalid_date_range", "Дата начала отпуска позже даты окончания.", "leave")

        if rd and sd:
            if rd > sd:
                add("request_after_start", "Дата заявления позже даты начала отпуска.", "request_date")
            delta = (sd - rd).days
            if 0 <= delta < 14:
                add(
                    "short_notice",
                    "До начала отпуска меньше 14 дней. По практике/графику отпусков может потребоваться согласование.",
                    "request_date",
                    {"days_before_start": delta},
                )

        expected_days: Optional[int] = None
        if sd and ed:
            expected_days = (ed - sd).days + 1

        if extract.leave.days_count is not None:
            if extract.leave.days_count <= 0:
                add("invalid_days_count", "Количество дней должно быть больше 0.", "leave.days_count")
            if expected_days is not None and expected_days != extract.leave.days_count:
                add(
                    "days_count_mismatch",
                    "Количество дней не совпадает с диапазоном дат (инклюзивно).",
                    "leave.days_count",
                    {"expected": expected_days, "actual": extract.leave.days_count},
                )
        elif expected_days is not None:
            add(
                "missing_days_count",
                "Лучше указать количество календарных дней, чтобы не было разночтений.",
                "leave.days_count",
                {"expected": expected_days},
            )

        if extract.leave.leave_type == "annual_paid" and extract.leave.days_count is not None and extract.leave.days_count < 14:
            add(
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
                    "unpaid_no_reason",
                    "Для отпуска без сохранения обычно указывают причину. Добавьте формулировку, если это необходимо.",
                    "leave.comment",
                )

        notes = [n.lower() for n in (extract.quality.notes or []) if isinstance(n, str)]
        if any(("возможно искажение" in n) or ("требует уточнения" in n) for n in notes):
            add(
                "needs_human_check",
                "В распознавании есть неоднозначности. Рекомендуется ручная проверка полей.",
                "quality.notes",
            )

    except Exception as e:  # noqa: BLE001
        add("compliance_internal_error", f"Внутренняя ошибка проверки соответствия: {type(e).__name__}")

    needs_rewrite = any(i.level == "error" for i in issues)
    return issues, needs_rewrite
