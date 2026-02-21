from __future__ import annotations

from .compliance_rules import run_all_rules
from .schemas import ComplianceIssue, LeaveRequestExtract


def run_compliance_checks(extract: LeaveRequestExtract) -> tuple[list[ComplianceIssue], bool]:
    """Run MVP TK-RF oriented rules and return issues + rewrite recommendation."""
    issues = run_all_rules(extract)
    needs_rewrite = any(i.level == "error" for i in issues)
    return issues, needs_rewrite
