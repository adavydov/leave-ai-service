import { byId, escapeHtml, fieldToId, severityRank, smartErrorTitle } from './utils.js';

const categoryOrder = ['document','dates','counts','signature','law_hints','quality','system','upstream','unknown'];

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
  const raw = state.result?.issues || [];
  const filtered = raw
    .filter((i) => state.filters.severity === 'all' || i.severity === state.filters.severity)
    .filter((i) => state.filters.category === 'all' || (i.category || 'unknown') === state.filters.category)
    .filter((i) => !state.filters.search || `${i.message || ''} ${i.hint || ''} ${i.field || ''} ${i.code || ''}`.toLowerCase().includes(state.filters.search.toLowerCase()))
    .sort((a,b) => severityRank(a.severity) - severityRank(b.severity) || String(a.category||'').localeCompare(String(b.category||'')));
  return filtered;
}

function renderIssues(state) {
  const root = byId('issuesExplorer');
  const raw = state.result?.issues || [];
  byId('issuesSummary').textContent = `Ошибок: ${raw.filter((i) => i.severity==='error').length} • Предупреждений: ${raw.filter((i) => i.severity==='warn').length} • Инфо: ${raw.filter((i) => i.severity==='info').length}`;

  const filtered = issueList(state);
  if (!filtered.length) {
    root.innerHTML = '<p class="muted">Ошибок не найдено</p>';
    return;
  }

  const grouped = {};
  filtered.forEach((i) => { const c = i.category || 'unknown'; (grouped[c] ||= []).push(i); });
  const cats = [...categoryOrder.filter((c) => grouped[c]), ...Object.keys(grouped).filter((c) => !categoryOrder.includes(c))];
  root.innerHTML = cats.map((cat) => `
    <details class="issue-group" open>
      <summary><strong>${escapeHtml(cat)}</strong> (${grouped[cat].length})</summary>
      ${grouped[cat].map((it, idx) => `
        <article class="issue-card sev-${escapeHtml(it.severity || 'info')} ${state.selectedIssue === it ? 'is-selected' : ''}">
          <div><span class="badge ${escapeHtml(it.severity || 'info')}">${escapeHtml(it.severity || 'info')}</span> ${escapeHtml(it.message || '')}</div>
          ${it.hint ? `<div class="muted">Как исправить: ${escapeHtml(it.hint)}</div>` : ''}
          <div class="row">
            <button type="button" class="selectIssueBtn" data-issue-index="${idx}" data-category="${escapeHtml(cat)}">Выбрать</button>
            ${it.field ? `<button type="button" class="linkToField" data-field="${escapeHtml(it.field)}">Где: ${escapeHtml(it.field)}</button>` : `<button type="button" class="linkToCategory" data-category="${escapeHtml(cat)}">Перейти к секции</button>`}
          </div>
          <details><summary>Подробнее</summary><div class="muted">code: ${escapeHtml(it.code || '—')} | source: ${escapeHtml(it.source || '—')}</div></details>
        </article>`).join('')}
    </details>`).join('');

  root.dataset.filteredIssues = JSON.stringify(filtered);
}

function renderDecision(state) {
  const decision = state.result?.decision;
  const topIssue = (state.result?.issues || []).find((i) => i.severity === 'error') || (state.result?.issues || [])[0];
  const banner = byId('decisionBanner');
  if (!decision) {
    byId('decisionTitle').textContent = state.phase === 'error' ? (state.error?.title || 'Ошибка') : 'Ожидание проверки';
    byId('decisionReason').textContent = state.phase === 'error' ? (state.error?.detail || state.error?.error || '') : 'Загрузите PDF, чтобы получить решение.';
    banner.className = 'decision';
    return;
  }
  const isError = decision.needs_rewrite || decision.status === 'error';
  byId('decisionTitle').textContent = isError ? '❌ Нужно переписать' : (decision.status === 'warn' ? '⚠ Нужна проверка' : '✅ Можно отправлять');
  byId('decisionReason').textContent = topIssue?.message || decision.summary || '';
  banner.className = `decision ${isError ? 'error' : decision.status === 'warn' ? 'warn' : 'ok'}`;
}

function renderTabs(state) {
  document.querySelectorAll('.tab').forEach((t) => {
    const active = t.dataset.tab === state.activeTab;
    t.classList.toggle('is-active', active);
  });
  ['issues','data','text','export'].forEach((name) => {
    byId(`tab-${name}`).classList.toggle('hidden', state.activeTab !== name);
  });
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

function renderInspector(state) {
  const empty = byId('inspectorEmpty');
  const body = byId('inspectorBody');
  const issue = state.selectedIssue;
  if (!issue) {
    empty.classList.remove('hidden');
    body.classList.add('hidden');
    byId('inspectorEditor').innerHTML = '';
    return;
  }
  empty.classList.add('hidden');
  body.classList.remove('hidden');
  byId('inspectorMessage').textContent = issue.message || '—';
  byId('inspectorHint').textContent = issue.hint || 'Проверьте вручную';
  byId('inspectorField').textContent = issue.field || '—';

  if (issue.field) {
    const val = getByPath(state.editableExtract || state.result?.extract || {}, issue.field);
    byId('inspectorEditor').innerHTML = `<label>Изменить значение <input id="inspectorValue" value="${escapeHtml(String(val ?? ''))}" /></label>`;
  } else {
    byId('inspectorEditor').innerHTML = '<p class="muted">Для этой ошибки нет прямого поля. Проверьте данные во вкладке «Данные».</p>';
  }
}

function getByPath(obj, path) {
  return String(path || '').split('.').reduce((acc, p) => (acc ? acc[p] : undefined), obj);
}

export function render(state) {
  const status = state.phase === 'done' ? (state.result?.decision?.status || 'ok') : state.phase === 'error' ? 'error' : state.phase;
  byId('headerBadge').textContent = String(status).toUpperCase();
  byId('headerBadge').className = `badge ${status === 'error' ? 'error' : status === 'warn' ? 'warn' : status === 'ok' ? 'ok' : ''}`;

  const done = state.steps.filter((s) => s.status === 'done').length;
  const active = state.steps.some((s) => s.status === 'active') ? 1 : 0;
  const progress = Math.round(((done + active * 0.5) / state.steps.length) * 100);
  byId('progressBar').style.width = `${progress}%`;
  byId('progress').setAttribute('aria-valuenow', String(progress));

  requestAnimationFrame(() => {
    byId('stepper').innerHTML = state.steps.map((s) => `<div class="step ${s.status === 'done' ? 'done' : s.status === 'active' ? 'active' : ''}">${escapeHtml(s.label + (s.key === 'check' && state.fallbackUsed ? ' (fallback)' : ''))}</div>`).join('');
  });

  byId('logs').innerHTML = state.logs.map((x) => `<li>${escapeHtml(x)}</li>`).join('');

  renderDecision(state);
  renderTabs(state);
  renderIssues(state);
  renderDataAndText(state);
  renderEditForm(state);
  renderInspector(state);

  const isError = state.phase === 'error';
  byId('errorCard').classList.toggle('hidden', !isError);
  byId('retryBtn').classList.toggle('hidden', !isError);
  byId('cancelBtn').classList.toggle('hidden', !(state.phase === 'uploading' || state.phase === 'processing'));

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
  if (!node && category) node = document.querySelector('#issuesExplorer details');
  if (!node) return;
  node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  node.classList.add('field-highlight');
  setTimeout(() => node.classList.remove('field-highlight'), 1500);
}
