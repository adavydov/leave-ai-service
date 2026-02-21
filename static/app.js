import { uploadPdf } from './api.js';
import { copyDiagnosticReport, copyJson, copyText, downloadCsv, downloadJson, downloadText } from './export.js';
import { render, scrollToFieldOrCategory, buildRewriteText } from './render.js';
import { createState, resetRun, setEditableExtract, updateStepFromLog } from './state.js';
import { byId, MAX_MB, nowIso, showToast, smartErrorTitle } from './utils.js';
import { runStreamSelfChecks } from './stream.js';

/** @typedef {{severity:string,category?:string,message?:string,hint?:string,field?:string,code?:string,source?:string}} Issue */
/** @typedef {{status?:'ok'|'warn'|'error',needs_rewrite?:boolean,summary?:string}} Decision */
/** @typedef {{request_id?:string, timings_ms?:Record<string,number>}} Trace */
/** @typedef {{extract?:any, issues?:Issue[], decision?:Decision, trace?:Trace}} ApiResult */

const state = createState();
let historyOpen = false;

function validateFile(file) {
  if (!file) return 'Выберите PDF файл.';
  if (!file.name.toLowerCase().endsWith('.pdf')) return 'Поддерживается только PDF.';
  if (file.size > MAX_MB * 1024 * 1024) return `Файл слишком большой (макс ${MAX_MB}MB).`;
  return null;
}

function sanitizeForHistory(payload, filename = '') {
  const ex = JSON.parse(JSON.stringify(payload?.extract || {}));
  delete ex.raw_text;
  return {
    ts: nowIso(),
    filename,
    request_id: payload?.trace?.request_id || null,
    decision: payload?.decision || null,
    timings_ms: payload?.trace?.timings_ms || null,
    extract: ex,
    issues: (payload?.issues || []).map((i) => ({ severity: i.severity, category: i.category, code: i.code, message: i.message, hint: i.hint, field: i.field, source: i.source })),
  };
}

function saveHistory(entry) {
  const key = 'leave_ai_history_v1';
  const arr = JSON.parse(localStorage.getItem(key) || '[]');
  arr.unshift(entry);
  localStorage.setItem(key, JSON.stringify(arr.slice(0, 10)));
}

function loadHistory() {
  return JSON.parse(localStorage.getItem('leave_ai_history_v1') || '[]');
}

function renderHistory() {
  const list = byId('historyList');
  const arr = loadHistory();
  if (!arr.length) {
    list.innerHTML = '<p class="muted">История пуста</p>';
    return;
  }
  list.innerHTML = arr.map((r, idx) => `
    <button type="button" data-history-idx="${idx}">
      <div><strong>${r.filename || 'Без имени'}</strong></div>
      <div class="muted">${r.ts}</div>
      <div class="muted">request_id: ${r.request_id || '—'}</div>
      <div class="muted">needs_rewrite: ${r.decision?.needs_rewrite ? 'да' : 'нет'}</div>
    </button>`).join('');
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

function updateIssueFilters() {
  state.filters.search = byId('issueSearch').value || '';
  state.filters.severity = byId('severityFilter').value || 'all';
  state.filters.category = byId('categoryFilter').value || 'all';
  render(state);
}

function setByPath(obj, path, value) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const p = parts[i];
    if (!cur[p]) cur[p] = {};
    cur = cur[p];
  }
  cur[parts[parts.length - 1]] = value;
}

function applyEdit(path, value) {
  if (!state.editableExtract) return;
  setByPath(state.editableExtract, path, path === 'leave.days_count' ? (value === '' ? null : Number(value)) : value);
  byId('rewriteText').textContent = buildRewriteText(state.editableExtract, state.result?.issues || []);
}

function openIssueInInspector(issue) {
  state.selectedIssue = issue || null;
  if (issue?.field) scrollToFieldOrCategory(issue.field, null);
  render(state);
}

function filteredIssues() {
  return (state.result?.issues || [])
    .filter((i) => state.filters.severity === 'all' || i.severity === state.filters.severity)
    .filter((i) => state.filters.category === 'all' || (i.category || 'unknown') === state.filters.category)
    .filter((i) => !state.filters.search || `${i.message || ''} ${i.hint || ''} ${i.field || ''} ${i.code || ''}`.toLowerCase().includes(state.filters.search.toLowerCase()));
}

function switchTab(name) {
  state.activeTab = name;
  render(state);
}

async function startProcessing(file) {
  const err = validateFile(file);
  state.file = file;
  byId('fileHint').textContent = err || `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)}MB`;
  if (err) return;

  resetRun(state);
  state.phase = 'uploading';
  state.steps.find((s) => s.key === 'upload').status = 'active';
  render(state);

  state.abortController = new AbortController();
  try {
    state.phase = 'processing';
    render(state);
    const result = await uploadPdf(file, {
      signal: state.abortController.signal,
      onStep: (msg) => {
        state.logs.push(msg);
        updateStepFromLog(state, msg);
        render(state);
      },
    });

    state.requestId = result.requestId;

    if (!result.payload) {
      state.phase = 'error';
      state.error = { title: 'Ошибка обработки', error: 'Не получен финальный результат от сервера.', trace: result.requestId ? { request_id: result.requestId } : undefined };
      render(state);
      return;
    }

    if (!result.ok || result.payload?.error) {
      state.phase = 'error';
      state.error = { ...result.payload, title: smartErrorTitle(result.status, (result.payload?.issues || []).map((i) => i.code)), status: result.status };
      render(state);
      return;
    }

    state.result = /** @type {ApiResult} */ (result.payload);
    state.phase = 'done';
    state.steps.forEach((s) => { s.status = 'done'; });
    setEditableExtract(state);
    state.selectedIssue = (state.result.issues || []).find((i) => i.severity === 'error') || (state.result.issues || [])[0] || null;

    const rid = state.result?.trace?.request_id;
    if (rid && state.editableExtract) {
      const c = JSON.parse(JSON.stringify(state.editableExtract));
      delete c.raw_text;
      localStorage.setItem(`leave_ai_draft_${rid}`, JSON.stringify({ expiresAt: Date.now() + 24 * 60 * 60 * 1000, extract: c }));
    }

    saveHistory(sanitizeForHistory(state.result, file.name));
    renderHistory();
    render(state);
  } catch (e) {
    state.phase = (e?.name === 'AbortError') ? 'cancelled' : 'error';
    if (e?.name === 'AbortError') {
      state.error = { title: 'Запрос отменён', error: 'Запрос отменён пользователем.' };
      showToast('Запрос отменён');
    } else {
      state.error = { title: 'Ошибка обработки', error: `Ошибка запроса: ${e?.message || String(e)}` };
    }
    render(state);
  } finally {
    state.abortController = null;
  }
}

function bindEvents() {
  byId('themeToggle').addEventListener('click', () => {
    setTheme(state.theme === 'dark' ? 'light' : 'dark');
    render(state);
  });

  byId('processBtn').addEventListener('click', () => startProcessing(byId('fileInput').files?.[0]));
  byId('retryBtn').addEventListener('click', () => startProcessing(state.file));
  byId('cancelBtn').addEventListener('click', () => state.abortController?.abort());

  const drop = byId('dropzone');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('drag'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('drag');
    const file = e.dataTransfer?.files?.[0];
    if (file) { byId('fileInput').files = e.dataTransfer.files; startProcessing(file); }
  });
  drop.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); byId('fileInput').click(); }
    if (e.key === 'Escape') byId('fileInput').value = '';
  });

  byId('copyRequestBtn').addEventListener('click', async () => {
    const rid = state.result?.trace?.request_id || state.requestId || state.error?.trace?.request_id;
    if (!rid) return;
    await navigator.clipboard.writeText(rid);
    showToast('Скопировано');
  });

  byId('copyJsonBtn').addEventListener('click', () => state.result && copyJson({ ...state.result, extract: state.editableExtract || state.result.extract }));
  byId('downloadJsonBtn').addEventListener('click', () => state.result && downloadJson({ ...state.result, extract: state.editableExtract || state.result.extract }));
  byId('downloadCsvBtn').addEventListener('click', () => state.result && downloadCsv({ ...state.result, extract: state.editableExtract || state.result.extract }));
  byId('printBtn').addEventListener('click', () => window.print());
  byId('copyDiagBtn').addEventListener('click', () => state.result && copyDiagnosticReport(state.result));

  byId('copyTextBtn').addEventListener('click', () => copyText(byId('rewriteText').textContent || ''));
  byId('downloadTextBtn').addEventListener('click', () => downloadText(byId('rewriteText').textContent || ''));
  byId('copyTextQuickBtn').addEventListener('click', () => copyText(byId('rewriteText').textContent || ''));
  byId('goToIssuesBtn').addEventListener('click', () => switchTab('issues'));

  byId('issueSearch').addEventListener('input', updateIssueFilters);
  byId('severityFilter').addEventListener('change', updateIssueFilters);
  byId('categoryFilter').addEventListener('change', updateIssueFilters);

  byId('issuesExplorer').addEventListener('click', (e) => {
    const btnField = e.target.closest('.linkToField');
    if (btnField) {
      const field = btnField.getAttribute('data-field');
      scrollToFieldOrCategory(field, null);
      const issue = (state.result?.issues || []).find((i) => i.field === field);
      if (issue) openIssueInInspector(issue);
      return;
    }

    const btnCat = e.target.closest('.linkToCategory');
    if (btnCat) {
      const cat = btnCat.getAttribute('data-category');
      scrollToFieldOrCategory(null, cat);
      return;
    }

    const selectBtn = e.target.closest('.selectIssueBtn');
    if (selectBtn) {
      const category = selectBtn.getAttribute('data-category');
      const idx = Number(selectBtn.getAttribute('data-issue-index'));
      const list = filteredIssues().filter((i) => (i.category || 'unknown') === category);
      openIssueInInspector(list[idx] || null);
    }
  });

  byId('editToggle').addEventListener('change', (e) => {
    state.editMode = Boolean(e.target.checked);
    if (state.editMode && !state.editableExtract) setEditableExtract(state);
    render(state);
  });

  byId('extractFormWrap').addEventListener('input', (e) => {
    const path = e.target.getAttribute('data-edit');
    if (!path) return;
    applyEdit(path, e.target.value);
    render(state);
  });

  byId('applyIssueBtn').addEventListener('click', () => {
    if (!state.selectedIssue?.field) return;
    const val = byId('inspectorValue')?.value;
    if (val == null) return;
    applyEdit(state.selectedIssue.field, val);
    showToast('Изменение применено');
    render(state);
  });

  byId('nextIssueBtn').addEventListener('click', () => {
    const list = filteredIssues();
    if (!list.length) return;
    const cur = list.findIndex((i) => i === state.selectedIssue);
    openIssueInInspector(list[(cur + 1 + list.length) % list.length]);
  });

  byId('markFixedBtn').addEventListener('click', () => {
    if (!state.selectedIssue || !state.result?.issues) return;
    state.result.issues = state.result.issues.filter((i) => i !== state.selectedIssue);
    state.selectedIssue = state.result.issues[0] || null;
    showToast('Отмечено как исправлено');
    render(state);
  });

  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => switchTab(tab.dataset.tab)));

  byId('historyToggle').addEventListener('click', () => {
    historyOpen = !historyOpen;
    byId('historyDrawer').classList.toggle('hidden', !historyOpen);
    renderHistory();
  });
  byId('clearHistoryBtn').addEventListener('click', () => {
    localStorage.removeItem('leave_ai_history_v1');
    renderHistory();
  });
  byId('historyList').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-history-idx]');
    if (!btn) return;
    const idx = Number(btn.getAttribute('data-history-idx'));
    const item = loadHistory()[idx];
    if (!item) return;
    state.result = { extract: item.extract, issues: item.issues, decision: item.decision, trace: { request_id: item.request_id, timings_ms: item.timings_ms } };
    state.phase = 'done';
    setEditableExtract(state);
    state.selectedIssue = (state.result.issues || [])[0] || null;
    render(state);
    showToast('Результат загружен из истории');
  });

  byId('logToggle').addEventListener('click', () => byId('logBody').classList.toggle('hidden'));

  byId('helpToggle').addEventListener('click', () => byId('helpDialog').showModal());
  byId('closeHelpBtn').addEventListener('click', () => byId('helpDialog').close());
}

function init() {
  setTheme(state.theme);
  runStreamSelfChecks();
  bindEvents();
  renderHistory();
  render(state);
}

init();
