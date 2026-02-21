from __future__ import annotations

from typing import Iterable, Optional

from .schemas import ComplianceIssue, Decision, Issue, Trace, ValidationIssue


_VALIDATION_CATEGORY_MAP = {
    'missing': 'document',
    'date': 'dates',
    'days': 'counts',
    'signature': 'signature',
    'confidence': 'quality',
}

_COMPLIANCE_CATEGORY_MAP = {
    'date': 'dates',
    'days': 'counts',
    'signature': 'signature',
    'employer': 'document',
    'employee': 'document',
    'manager': 'document',
    'law': 'law_hints',
    'quality': 'quality',
}



def _guess_category(code: str, mapping: dict[str, str]) -> str:
    low = (code or '').lower()
    for key, val in mapping.items():
        if key in low:
            return val
    return 'validation'



def from_validation(items: Iterable[ValidationIssue]) -> list[Issue]:
    out: list[Issue] = []
    for it in items:
        cat = _guess_category(it.code, _VALIDATION_CATEGORY_MAP)
        out.append(
            Issue(
                severity=it.level,
                domain='extraction',
                category=cat,
                code=it.code,
                message=it.message,
                hint='Проверьте распознанные поля в заявлении и при необходимости поправьте документ.' if it.level != 'info' else None,
            )
        )
    return out



def from_compliance(items: Iterable[ComplianceIssue]) -> list[Issue]:
    out: list[Issue] = []
    for it in items:
        cat = _guess_category(it.code, _COMPLIANCE_CATEGORY_MAP)
        hint = None
        if it.level == 'error':
            hint = 'Исправьте заявление и загрузите PDF повторно.'
        elif it.level == 'warn':
            hint = 'Проверьте поле и при необходимости уточните формулировку.'
        out.append(
            Issue(
                severity=it.level,
                domain='compliance',
                category=cat,
                code=it.code,
                field=it.field,
                message=it.message,
                hint=hint,
                details=it.details,
            )
        )
    return out



def make_upstream_issue(*, code: str, message: str, source: Optional[str] = None, category: str = 'network', severity: str = 'error', hint: Optional[str] = None) -> Issue:
    return Issue(
        severity=severity,
        domain='upstream',
        category=category,
        code=code,
        message=message,
        source=source,
        hint=hint,
    )



def build_decision(issues: list[Issue]) -> Decision:
    severe_error = any(i.severity == 'error' and i.domain in {'extraction', 'compliance', 'system'} and i.category != 'quality' for i in issues)
    warn_exists = any(i.severity == 'warn' for i in issues)
    if severe_error:
        return Decision(status='error', needs_rewrite=True, summary='Найдены критичные проблемы: заявление нужно исправить.')
    if warn_exists:
        return Decision(status='warn', needs_rewrite=False, summary='Есть замечания. Проверьте поля перед отправкой в кадровую службу.')
    if issues:
        return Decision(status='ok', needs_rewrite=False, summary='Извлечение завершено. Есть информационные подсказки.')
    return Decision(status='ok', needs_rewrite=False, summary='Ошибок не найдено.')



def build_trace(request_id: str, timings_ms: dict[str, int], upstream_request_ids: dict[str, str]) -> Trace:
    return Trace(request_id=request_id, timings_ms=timings_ms, upstream_request_ids=upstream_request_ids)
