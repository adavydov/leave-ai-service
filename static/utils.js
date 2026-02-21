/** @typedef {'idle'|'uploading'|'processing'|'done'|'error'|'cancelled'} Phase */

export const MAX_MB = 15;

export function byId(id) { return document.getElementById(id); }
export function escapeHtml(s) { return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }
export function fieldToId(field='') { return `field-${String(field).replaceAll('.', '__')}`; }

export function showToast(message) {
  const t = byId('toast');
  t.textContent = message;
  t.classList.remove('hidden');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => t.classList.add('hidden'), 1400);
}

export function nowIso() { return new Date().toISOString(); }

export function severityRank(v) {
  if (v === 'error') return 0;
  if (v === 'warn') return 1;
  return 2;
}

export function smartErrorTitle(status, issueCodes = []) {
  const codes = new Set(issueCodes);
  if (status === 413 || codes.has('pdf_too_large')) return 'Слишком большой файл';
  if (status === 429 || codes.has('anthropic_rate_limited')) return 'Слишком много запросов';
  if (status === 504 || codes.has('anthropic_timeout')) return 'Время ожидания истекло';
  if (status >= 500) return 'Сервис временно недоступен';
  return 'Ошибка обработки';
}

export function preferredTheme() {
  const saved = localStorage.getItem('theme');
  if (saved) return saved;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
