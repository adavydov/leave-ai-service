const fileEl = document.getElementById('file');
const btn = document.getElementById('upload');
const dlBtn = document.getElementById('download');
// legacy compatibility: older cached scripts may expect `outEl`
const outEl = document.getElementById('out') || { textContent: '' };
const statusEl = document.getElementById('status');
const stepsEl = document.getElementById('steps');
const resultBody = document.querySelector('#resultTable tbody');
const validationBody = document.querySelector('#validationTable tbody');
const errorBox = document.getElementById('errorBox');
const complianceSummaryEl = document.getElementById('complianceSummary');
const complianceBody = document.querySelector('#complianceTable tbody');

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
  validationBody.innerHTML = '';
  errorBox.hidden = true;
  errorBox.textContent = '';
  complianceSummaryEl.textContent = 'Ожидание результата…';
  complianceSummaryEl.className = 'small muted';
  complianceBody.innerHTML = '';
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


function renderCompliance(compliance, needsRewrite) {
  complianceBody.innerHTML = '';
  const items = Array.isArray(compliance) ? compliance : [];

  if (!items.length) {
    complianceSummaryEl.textContent = 'Ошибок не найдено';
    complianceSummaryEl.className = 'small';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="5">Ошибок не найдено</td>';
    complianceBody.appendChild(tr);
    return;
  }

  const counts = { error: 0, warn: 0, info: 0 };
  for (const item of items) {
    if (counts[item.level] != null) counts[item.level] += 1;
  }

  if (needsRewrite) {
    complianceSummaryEl.textContent = `Нужно исправить заявление · error: ${counts.error}, warn: ${counts.warn}, info: ${counts.info}`;
    complianceSummaryEl.className = 'small bad';
  } else {
    complianceSummaryEl.textContent = `Критичных ошибок не найдено · error: ${counts.error}, warn: ${counts.warn}, info: ${counts.info}`;
    complianceSummaryEl.className = 'small ok';
  }

  const order = { error: 0, warn: 1, info: 2 };
  items
    .slice()
    .sort((a, b) => (order[a.level] ?? 9) - (order[b.level] ?? 9))
    .forEach((item) => {
      const tr = document.createElement('tr');
      const details = item.details || {};
      const norm = [details.rule_id, details.law_ref].filter(Boolean).join(' · ') || '—';
      const expected = details.expected == null ? '' : `ожидалось: ${JSON.stringify(details.expected)}`;
      const actual = details.actual == null ? '' : `факт: ${JSON.stringify(details.actual)}`;
      const detailsText = [expected, actual].filter(Boolean).join('\n') || '—';
      tr.innerHTML = `<td>${item.level || ''}</td><td>${item.message || ''}</td><td class="small">${item.field || '—'}</td><td class="small">${norm}</td><td class="small mono">${detailsText}</td>`;
      complianceBody.appendChild(tr);
    });
}

function renderValidation(validation) {
  validationBody.innerHTML = '';
  if (!Array.isArray(validation) || validation.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="3">Нет замечаний</td>';
    validationBody.appendChild(tr);
    return;
  }
  for (const item of validation) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${item.level || ''}</td><td>${item.code || ''}</td><td>${item.message || ''}</td>`;
    validationBody.appendChild(tr);
  }
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

  row('Статус', 'OK');
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
  row('Уверенность подписи', extract.signature_confidence);
  row('Текст заявления (raw)', extract.raw_text);

  renderValidation(payload.validation);
  renderCompliance(payload.compliance, payload.needs_rewrite);
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
    setStatus(state.ok, state.ok ? 'OK' : `НЕ ОК (${evt.status || 'error'})`);
  } else if (evt.detail) {
    state.finalPayload = evt;
    state.ok = false;
    setStatus(false, `НЕ ОК (${evt.status || 'error'})`);
  }
}

btn.addEventListener('click', async () => {
  const f = fileEl.files && fileEl.files[0];
  if (!f) {
    setStatus(false, 'НЕ ОК');
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
        row('Статус', 'НЕ ОК');
      }
    } else {
      setStatus(false, 'НЕ ОК');
      errorBox.hidden = false;
      errorBox.textContent = 'Не получен финальный результат от сервера.';
    }
  } catch (e) {
    setStatus(false, 'НЕ ОК');
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
