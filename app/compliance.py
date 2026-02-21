from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from .schemas import ComplianceIssue, LeaveRequestExtract

COMPLIANCE_RULES_VERSION = "tkrf-mvp-2026-02-21"

RuleFn = Callable[[LeaveRequestExtract], list[ComplianceIssue]]


def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _text(v: Optional[str]) -> str:
    return (v or "").strip()


def _issue(
    *,
    level: str,
    code: str,
    message: str,
    field: Optional[str] = None,
    law_ref: Optional[str] = None,
    expected: Any = None,
    actual: Any = None,
    extras: Optional[dict[str, Any]] = None,
) -> ComplianceIssue:
    details: dict[str, Any] = {"rule_id": code}
    if law_ref:
        details["law_ref"] = law_ref
    if expected is not None:
        details["expected"] = expected
    if actual is not None:
        details["actual"] = actual
    if extras:
        details.update(extras)
    return ComplianceIssue(level=level, code=code, field=field, message=message, details=details)


def _rule_required_fields(extract: LeaveRequestExtract) -> list[ComplianceIssue]:
    out: list[ComplianceIssue] = []
    if not _text(extract.employer_name):
        out.append(
            _issue(
                level="error",
                code="missing_employer_name",
                field="employer_name",
                message="Не указана организация работодателя.",
                law_ref="ТК РФ (общие требования к кадровым документам)",
                expected="Заполненное наименование работодателя",
                actual=extract.employer_name,
            )
        )
    if not _text(extract.employee.full_name):
        out.append(
            _issue(
                level="error",
                code="missing_employee_name",
                field="employee.full_name",
                message="Не указано ФИО сотрудника.",
                law_ref="ТК РФ ст. 21, 22 (идентификация сторон трудовых отношений)",
                expected="ФИО сотрудника",
                actual=extract.employee.full_name,
            )
        )
    if not _text(extract.manager.full_name):
        out.append(
            _issue(
                level="warn",
                code="missing_manager_name",
                field="manager.full_name",
                message="Не указано ФИО руководителя/адресата заявления.",
                expected="ФИО адресата",
                actual=extract.manager.full_name,
            )
        )
    if not _text(extract.request_date):
        out.append(
            _issue(
                level="error",
                code="missing_request_date",
                field="request_date",
                message="Не указана дата заявления.",
                expected="YYYY-MM-DD",
                actual=extract.request_date,
            )
        )
    if not _text(extract.leave.start_date):
        out.append(
            _issue(
                level="error",
                code="missing_leave_start_date",
                field="leave.start_date",
                message="Не указана дата начала отпуска.",
                expected="YYYY-MM-DD",
                actual=extract.leave.start_date,
            )
        )
    if not _text(extract.leave.end_date):
        out.append(
            _issue(
                level="error",
                code="missing_leave_end_date",
                field="leave.end_date",
                message="Не указана дата окончания отпуска.",
                expected="YYYY-MM-DD",
                actual=extract.leave.end_date,
            )
        )

    if extract.signature_present is False:
        out.append(
            _issue(
                level="error",
                code="missing_signature",
                field="signature_present",
                message="В заявлении не обнаружена подпись сотрудника.",
                expected=True,
                actual=extract.signature_present,
            )
        )
    if extract.signature_present is True and extract.signature_confidence is not None and extract.signature_confidence < 0.6:
        out.append(
            _issue(
                level="warn",
                code="low_signature_confidence",
                field="signature_confidence",
                message="Подпись найдена, но уверенность низкая. Желательна ручная проверка.",
                expected=">= 0.6",
                actual=extract.signature_confidence,
            )
        )
    return out


def _rule_date_logic(extract: LeaveRequestExtract) -> list[ComplianceIssue]:
    out: list[ComplianceIssue] = []
    sd = _parse_iso(extract.leave.start_date)
    ed = _parse_iso(extract.leave.end_date)
    rd = _parse_iso(extract.request_date)

    if sd and ed and sd > ed:
        out.append(
            _issue(
                level="error",
                code="invalid_date_range",
                field="leave",
                message="Дата начала отпуска позже даты окончания.",
                expected="start_date <= end_date",
                actual={"start_date": extract.leave.start_date, "end_date": extract.leave.end_date},
            )
        )

    if rd and sd:
        if rd > sd:
            out.append(
                _issue(
                    level="warn",
                    code="request_after_start",
                    field="request_date",
                    message="Дата заявления позже даты начала отпуска.",
                    expected="request_date <= leave.start_date",
                    actual={"request_date": extract.request_date, "leave_start_date": extract.leave.start_date},
                )
            )
        delta = (sd - rd).days
        if 0 <= delta < 14:
            out.append(
                _issue(
                    level="info",
                    code="short_notice",
                    field="request_date",
                    message="До начала отпуска меньше 14 дней. По практике/графику отпусков может потребоваться согласование.",
                    law_ref="ТК РФ ст. 123 (график отпусков)",
                    extras={"days_before_start": delta},
                )
            )

    expected_days: Optional[int] = (ed - sd).days + 1 if sd and ed else None
    if extract.leave.days_count is not None:
        if extract.leave.days_count <= 0:
            out.append(
                _issue(
                    level="error",
                    code="invalid_days_count",
                    field="leave.days_count",
                    message="Количество дней должно быть больше 0.",
                    expected="> 0",
                    actual=extract.leave.days_count,
                )
            )
        if expected_days is not None and expected_days != extract.leave.days_count:
            out.append(
                _issue(
                    level="error",
                    code="days_count_mismatch",
                    field="leave.days_count",
                    message="Количество дней не совпадает с диапазоном дат (инклюзивно).",
                    expected=expected_days,
                    actual=extract.leave.days_count,
                )
            )
    elif expected_days is not None:
        out.append(
            _issue(
                level="warn",
                code="missing_days_count",
                field="leave.days_count",
                message="Лучше указать количество календарных дней, чтобы не было разночтений.",
                expected=expected_days,
                actual=extract.leave.days_count,
            )
        )
    return out


def _rule_tkrf_hints(extract: LeaveRequestExtract) -> list[ComplianceIssue]:
    out: list[ComplianceIssue] = []
    if extract.leave.leave_type == "unknown":
        out.append(
            _issue(
                level="warn",
                code="unknown_leave_type",
                field="leave.leave_type",
                message="Тип отпуска не определён. Требуется ручная классификация.",
                expected="annual_paid|unpaid|study|maternity|childcare|other",
                actual=extract.leave.leave_type,
            )
        )

    if extract.leave.leave_type == "annual_paid" and extract.leave.days_count is not None and extract.leave.days_count < 14:
        out.append(
            _issue(
                level="warn",
                code="annual_paid_part_lt14",
                field="leave.days_count",
                message="Если ежегодный отпуск делится на части, одна часть должна быть не менее 14 календарных дней.",
                law_ref="ТК РФ ст. 125",
                expected=">= 14 (для одной из частей)",
                actual=extract.leave.days_count,
            )
        )

    if extract.leave.leave_type == "unpaid":
        comment = _text(extract.leave.comment).lower()
        raw = _text(extract.raw_text).lower()
        markers = ["по семейным обстоятельствам", "по состоянию здоровья", "по уходу", "по причине"]
        if not comment and not any(m in raw for m in markers):
            out.append(
                _issue(
                    level="info",
                    code="unpaid_no_reason",
                    field="leave.comment",
                    message="Для отпуска без сохранения обычно указывают причину. Добавьте формулировку, если это необходимо.",
                )
            )

    notes = [n.lower() for n in (extract.quality.notes or []) if isinstance(n, str)]
    if any(("возможно искажение" in n) or ("требует уточнения" in n) for n in notes):
        out.append(
            _issue(
                level="info",
                code="needs_human_check",
                field="quality.notes",
                message="В распознавании есть неоднозначности. Рекомендуется ручная проверка полей.",
            )
        )

    return out


RULES: list[RuleFn] = [
    _rule_required_fields,
    _rule_date_logic,
    _rule_tkrf_hints,
]


def run_compliance_checks(extract: LeaveRequestExtract) -> tuple[list[ComplianceIssue], bool]:
    issues: list[ComplianceIssue] = []
    try:
        for rule in RULES:
            issues.extend(rule(extract))
    except Exception as e:  # noqa: BLE001
        issues.append(
            _issue(
                level="warn",
                code="compliance_internal_error",
                message=f"Внутренняя ошибка проверки соответствия: {type(e).__name__}",
            )
        )

    needs_rewrite = any(i.level == "error" for i in issues)
    return issues, needs_rewrite
