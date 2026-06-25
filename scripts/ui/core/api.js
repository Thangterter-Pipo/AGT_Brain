// core/api.js — Lớp gọi API tập trung. Tự gắn token (token guard đã làm ở server),
// xử lý lỗi/JSON một chỗ. Panel KHÔNG tự fetch — gọi qua đây để dễ nâng cấp.

// Token lấy từ ?token= trên URL (server chặn request qua tunnel nếu thiếu).
const TOKEN = new URLSearchParams(location.search).get('token') || '';

function authHeaders(extra = {}) {
  const h = { ...extra };
  if (TOKEN) h['X-Synapz-Token'] = TOKEN;
  return h;
}

async function request(path, { method = 'GET', body, raw = false } = {}) {
  const opts = { method, headers: authHeaders() };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new ApiError(res.status, text || res.statusText, path);
  }
  if (raw) return res;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

export class ApiError extends Error {
  constructor(status, body, path) {
    super(`API ${status} @ ${path}: ${body}`);
    this.status = status;
    this.body = body;
    this.path = path;
  }
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: 'POST', body }),
  // Static file (vd /data/detected_agents.json) — cùng cơ chế token.
  json: (p) => request(p),
  token: TOKEN,
};

// Server-Sent Events helper (server đã có /api/events).
export function subscribeEvents(onMsg, onErr) {
  const url = TOKEN ? `/api/events?token=${encodeURIComponent(TOKEN)}` : '/api/events';
  const es = new EventSource(url);
  es.onmessage = (e) => { try { onMsg(JSON.parse(e.data)); } catch { onMsg(e.data); } };
  if (onErr) es.onerror = onErr;
  return () => es.close();
}
