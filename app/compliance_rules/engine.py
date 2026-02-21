from __future__ import annotations

from ..schemas import ComplianceIssue, LeaveRequestExtract
from .common import RuleContext, RuleFunc
from .rules import dates_and_counts_rule, leave_type_hints_rule, quality_hints_rule, required_fields_rule, signature_rule

RULES: tuple[RuleFunc, ...] = (
    required_fields_rule,
    signature_rule,
    dates_and_counts_rule,
    leave_type_hints_rule,
    quality_hints_rule,
)


def run_all_rules(extract: LeaveRequestExtract) -> list[ComplianceIssue]:
    ctx = RuleContext(extract=extract)
    for rule in RULES:
        try:
            rule(ctx)
        except Exception as exc:  # noqa: BLE001
            ctx.add(
                level="warn",
                code="compliance_internal_error",
                message=f"Внутренняя ошибка проверки соответствия: {type(exc).__name__}",
                rule_id="SYS-001",
                legal_basis="Техническая ошибка сервиса проверки.",
                action_hint="Повторите проверку или обратитесь к администратору сервиса.",
            )
    return ctx.issues
