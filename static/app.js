const fileEl = document.getElementById('file');
const outEl = document.getElementById('out');
const btn = document.getElementById('upload');

function appendLine(line) {
  outEl.textContent += (outEl.textContent ? '\n' : '') + line;
}

function handleNdjsonLine(line, state) {
  const trimmed = line.trim();
  if (!trimmed) return;

  let evt;
  try {
    evt = JSON.parse(trimmed);
  } catch {
    appendLine('[stream] некорректная строка: ' + trimmed.slice(0, 160));
    return;
  }

  if (evt.type === 'step') {
    appendLine('• ' + evt.message);
  } else if (evt.type === 'result') {
    state.finalPayload = evt.payload;
    appendLine(evt.ok ? '✅ Завершено успешно' : `❌ Ошибка (${evt.status})`);
  } else if (evt.detail) {
    state.finalPayload = evt;
    appendLine('❌ Ошибка (' + (evt.status || 'unknown') + ')');
  }
}

btn.addEventListener('click', async () => {
  const f = fileEl.files && fileEl.files[0];
  if (!f) {
    outEl.textContent = 'Выберите PDF файл.';
    return;
  }

  outEl.textContent = 'Старт обработки...';

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
    const state = { finalPayload: null };

    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          handleNdjsonLine(line, state);
        }
      }
      if (done) break;
    }

    if (buffer.trim()) {
      handleNdjsonLine(buffer, state);
    }

    if (state.finalPayload) {
      appendLine('');
      appendLine(JSON.stringify(state.finalPayload, null, 2));
    } else {
      appendLine('❌ Не получен финальный результат от сервера.');
    }
  } catch (e) {
    const msg = e && e.name === 'AbortError'
      ? '❌ Запрос выполняется слишком долго (>300с). Скопируйте шаги выше и проверьте Render logs.'
      : '❌ Ошибка запроса: ' + (e && e.message ? e.message : String(e));
    appendLine(msg);
  } finally {
    clearTimeout(timeoutId);
  }
});
