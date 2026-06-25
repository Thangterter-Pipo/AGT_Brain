// core/registry.js — Panel Registry. Trái tim của kiến trúc mở rộng.
// Thêm tính năng mới = thêm 1 file panel + gọi registerPanel(). KHÔNG đụng core.

const _panels = [];

/**
 * Đăng ký một panel.
 * @param {object} def
 * @param {string} def.id        - id duy nhất (vd "agents")
 * @param {string} def.title     - tên hiển thị ở sidebar
 * @param {string} def.icon      - emoji/icon
 * @param {number} [def.order]   - thứ tự sidebar (nhỏ = trên)
 * @param {function} def.mount   - (rootEl) => void | cleanupFn. Dựng UI vào rootEl.
 */
export function registerPanel(def) {
  if (!def.id || typeof def.mount !== 'function') {
    console.error('registerPanel: thiếu id hoặc mount', def);
    return;
  }
  if (_panels.find(p => p.id === def.id)) {
    console.warn('registerPanel: trùng id', def.id);
    return;
  }
  _panels.push({ order: 100, icon: '▸', ...def });
  _panels.sort((a, b) => a.order - b.order);
  document.dispatchEvent(new CustomEvent('panels:changed'));
}

export function getPanels() {
  return [..._panels];
}

export function getPanel(id) {
  return _panels.find(p => p.id === id);
}
