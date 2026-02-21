const fileEl = document.getElementById('file');
const btn = document.getElementById('upload');
const dlBtn = document.getElementById('download');
const outEl = document.getElementById('out') || { textContent: '' };
const statusEl = document.getElementById('status');
const stepsEl = document.getElementById('steps');
const resultBody = document.querySelector('#resultTable tbody');
const errorBox = document.getElementById('errorBox');
const issuesSummaryEl = document.getElementById('issuesSummary');
const issuesListEl = document.getElementById('issuesList');

let lastPayload = null;

function humanLeaveType(v) {
  const m = {
    annual_paid: 'Ежегодный оплачиваемый',
    unpaid: 'Без сохранения ЗП',
    study: 'Учебный',
    maternity: 'По беременности и родам',
    childcare: 'По уходу за ребёнком',
    other: 'Другой',
    unknown: 'Не определён',
  };
  return m[v] || v || '—';
}

function setStatus(ok, text) {
  statusEl.className = `status ${ok ? 'ok' : 'bad'}`;
  statusEl.textContent = text;
}

function addStep(text) {
  const li = document.createElement('li');
  li.textContent = text;
  stepsEl.appendChild(li);
}

function clearUI() {
  stepsEl.innerHTML = '';
  resultBody.innerHTML = '';
  errorBox.hidden = true;
  errorBox.textContent = '';
  issuesSummaryEl.textContent = 'Ожидание результата…';
  issuesSummaryEl.className = 'small muted';
  issuesListEl.innerHTML = '';
  dlBtn.hidden = true;
  lastPayload = null;
  statusEl.className = 'status muted';
  statusEl.textContent = 'В обработке...';
}

function row(key, val) {
  const tr = document.createElement('tr');
  const k = document.createElement('th');
  const v = document.createElement('td');
  k.textContent = key;
  v.textContent = val == null ? '—' : String(val);
  tr.appendChild(k);
  tr.appendChild(v);
  resultBody.appendChild(tr);
}

function renderIssues(issues) {
  const items = Array.isArray(issues) ? issues.slice() : [];
  const errors = items.filter((i) => i.severity === 'error');
  const warnings = items.filter((i) => i.severity === 'warn');

  if (!items.length || (!errors.length && !warnings.length)) {
    issuesSummaryEl.textContent = 'Заявление корректно';
    issuesSummaryEl.className = 'small ok';
    issuesListEl.innerHTML = '<p class="small muted">Проблем не найдено.</p>';
    return;
  }

  issuesSummaryEl.textContent = `Найдено проблем: ${errors.length + warnings.length} (критичных: ${errors.length})`;
  issuesSummaryEl.className = errors.length ? 'small bad' : 'small';

  const order = { error: 0, warn: 1, info: 2 };
  items
    .filter((i) => i.severity !== 'info')
    .sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
    .forEach((item) => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <div><b>${item.message || '—'}</b></div>
        <div class="small">Где: ${item.field || 'Общая проверка документа'}</div>
        <details class="small">
          <summary>Технические детали</summary>
          domain: ${item.domain || '—'} | code: ${item.code || '—'} | source: ${item.source || '—'}
        </details>
      `;
      issuesListEl.appendChild(card);
    });
}

function renderPayload(payload) {
  lastPayload = payload;
  dlBtn.hidden = false;

  const extract = payload?.extract;
  if (!extract) {
    errorBox.hidden = false;
    errorBox.textContent = payload?.detail || payload?.error || 'Неизвестная ошибка';
    return;
  }

  row('Статус обработки', 'Обработка завершена');
  row('Организация', extract.employer_name);
  row('Сотрудник', extract.employee?.full_name);
  row('Должность', extract.employee?.position);
  row('Руководитель', extract.manager?.full_name);
  row('Дата заявления', extract.request_date);
  row('Тип отпуска', humanLeaveType(extract.leave?.leave_type));
  row('Начало отпуска', extract.leave?.start_date);
  row('Окончание отпуска', extract.leave?.end_date);
  row('Дней', extract.leave?.days_count);
  row('Подпись', extract.signature_present ? 'Да' : (extract.signature_present === false ? 'Нет' : 'Неизвестно'));

  renderIssues(payload.issues);
}

function handleNdjsonLine(line, state) {
  const trimmed = line.trim();
  if (!trimmed) return;

  let evt;
  try {
    evt = JSON.parse(trimmed);
  } catch {
    addStep('[stream] Некорректная строка: ' + trimmed.slice(0, 160));
    return;
  }

  if (evt.type === 'step') {
    addStep(evt.message || '');
  } else if (evt.type === 'result') {
    state.finalPayload = evt.payload;
    state.ok = Boolean(evt.ok);
    setStatus(state.ok, state.ok ? 'Обработка завершена' : `Ошибка обработки (${evt.status || 'error'})`);
  } else if (evt.detail) {
    state.finalPayload = evt;
    state.ok = false;
    setStatus(false, `Ошибка обработки (${evt.status || 'error'})`);
  }
}

btn.addEventListener('click', async () => {
  const f = fileEl.files && fileEl.files[0];
  if (!f) {
    setStatus(false, 'Файл не выбран');
    errorBox.hidden = false;
    errorBox.textContent = 'Ошибка: сначала выберите PDF файл.';
    return;
  }

  clearUI();

  const fd = new FormData();
  fd.append('file', f);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 300000);

  try {
    const res = await fetch('/api/extract/stream', { method: 'POST', body: fd, signal: controller.signal });

    if (!res.body) {
      const txt = await res.text();
      throw new Error(txt || 'Пустой ответ от сервера');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    const state = { finalPayload: null, ok: false };

    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) handleNdjsonLine(line, state);
      }
      if (done) break;
    }

    if (buffer.trim()) handleNdjsonLine(buffer, state);

    if (state.finalPayload) {
      renderPayload(state.finalPayload);
      if (!state.ok) {
        errorBox.hidden = false;
        errorBox.textContent = 'Ошибка обработки: ' + (state.finalPayload.detail || state.finalPayload.error || 'неизвестная причина');
      }
    } else {
      setStatus(false, 'НЕ получен финальный результат');
      errorBox.hidden = false;
      errorBox.textContent = 'Не получен финальный результат от сервера.';
    }
  } catch (e) {
    setStatus(false, 'Ошибка запроса');
    errorBox.hidden = false;
    errorBox.textContent = e && e.name === 'AbortError'
      ? 'Запрос выполняется слишком долго (>300с).'
      : 'Ошибка запроса: ' + (e && e.message ? e.message : String(e));
  } finally {
    clearTimeout(timeoutId);
  }
});

dlBtn.addEventListener('click', () => {
  if (!lastPayload) return;
  const blob = new Blob([JSON.stringify(lastPayload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'leave-extract-result.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});
