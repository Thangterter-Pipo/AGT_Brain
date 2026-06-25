// core/shell.js — App shell. Dựng sidebar từ registry, chuyển panel, mount/cleanup.
import { getPanels, getPanel } from './registry.js';

let _activeId = null;
let _cleanup = null;

function renderSidebar() {
  const nav = document.querySelector('#sidebar .nav');
  nav.innerHTML = '';
  for (const p of getPanels()) {
    const el = document.createElement('div');
    el.className = 'nav-item' + (p.id === _activeId ? ' active' : '');
    el.innerHTML = `<span class="ico">${p.icon}</span><span>${p.title}</span>`;
    el.onclick = () => activate(p.id);
    nav.appendChild(el);
  }
}

export function activate(id) {
  const panel = getPanel(id);
  if (!panel) return;
  // cleanup panel cũ
  if (typeof _cleanup === 'function') { try { _cleanup(); } catch (e) { console.error(e); } }
  _cleanup = null;
  _activeId = id;

  document.querySelector('#topbar .title').textContent = `${panel.icon} ${panel.title}`;
  const root = document.querySelector('#panel-root');
  root.innerHTML = '';
  try {
    _cleanup = panel.mount(root) || null;
  } catch (e) {
    root.innerHTML = `<div class="card"><b style="color:var(--err)">Lỗi panel:</b> ${e.message}</div>`;
    console.error(e);
  }
  renderSidebar();
  location.hash = id;
}

export function bootShell() {
  document.addEventListener('panels:changed', renderSidebar);
  renderSidebar();
  const fromHash = location.hash.slice(1);
  const first = getPanel(fromHash) ? fromHash : (getPanels()[0] && getPanels()[0].id);
  if (first) activate(first);
}
