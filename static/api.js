import { parseStreamResponse } from './stream.js';

/**
 * @param {File} file
 * @param {{onStep?: (msg:string)=>void, signal?: AbortSignal}} opts
 */
export async function uploadPdf(file, opts = {}) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/extract/stream', { method: 'POST', body: fd, signal: opts.signal });
  const requestId = res.headers.get('x-request-id') || null;
  const ct = (res.headers.get('content-type') || '').toLowerCase();

  let payload;
  if (ct.includes('application/json')) payload = await res.json();
  else if (res.body) payload = await parseStreamResponse(res, opts);
  else payload = JSON.parse(await res.text());

  return { ok: res.ok && !payload?.error, status: res.status, payload, requestId };
}
