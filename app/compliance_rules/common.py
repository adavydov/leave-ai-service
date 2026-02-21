from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..schemas import ComplianceIssue, LeaveRequestExtract


@dataclass
class RuleContext:
    extract: LeaveRequestExtract
    issues: list[ComplianceIssue] = field(default_factory=list)

    def add(
        self,
        *,
        level: str,
        code: str,
        message: str,
        field: str | None = None,
        details: dict | None = None,
        rule_id: str | None = None,
        legal_basis: str | None = None,
        action_hint: str | None = None,
    ) -> None:
        self.issues.append(
            ComplianceIssue(
                level=level,
                code=code,
                field=field,
                message=message,
                details=details,
                rule_id=rule_id,
                legal_basis=legal_basis,
                action_hint=action_hint,
            )
        )


def parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def safe_text(v: str | None) -> str:
    return (v or "").strip()


RuleFunc = Callable[[RuleContext], None]
