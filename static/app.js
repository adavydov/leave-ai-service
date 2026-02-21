const fileEl = document.getElementById('file');
const outEl = document.getElementById('out');
const btn = document.getElementById('upload');

btn.addEventListener('click', async () => {
  const f = fileEl.files && fileEl.files[0];
  if (!f) {
    outEl.textContent = 'Выберите PDF файл.';
    return;
  }

  outEl.textContent = 'Загружаю...';

  const fd = new FormData();
  fd.append('file', f);

  try {
    const res = await fetch('/api/extract', { method: 'POST', body: fd });
    const contentType = (res.headers.get('content-type') || '').toLowerCase();
    const text = await res.text();

    let obj;
    if (contentType.includes('application/json')) {
      try {
        obj = JSON.parse(text);
      } catch {
        obj = { error: 'Сервер вернул повреждённый JSON.', status: res.status };
      }
    } else {
      const shortText = text
        .replace(/<[^>]*>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 500);
      obj = {
        error: 'Сервер вернул не JSON ответ.',
        status: res.status,
        detail: shortText || 'Пустой ответ',
      };
    }

    if (!res.ok) {
      obj = {
        error: 'Ошибка при обработке PDF.',
        status: res.status,
        detail: obj?.detail || obj?.error || 'Неизвестная ошибка',
      };
    }

    outEl.textContent = JSON.stringify(obj, null, 2);
  } catch (e) {
    outEl.textContent = 'Ошибка запроса: ' + (e && e.message ? e.message : String(e));
  }
});
