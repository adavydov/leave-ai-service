from __future__ import annotations

from .common import RuleContext, parse_iso, safe_text


def required_fields_rule(ctx: RuleContext) -> None:
    ex = ctx.extract
    if not safe_text(ex.employer_name):
        ctx.add(
            level="error",
            code="missing_employer_name",
            field="employer_name",
            message="Не указана организация работодателя.",
            rule_id="DOC-REQ-001",
            legal_basis="ТК РФ (практика документооборота): реквизиты заявления должны однозначно идентифицировать работодателя.",
            action_hint="Добавьте полное наименование организации в шапке заявления.",
        )
    if not safe_text(ex.employee.full_name):
        ctx.add(
            level="error",
            code="missing_employee_name",
            field="employee.full_name",
            message="Не указано ФИО сотрудника.",
            rule_id="DOC-REQ-002",
            legal_basis="ТК РФ: заявление должно позволять идентифицировать работника.",
            action_hint="Укажите полные ФИО сотрудника без сокращений.",
        )
    if not safe_text(ex.manager.full_name):
        ctx.add(
            level="warn",
            code="missing_manager_name",
            field="manager.full_name",
            message="Не указано ФИО руководителя/адресата заявления.",
            rule_id="DOC-REQ-003",
            legal_basis="Локальные практики кадрового делопроизводства: адресат заявления должен быть определён.",
            action_hint="Добавьте ФИО адресата (руководителя/уполномоченного лица).",
        )
    if not safe_text(ex.request_date):
        ctx.add(
            level="error",
            code="missing_request_date",
            field="request_date",
            message="Не указана дата заявления.",
            rule_id="DOC-REQ-004",
            legal_basis="ТК РФ и кадровая практика: дата заявления нужна для фиксации волеизъявления.",
            action_hint="Проставьте дату составления заявления в формате YYYY-MM-DD.",
        )
    if not safe_text(ex.leave.start_date):
        ctx.add(
            level="error",
            code="missing_leave_start_date",
            field="leave.start_date",
            message="Не указана дата начала отпуска.",
            rule_id="DOC-REQ-005",
            legal_basis="ТК РФ: период отпуска должен быть определён датами.",
            action_hint="Укажите дату начала отпуска.",
        )
    if not safe_text(ex.leave.end_date):
        ctx.add(
            level="error",
            code="missing_leave_end_date",
            field="leave.end_date",
            message="Не указана дата окончания отпуска.",
            rule_id="DOC-REQ-006",
            legal_basis="ТК РФ: период отпуска должен быть определён датами.",
            action_hint="Укажите дату окончания отпуска.",
        )


def signature_rule(ctx: RuleContext) -> None:
    ex = ctx.extract
    if ex.signature_present is False:
        ctx.add(
            level="error",
            code="missing_signature",
            field="signature_present",
            message="В заявлении не обнаружена подпись сотрудника.",
            rule_id="DOC-SIGN-001",
            legal_basis="Кадровая практика: заявление работника подписывается заявителем.",
            action_hint="Подпишите заявление и загрузите PDF повторно.",
        )
    if ex.signature_present is True and ex.signature_confidence is not None and ex.signature_confidence < 0.6:
        ctx.add(
            level="warn",
            code="low_signature_confidence",
            field="signature_confidence",
            message="Подпись найдена, но уверенность низкая. Желательна ручная проверка.",
            rule_id="OCR-SIGN-002",
            legal_basis="Техническая проверка OCR/vision: низкая уверенность требует ручного подтверждения.",
            action_hint="Проверьте визуально наличие подписи в скане.",
        )


def dates_and_counts_rule(ctx: RuleContext) -> None:
    ex = ctx.extract
    sd = parse_iso(ex.leave.start_date)
    ed = parse_iso(ex.leave.end_date)
    rd = parse_iso(ex.request_date)

    if sd and ed and sd > ed:
        ctx.add(
            level="error",
            code="invalid_date_range",
            field="leave",
            message="Дата начала отпуска позже даты окончания.",
            rule_id="DATE-001",
            legal_basis="ТК РФ: период отпуска не может иметь обратный диапазон дат.",
            action_hint="Исправьте даты начала и окончания отпуска.",
        )

    if rd and sd:
        if rd > sd:
            ctx.add(
                level="warn",
                code="request_after_start",
                field="request_date",
                message="Дата заявления позже даты начала отпуска.",
                rule_id="DATE-002",
                legal_basis="Кадровая практика: заявление обычно подаётся до начала отпуска.",
                action_hint="Проверьте дату заявления и дату начала отпуска.",
            )
        delta = (sd - rd).days
        if 0 <= delta < 14:
            ctx.add(
                level="info",
                code="short_notice",
                field="request_date",
                message="До начала отпуска меньше 14 дней. По практике/графику отпусков может потребоваться согласование.",
                details={"days_before_start": delta},
                rule_id="DATE-003",
                legal_basis="Ст. 123 ТК РФ (график отпусков) и локальные процедуры согласования.",
                action_hint="Проверьте необходимость дополнительного согласования с работодателем.",
            )

    expected_days = None
    if sd and ed:
        expected_days = (ed - sd).days + 1

    if ex.leave.days_count is not None:
        if ex.leave.days_count <= 0:
            ctx.add(
                level="error",
                code="invalid_days_count",
                field="leave.days_count",
                message="Количество дней должно быть больше 0.",
                rule_id="COUNT-001",
                legal_basis="Логическая проверка кадрового документа: длительность отпуска должна быть положительной.",
                action_hint="Укажите корректное количество календарных дней.",
            )
        if expected_days is not None and expected_days != ex.leave.days_count:
            ctx.add(
                level="error",
                code="days_count_mismatch",
                field="leave.days_count",
                message="Количество дней не совпадает с диапазоном дат (инклюзивно).",
                details={"expected": expected_days, "actual": ex.leave.days_count},
                rule_id="COUNT-002",
                legal_basis="Период отпуска и число календарных дней должны быть согласованы.",
                action_hint="Скорректируйте даты или количество дней, чтобы значения совпали.",
            )
    elif expected_days is not None:
        ctx.add(
            level="warn",
            code="missing_days_count",
            field="leave.days_count",
            message="Лучше указать количество календарных дней, чтобы не было разночтений.",
            details={"expected": expected_days},
            rule_id="COUNT-003",
            legal_basis="Кадровая практика: явное указание длительности снижает риск ошибок в приказе.",
            action_hint="Добавьте количество календарных дней отпуска.",
        )


def leave_type_hints_rule(ctx: RuleContext) -> None:
    ex = ctx.extract
    if ex.leave.leave_type == "annual_paid" and ex.leave.days_count is not None and ex.leave.days_count < 14:
        ctx.add(
            level="warn",
            code="annual_paid_part_lt14",
            field="leave.days_count",
            message="Если ежегодный отпуск делится на части, одна часть должна быть не менее 14 календарных дней. Убедитесь, что в другом периоде есть 14+ дней.",
            rule_id="LAW-122-001",
            legal_basis="Ст. 125 ТК РФ: одна из частей ежегодного оплачиваемого отпуска — не менее 14 календарных дней.",
            action_hint="Проверьте суммарное планирование частей отпуска и подтвердите наличие части 14+ дней.",
        )

    if ex.leave.leave_type == "unpaid":
        comment = safe_text(ex.leave.comment).lower()
        raw = safe_text(ex.raw_text).lower()
        markers = ["по семейным обстоятельствам", "по состоянию здоровья", "по уходу", "по причине"]
        if not comment and not any(m in raw for m in markers):
            ctx.add(
                level="info",
                code="unpaid_no_reason",
                field="leave.comment",
                message="Для отпуска без сохранения обычно указывают причину. Добавьте формулировку, если это необходимо.",
                rule_id="LAW-128-001",
                legal_basis="Ст. 128 ТК РФ: отпуск без сохранения предоставляется по заявлению работника, как правило с указанием причины.",
                action_hint="Добавьте краткое основание (например, семейные обстоятельства).",
            )


def quality_hints_rule(ctx: RuleContext) -> None:
    notes = [n.lower() for n in (ctx.extract.quality.notes or []) if isinstance(n, str)]
    if any(("возможно искажение" in n) or ("требует уточнения" in n) for n in notes):
        ctx.add(
            level="info",
            code="needs_human_check",
            field="quality.notes",
            message="В распознавании есть неоднозначности. Рекомендуется ручная проверка полей.",
            rule_id="OCR-QUALITY-001",
            legal_basis="Техническое ограничение OCR/LLM: неоднозначный распознанный текст требует ручной валидации.",
            action_hint="Сверьте извлечённые поля с исходным PDF вручную.",
        )
