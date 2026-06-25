// panels/orchestrator.js — Điều phối: giao 1 task cho mọi agent Connected.
// Gọi /api/orchestrator/dispatch → synapz-orchestrator --live --json.
import { registerPanel } from '../core/registry.js';
import { api } from '../core/api.js';

function resultCard(r) {
  const cls = r.ok ? 'ok' : 'err';
  const label = r.ok ? 'OK' : 'Lỗi';
  const body = r.ok ? (r.output || '') : (r.error || '');
  return `
    <div class="card" style="margin-top:10px">
      <div class="row">
        <span style="font-weight:600">${r.agent}</span>
        <span class="spacer" style="flex:1"></span>
        <span class="badge ${cls}">${label}</span>
      </div>
      <pre class="mono" style="margin-top:8px;white-space:pre-wrap;color:var(--text-dim);max-height:240px;overflow:auto">${escapeHtml(body)}</pre>
    </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

function mount(root) {
  root.innerHTML = `
    <div class="card" style="max-width:760px">
      <h3 style="margin-bottom:12px">🚀 Giao task cho cả nhà agent</h3>
      <p class="muted" style="margin-bottom:12px">Phát 1 lệnh → broadcast tới mọi agent Connected có CLI headless (Claude, Codex, Hermes...).</p>
      <textarea id="prompt" rows="3" style="width:100%;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:10px;font-family:inherit" placeholder="Nhập task... vd: trả lời đúng 1 từ OK">trả lời đúng 1 từ: OK</textarea>
      <div class="row" style="margin-top:12px">
        <button class="btn" id="send">Phát lệnh</button>
        <span class="muted" id="hint"></span>
      </div>
    </div>
    <div id="out" style="max-width:760px"></div>`;

  const send = root.querySelector('#send');
  const hint = root.querySelector('#hint');
  const out = root.querySelector('#out');

  send.onclick = async () => {
    const prompt = root.querySelector('#prompt').value.trim();
    if (!prompt) { hint.textContent = 'Nhập task đã.'; return; }
    send.disabled = true;
    hint.textContent = '⏳ Đang gọi agent (có thể tới ~1-2 phút)...';
    out.innerHTML = '';
    const t0 = Date.now();
    try {
      const res = await api.post('/api/orchestrator/dispatch', { prompt });
      const secs = ((Date.now() - t0) / 1000).toFixed(0);
      if (!res.ok) {
        hint.textContent = `❌ ${res.reason || 'lỗi'} (${secs}s)`;
        return;
      }
      hint.textContent = `✅ ${res.completed}/${res.agents} xong · ${res.failed} lỗi · ${secs}s`;
      out.innerHTML = `<h4 style="margin:16px 0 4px">Kết quả</h4>` + (res.results || []).map(resultCard).join('');
    } catch (e) {
      hint.textContent = `❌ ${e.message}`;
    } finally {
      send.disabled = false;
    }
  };
}

registerPanel({ id: 'orchestrator', title: 'Điều phối', icon: '🚀', order: 20, mount });
