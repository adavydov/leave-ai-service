from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["error", "warn", "info"]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: Severity
    code: str
