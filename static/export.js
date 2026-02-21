import { showToast } from './utils.js';

export async function copyJson(payload) {
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  showToast('Скопировано');
}

export function downloadJson(payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'leave-ai-result.json'; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  showToast('Скачивание начато');
}

export function downloadCsv(payload) {
  const ex = payload?.extract || {};
  const issues = payload?.issues || [];
  const lines = ['section,key,value'];
  const fields = {
    employer_name: ex.employer_name,
    employee_full_name: ex.employee?.full_name,
    employee_position: ex.employee?.position,
    manager_full_name: ex.manager?.full_name,
    request_date: ex.request_date,
    leave_type: ex.leave?.leave_type,
    start_date: ex.leave?.start_date,
    end_date: ex.leave?.end_date,
    days_count: ex.leave?.days_count,
  };
  Object.entries(fields).forEach(([k,v]) => lines.push(`extract,${k},"${String(v ?? '').replaceAll('"','""')}"`));
  issues.forEach((i,idx) => lines.push(`issues_${idx},${i.code || ''},"${String(i.message || '').replaceAll('"','""')}"`));
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'leave-ai-result.csv'; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  showToast('Скачивание начато');
}

export async function copyText(txt) {
  await navigator.clipboard.writeText(txt || '');
  showToast('Скопировано');
}

export function downloadText(txt) {
  const blob = new Blob([txt || ''], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'leave-statement.txt'; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  showToast('Скачивание начато');
}

export async function copyDiagnosticReport(payload) {
  const issues = payload?.issues || [];
  const report = {
    request_id: payload?.trace?.request_id,
    timings_ms: payload?.trace?.timings_ms,
    decision: payload?.decision,
    issue_counts: {
      error: issues.filter((i) => i.severity === 'error').length,
      warn: issues.filter((i) => i.severity === 'warn').length,
      info: issues.filter((i) => i.severity === 'info').length,
    },
    issue_codes: issues.map((i) => i.code).filter(Boolean),
  };
  await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
  showToast('Скопировано');
}
