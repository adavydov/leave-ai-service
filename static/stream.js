function extractJsonTail(text) {
  const s = (text || '').trim();
  if (!s) return null;
  try { return JSON.parse(s); } catch {}
  for (let i = 0; i < s.length; i += 1) {
    if (s[i] !== '{') continue;
    try {
      const chunk = s.slice(i);
      return JSON.parse(chunk);
    } catch {}
  }
  return null;
}

/**
 * @param {Response} res
 * @param {{onStep?: (s:string)=>void, signal?: AbortSignal}} opts
 */
export async function parseStreamResponse(res, opts = {}) {
  const { onStep, signal } = opts;
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalPayload = null;

  const handleLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      const evt = JSON.parse(trimmed);
      if (evt.type === 'step') onStep?.(evt.message || '');
      if (evt.type === 'result') finalPayload = evt.payload;
      if (!evt.type && evt.detail) finalPayload = evt;
      return;
    } catch {}
    onStep?.(trimmed);
    const maybe = extractJsonTail(trimmed);
    if (maybe && (maybe.extract || maybe.error || maybe.detail || maybe.status)) finalPayload = maybe;
  };

  while (true) {
    if (signal?.aborted) {
      await reader.cancel('aborted');
      throw new DOMException('Aborted', 'AbortError');
    }
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      lines.forEach(handleLine);
    }
    if (done) break;
  }

  if (buffer.trim()) {
    handleLine(buffer);
    if (!finalPayload) {
      const tail = extractJsonTail(buffer);
      if (tail) finalPayload = tail;
    }
  }

  return finalPayload;
}

export function runStreamSelfChecks() {
  const cases = [
    { in: '{"type":"result","payload":{"ok":1}}', ok: (x) => x?.type === 'result' },
    { in: 'log... {"error":"boom","status":500}', ok: (x) => x?.status === 500 },
    { in: '{"extract":{"x":1}}', ok: (x) => x?.extract?.x === 1 },
    { in: 'not json', ok: (x) => x === null },
  ];
  return cases.every((c) => c.ok(extractJsonTail(c.in)));
}
