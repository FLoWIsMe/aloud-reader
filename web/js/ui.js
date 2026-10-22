// Small DOM helpers: element builder, icons, sheets, menus, toasts, formatting.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  append(node, children);
  return node;
}

export function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

const ICONS = {
  play: '<path d="M7 4.5v15l12-7.5z" />',
  pause: '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
  prev: '<path d="M18 5v14L8 12z"/><rect x="5" y="5" width="2" height="14" rx="1"/>',
  next: '<path d="M6 5v14l10-7z"/><rect x="17" y="5" width="2" height="14" rx="1"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  more: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  upload: '<path d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.5 1.5"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5"/>',
  text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  wave: '<path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 12h2"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/>',
};

export function icon(name, { filled = false, size } = {}) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('icon');
  if (filled) svg.classList.add('filled');
  if (size) {
    svg.style.width = `${size}px`;
    svg.style.height = `${size}px`;
  }
  svg.innerHTML = ICONS[name] || '';
  return svg;
}

// Sheets

let openSheetEl = null;

export function openSheet(title, body, { onClose } = {}) {
  closeSheet();
  const root = document.getElementById('sheet-root');
  const sheet = el('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title });
  const backdrop = el('div', { class: 'sheet-backdrop' }, sheet);
  const closeButton = el('button', { class: 'icon-button', type: 'button', 'aria-label': 'Close' }, icon('close'));
  closeButton.addEventListener('click', closeSheet);
  sheet.append(
    el('div', { class: 'sheet-head' }, el('h2', { class: 'sheet-title', text: title }), closeButton),
    el('div', { class: 'sheet-body' }, body),
  );
  backdrop.addEventListener('mousedown', (event) => {
    if (event.target === backdrop) closeSheet();
  });
  root.append(backdrop);
  openSheetEl = { backdrop, onClose };
  const focusable = sheet.querySelector('input, textarea, button:not(.icon-button)');
  if (focusable) focusable.focus();
  return sheet;
}

export function closeSheet() {
  if (!openSheetEl) return;
  const { backdrop, onClose } = openSheetEl;
  openSheetEl = null;
  backdrop.remove();
  if (onClose) onClose();
}

export function isSheetOpen() {
  return openSheetEl !== null;
}

// Floating menus and popovers anchored to a button

let openFloat = null;

export function openFloating(anchor, node, { align = 'right', above = false } = {}) {
  closeFloating();
  document.body.append(node);
  const rect = anchor.getBoundingClientRect();
  const width = node.offsetWidth;
  const height = node.offsetHeight;
  let left = align === 'right' ? rect.right - width : rect.left;
  left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
  let top = above ? rect.top - height - 8 : rect.bottom + 6;
  if (top < 8) top = rect.bottom + 6;
  if (node.classList.contains('popover')) {
    node.style.left = `${left}px`;
    node.style.top = `${top}px`;
  } else {
    node.style.left = `${left + window.scrollX}px`;
    node.style.top = `${top + window.scrollY}px`;
  }
  const dismiss = (event) => {
    if (node.contains(event.target) || anchor.contains(event.target)) return;
    closeFloating();
  };
  setTimeout(() => document.addEventListener('mousedown', dismiss), 0);
  openFloat = { node, dismiss };
  return node;
}

export function closeFloating() {
  if (!openFloat) return;
  document.removeEventListener('mousedown', openFloat.dismiss);
  openFloat.node.remove();
  openFloat = null;
}

// Toasts

export function toast(message, { kind = 'info', duration = 3200 } = {}) {
  const root = document.getElementById('toasts');
  const node = el('div', { class: `toast ${kind === 'error' ? 'error' : ''}`, text: message });
  root.append(node);
  setTimeout(() => node.remove(), duration);
}

export function confirmDialog(message, { confirmLabel = 'Delete', danger = true } = {}) {
  return new Promise((resolve) => {
    const body = el('div', {},
      el('p', { style: { margin: '0 0 18px', lineHeight: '1.5' }, text: message }),
      el('div', { class: 'sheet-actions' },
        el('button', { class: 'btn', type: 'button', onclick: () => { closeSheet(); resolve(false); } }, 'Cancel'),
        el('button', { class: `btn ${danger ? 'danger' : 'primary'}`, type: 'button', onclick: () => { closeSheet(); resolve(true); } }, confirmLabel),
      ),
    );
    openSheet('Are you sure?', body, { onClose: () => resolve(false) });
  });
}

// Formatting

export function formatWords(count) {
  return `${count.toLocaleString()} ${count === 1 ? 'word' : 'words'}`;
}

export function minutesForWords(words, speed = 1) {
  return words / (165 * Math.max(0.1, speed));
}

export function formatMinutes(minutes) {
  if (minutes < 1) return 'under a minute';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function formatSpeed(speed) {
  return `${Number(speed).toFixed(1)}x`;
}

export function relativeTime(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 90) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 7 * 86400) return `${Math.round(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
