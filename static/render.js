import { byId, escapeHtml, fieldToId, severityRank, smartErrorTitle } from './utils.js';

export function humanLeaveType(v) {
  const m = { annual_paid:'Ежегодный оплачиваемый', unpaid:'Без сохранения ЗП', study:'Учебный', maternity:'По беременности и родам', childcare:'По уходу за ребёнком', other:'Другой', unknown:'Не определён' };
  return m[v] || v || '—';
}

export function buildRewriteText(extract, issues = []) {
  const ex = extract || {};
  const employee = ex.employee || {};
  const manager = ex.manager || {};
  const leave = ex.leave || {};
  const p = {
    managerName: manager.full_name || '[УКАЖИТЕ ФИО РУКОВОДИТЕЛЯ]',
    employer: ex.employer_name || '[УКАЖИТЕ ОРГАНИЗАЦИЮ]',
    employeeName: employee.full_name || '[УКАЖИТЕ ФИО СОТРУДНИКА]',
    position: employee.position || '[УКАЖИТЕ ДОЛЖНОСТЬ]',
    start: leave.start_date || '[УКАЖИТЕ ДАТУ НАЧАЛА]',
    end: leave.end_date || '[УКАЖИТЕ ДАТУ ОКОНЧАНИЯ]',
    days: leave.days_count ?? '[УКАЖИТЕ КОЛИЧЕСТВО ДНЕЙ]',
    requestDate: ex.request_date || '[УКАЖИТЕ ДАТУ ЗАЯВЛЕНИЯ]',
  };
  const dateWarn = issues.some((i) => i.category === 'dates' && i.severity !== 'info');
  return [
    `Руководителю ${p.employer}`,
    `${p.managerName}`,
    `от ${p.employeeName}`,
    `${p.position}`,
    '', 'Заявление', '',
    `Прошу предоставить мне ${humanLeaveType(leave.leave_type).toLowerCase()} с ${p.start} по ${p.end} на ${p.days} календарных дней.`,
    '', `${p.requestDate}    __________________ /${p.employeeName}/`,
    dateWarn ? '⚠ Проверьте даты перед подачей заявления.' : '',
  ].filter(Boolean).join('\n');
}

function row(label, value, field) {
  return `<tr id="${fieldToId(field)}" data-field="${escapeHtml(field)}"><th>${escapeHtml(label)}</th><td>${escapeHtml(String(value ?? '—'))}</td></tr>`;
}

function issueList(state) {
  return (state.result?.issues || [])
    .filter((i) => i.severity !== 'info')
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
}

function renderIssues(state) {
  const root = byId('issuesExplorer');
  const raw = state.result?.issues || [];
  const critical = raw.filter((i) => i.severity === 'error').length;
  const nonCritical = raw.filter((i) => i.severity === 'warn').length;
  byId('issuesSummary').textContent = `Критичных: ${critical} • Некритичных: ${nonCritical}`;

  const filtered = issueList(state);
  if (!filtered.length) {
    root.innerHTML = '<p class="muted">Проблем не найдено. Файл можно отправлять.</p>';
    return;
  }

  root.innerHTML = filtered.map((it) => `
    <article class="issue-card sev-${escapeHtml(it.severity || 'info')}">
      <div><strong>Проблема:</strong> ${escapeHtml(it.message || '—')}</div>
      <div class="issue-meta"><strong>Где в документе:</strong> ${escapeHtml(it.field || 'Общая проверка документа')}</div>
      <div class="issue-meta"><strong>Что сделать:</strong> ${escapeHtml(it.hint || 'Проверьте данные в заявлении.')}</div>
      <details class="issue-meta"><summary>Технические детали</summary><span class="muted">code: ${escapeHtml(it.code || '—')} | category: ${escapeHtml(it.category || 'unknown')} | source: ${escapeHtml(it.source || '—')}</span></details>
    </article>`).join('');
}

function renderDecision(state) {
  const banner = byId('decisionBanner');
  if (state.phase === 'uploading' || state.phase === 'processing') {
    byId('decisionTitle').textContent = 'Проверяем документ…';
    byId('decisionReason').textContent = 'Подождите, анализ обычно занимает несколько секунд.';
    banner.className = 'card decision warn';
    return;
  }

  if (state.phase === 'error') {
    byId('decisionTitle').textContent = 'Не удалось проверить файл';
    byId('decisionReason').textContent = state.error?.detail || state.error?.error || 'Попробуйте отправить файл ещё раз.';
    banner.className = 'card decision error';
    return;
  }

  const decision = state.result?.decision;
  if (!decision) {
    byId('decisionTitle').textContent = '2) Статус проверки';
    byId('decisionReason').textContent = 'Загрузите PDF, чтобы начать проверку.';
    banner.className = 'card decision';
    return;
  }

  const hasErrors = decision.needs_rewrite || decision.status === 'error' || (state.result?.issues || []).some((i) => i.severity === 'error');
  byId('decisionTitle').textContent = hasErrors ? 'Нужно исправить' : 'Можно отправлять';
  byId('decisionReason').textContent = hasErrors
    ? 'Ниже список того, что нужно поправить в файле.'
    : 'Критичных ошибок нет, заявление готово к отправке.';
  banner.className = `card decision ${hasErrors ? 'error' : 'ok'}`;
}

function renderDataAndText(state) {
  const ex = state.editableExtract || state.result?.extract;
  if (!ex) {
    byId('resultTable').innerHTML = '';
    byId('rewriteText').textContent = '';
    return;
  }
  byId('resultTable').innerHTML = [
    row('Организация', ex.employer_name, 'employer_name'),
    row('Сотрудник', ex.employee?.full_name, 'employee.full_name'),
    row('Должность', ex.employee?.position, 'employee.position'),
    row('Руководитель', ex.manager?.full_name, 'manager.full_name'),
    row('Дата заявления', ex.request_date, 'request_date'),
    row('Тип отпуска', ex.leave?.leave_type, 'leave.leave_type'),
    row('Начало', ex.leave?.start_date, 'leave.start_date'),
    row('Окончание', ex.leave?.end_date, 'leave.end_date'),
    row('Дней', ex.leave?.days_count, 'leave.days_count'),
    row('Подпись', ex.signature_present, 'signature_present'),
  ].join('');

  byId('rewriteText').textContent = buildRewriteText(ex, state.result?.issues || []);

  const raw = state.result?.extract?.raw_text;
  byId('rawSection').classList.toggle('hidden', !raw);
  byId('rawText').textContent = raw || '';

  byId('requestId').textContent = state.result?.trace?.request_id || state.requestId || state.error?.trace?.request_id || '—';
  byId('timings').textContent = state.result?.trace?.timings_ms ? JSON.stringify(state.result.trace.timings_ms) : '—';
}

function renderEditForm(state) {
  const wrap = byId('extractFormWrap');
  const table = byId('resultTable').closest('table');
  const ex = state.editableExtract;
  if (!state.editMode || !ex) {
    wrap.classList.add('hidden');
    table.classList.remove('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  table.classList.add('hidden');
  wrap.innerHTML = `
    <div class="grid summary">
      <label>ФИО<input data-edit="employee.full_name" value="${escapeHtml(ex.employee?.full_name || '')}" /></label>
      <label>Должность<input data-edit="employee.position" value="${escapeHtml(ex.employee?.position || '')}" /></label>
      <label>Организация<input data-edit="employer_name" value="${escapeHtml(ex.employer_name || '')}" /></label>
      <label>Руководитель<input data-edit="manager.full_name" value="${escapeHtml(ex.manager?.full_name || '')}" /></label>
      <label>Дата заявления<input data-edit="request_date" value="${escapeHtml(ex.request_date || '')}" /></label>
      <label>Начало<input data-edit="leave.start_date" value="${escapeHtml(ex.leave?.start_date || '')}" /></label>
      <label>Окончание<input data-edit="leave.end_date" value="${escapeHtml(ex.leave?.end_date || '')}" /></label>
      <label>Дней<input data-edit="leave.days_count" value="${escapeHtml(String(ex.leave?.days_count ?? ''))}" /></label>
      <label>Тип отпуска
        <select data-edit="leave.leave_type">
          ${['annual_paid','unpaid','study','maternity','childcare','other','unknown'].map((v) => `<option value="${v}" ${ex.leave?.leave_type===v?'selected':''}>${v} (${humanLeaveType(v)})</option>`).join('')}
        </select>
      </label>
    </div>`;
}

export function render(state) {
  const statusEl = byId('headerBadge');
  if (state.phase === 'uploading' || state.phase === 'processing') {
    statusEl.textContent = 'Статус: проверяем';
    statusEl.className = 'badge warn';
  } else if (state.phase === 'error') {
    statusEl.textContent = 'Статус: ошибка';
    statusEl.className = 'badge error';
  } else if (state.phase === 'done' && (state.result?.decision?.needs_rewrite || state.result?.decision?.status === 'error')) {
    statusEl.textContent = 'Статус: нужно исправить';
    statusEl.className = 'badge error';
  } else if (state.phase === 'done') {
    statusEl.textContent = 'Статус: можно отправлять';
    statusEl.className = 'badge ok';
  } else {
    statusEl.textContent = 'Статус: ожидание';
    statusEl.className = 'badge';
  }

  const done = state.steps.filter((s) => s.status === 'done').length;
  const active = state.steps.some((s) => s.status === 'active') ? 1 : 0;
  const progress = Math.round(((done + active * 0.5) / state.steps.length) * 100);
  byId('progressBar').style.width = `${progress}%`;
  byId('progress').setAttribute('aria-valuenow', String(progress));
  byId('logs').innerHTML = state.logs.map((x) => `<li>${escapeHtml(x)}</li>`).join('');

  renderDecision(state);
  renderIssues(state);
  renderDataAndText(state);
  renderEditForm(state);

  const isError = state.phase === 'error';
  byId('errorCard').classList.toggle('hidden', !isError);
  byId('retryBtn').classList.toggle('hidden', !isError);
  byId('cancelBtn').classList.toggle('hidden', !(state.phase === 'uploading' || state.phase === 'processing'));

  byId('quickDownloadTextBtn').disabled = !state.result;
  byId('quickDownloadJsonBtn').disabled = !state.result;

  if (isError) {
    const title = state.error?.title || smartErrorTitle(state.error?.status || 0, (state.error?.issues || []).map((i) => i.code));
    byId('errorTitle').textContent = title;
    byId('errorMessage').textContent = state.error?.detail || state.error?.error || title;
    byId('errorDetails').textContent = JSON.stringify(state.error || {}, null, 2);
  }
}

export function scrollToFieldOrCategory(field, category) {
  let node = null;
  if (field) node = document.getElementById(fieldToId(field));
  if (!node && category) node = document.querySelector('#issuesExplorer .issue-card');
  if (!node) return;
  node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  node.classList.add('field-highlight');
  setTimeout(() => node.classList.remove('field-highlight'), 1500);
}
