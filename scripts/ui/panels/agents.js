// panels/agents.js — Lưới AI Agent phát hiện trên hệ thống (như UI bố gửi).
// Đọc data/detected_agents.json (do `synapz-orchestrator --scan` sinh).
import { registerPanel } from '../core/registry.js';
import { api } from '../core/api.js';

const ICONS = {
  'Claude Code': '✳️', 'OpenAI Codex CLI': '🌀', 'Cursor': '🟦', 'Cline': '🤖',
  'Continue': '🟩', 'Gemini CLI': '💎', 'OpenCode': '🟧', 'Hermes Agent': '🪽',
  'Qwen Code': '🟣', 'Aider': '🛠️', 'Factory Droid': '⚛️', 'Kilo Code': '🔲',
  'Amp CLI': '🔴', 'Roo': '🦘', 'DeepSeek TUI': '🐋',
};
const STATUS = {
  Connected: { cls: 'ok', label: 'Connected' },
  NotConfigured: { cls: 'warn', label: 'Not configured' },
  NotInstalled: { cls: 'gray', label: 'Not installed' },
  Unknown: { cls: 'gray', label: 'Unknown' },
};

function card(a) {
  const s = STATUS[a.status] || STATUS.Unknown;
  const icon = ICONS[a.name] || '▸';
  const ver = a.version ? `<span class="muted mono">${a.version}</span>` : '';
  const path = a.binary_path ? `<div class="muted mono" style="margin-top:8px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.binary_path}</div>` : '';
  return `
    <div class="card" data-agent="${a.name}">
      <div class="row">
        <span style="font-size:24px">${icon}</span>
        <div style="flex:1">
          <div style="font-weight:600">${a.name}</div>
          ${ver}
        </div>
        <span class="badge ${s.cls}">${s.label}</span>
      </div>
      ${path}
    </div>`;
}

async function load(root) {
  root.innerHTML = '<div class="muted">Đang quét agent...</div>';
  let agents;
  try {
    agents = await api.json('/data/detected_agents.json');
  } catch (e) {
    root.innerHTML = `<div class="card">Chưa có dữ liệu. Chạy <code class="mono">synapz-orchestrator --scan</code> để quét.<br><span class="muted">${e.message}</span></div>`;
    return;
  }
  const n = agents.reduce((acc, a) => { acc[a.status] = (acc[a.status] || 0) + 1; return acc; }, {});
  root.innerHTML = `
    <div class="row" style="margin-bottom:16px">
      <span class="badge ok">${n.Connected || 0} Connected</span>
      <span class="badge warn">${n.NotConfigured || 0} chưa cấu hình</span>
      <span class="badge gray">${(n.NotInstalled || 0) + (n.Unknown || 0)} khác</span>
      <span class="spacer" style="flex:1"></span>
      <button class="btn ghost" id="rescan">↻ Quét lại</button>
    </div>
    <div class="grid grid-3">${agents.map(card).join('')}</div>`;
  const btn = root.querySelector('#rescan');
  if (btn) btn.onclick = () => load(root);
}

registerPanel({
  id: 'agents',
  title: 'AI Agents',
  icon: '🧩',
  order: 10,
  mount(root) { load(root); },
});
