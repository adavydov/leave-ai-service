import { preferredTheme } from './utils.js';

export const stepDefs = [
  { key: 'upload', label: 'Загрузка' },
  { key: 'analyze', label: 'Анализ' },
  { key: 'check', label: 'Проверка' },
  { key: 'fix', label: 'Исправление' },
  { key: 'export', label: 'Экспорт' },
];

export function createState() {
  return {
    phase: 'idle',
    theme: preferredTheme(),
    file: null,
    logs: [],
    result: null,
    error: null,
    requestId: null,
    abortController: null,
    fallbackUsed: false,
    editMode: false,
    editableExtract: null,
    selectedIssue: null,
    activeTab: 'issues',
    filters: { search: '', severity: 'all', category: 'all' },
    steps: stepDefs.map((s) => ({ ...s, status: 'todo', ts: null })),
  };
}

export function resetRun(state) {
  state.logs = [];
  state.result = null;
  state.error = null;
  state.fallbackUsed = false;
  state.editMode = false;
  state.editableExtract = null;
  state.selectedIssue = null;
  state.activeTab = 'issues';
  state.steps = stepDefs.map((s) => ({ ...s, status: 'todo', ts: null }));
}

export function updateStepFromLog(state, line) {
  const t = (line || '').toLowerCase();
  if (t.includes('fallback')) state.fallbackUsed = true;

  let key = null;
  if (t.includes('файл загружен')) key = 'upload';
  else if (t.includes('pdf открыт') || t.includes('pdf->png') || t.includes('vision')) key = 'analyze';
  else if (t.includes('structured.parse') || t.includes('structured.fallback') || t.includes('compliance')) key = 'check';
  else if (t.includes('готово')) key = 'export';
  if (!key) return;

  if (key === 'export') {
    state.steps.forEach((s) => { s.status = 'done'; });
    return;
  }
  state.steps.forEach((s) => {
    if (s.status === 'active') s.status = 'done';
  });
  const cur = state.steps.find((s) => s.key === key);
  if (cur) {
    cur.status = 'active';
    cur.ts = Date.now();
  }
}

export function setEditableExtract(state) {
  const ex = state.result?.extract;
  if (!ex) return;
  state.editableExtract = JSON.parse(JSON.stringify(ex));
}
