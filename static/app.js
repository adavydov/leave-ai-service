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
    const text = await res.text();

    let obj;
    try { obj = JSON.parse(text); } catch { obj = { raw: text }; }

    outEl.textContent = JSON.stringify(obj, null, 2);
  } catch (e) {
    outEl.textContent = 'Ошибка запроса: ' + (e && e.message ? e.message : String(e));
  }
});
