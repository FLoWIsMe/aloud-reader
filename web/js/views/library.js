// The library: every document, how far along it is, and the Add flow.

import { api } from '../api.js';
import { store } from '../store.js';
import { player } from '../player.js';
import {
  clear, closeFloating, confirmDialog, el, formatMinutes, formatWords, icon, minutesForWords,
  openFloating, relativeTime, toast,
} from '../ui.js';
import { openAddSheet } from './add.js';

const KIND_LABEL = { upload: 'File', paste: 'Text', url: 'Web', bundled: 'Guide' };

export function renderLibrary(root) {
  root.className = 'view view-library';
  clear(root);
  const addButton = el('button', { class: 'btn primary', type: 'button', onclick: () => openAddSheet() }, icon('plus'), 'Add');
  root.append(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', { class: 'page-title', text: 'Library' }),
        el('div', { class: 'subtle', id: 'library-count' })),
      addButton,
    ),
    el('div', { class: 'library-grid', id: 'library-grid' }),
  );
  paint(root);
  const repaint = () => {
    if (document.getElementById('library-grid')) paint(root);
  };
  store.addEventListener('documents', repaint);
  player.addEventListener('doc', repaint);
  player.addEventListener('state', repaint);
  installDropZone(root);
  store.loadDocuments().catch((error) => toast(error.message, { kind: 'error' }));
  return () => {
    store.removeEventListener('documents', repaint);
    player.removeEventListener('doc', repaint);
    player.removeEventListener('state', repaint);
  };
}

function paint(root) {
  const grid = root.querySelector('#library-grid');
  const count = root.querySelector('#library-count');
  if (!grid) return;
  clear(grid);
  const docs = store.documents;
  if (count) {
    const words = docs.reduce((sum, doc) => sum + doc.word_count, 0);
    count.textContent = docs.length
      ? `${docs.length} ${docs.length === 1 ? 'document' : 'documents'}, ${formatMinutes(minutesForWords(words))} of listening`
      : 'Nothing here yet';
  }
  if (!docs.length) {
    grid.append(el('div', { class: 'empty' },
      el('p', {}, 'Add a PDF, a Word file, an EPUB, some text, or a link to start listening.'),
      el('button', { class: 'btn primary', type: 'button', onclick: () => openAddSheet() }, icon('plus'), 'Add something')));
    return;
  }
  for (const doc of docs) grid.append(card(doc));
}

function card(doc) {
  const progress = doc.chunk_count ? Math.min(1, doc.position / doc.chunk_count) : 0;
  const finished = Boolean(doc.finished_at);
  const minutes = minutesForWords(doc.word_count);
  const remaining = finished ? 'Finished' : progress > 0 ? `${formatMinutes(minutes * (1 - progress))} left` : formatMinutes(minutes);
  const isCurrent = player.doc && player.doc.id === doc.id && player.isActive;
  const node = el('button', {
    class: `doc-card ${isCurrent ? 'playing' : ''}`,
    type: 'button',
    onclick: () => { window.location.hash = `#/doc/${doc.id}`; },
  },
  el('span', { class: 'doc-kind' }, `${KIND_LABEL[doc.source_kind] || doc.source_kind} · ${relativeTime(doc.last_opened_at || doc.created_at)}`),
  el('h3', { class: 'doc-title', text: doc.title }),
  el('div', { class: 'doc-meta' }, `${formatWords(doc.word_count)} · ${remaining}`),
  el('div', { class: 'progress' }, el('span', { style: { width: `${finished ? 100 : progress * 100}%` } })),
  );
  const menuButton = el('button', { class: 'doc-menu', type: 'button', 'aria-label': 'Document menu' }, icon('more', { filled: true }));
  menuButton.addEventListener('click', (event) => {
    event.stopPropagation();
    openMenu(menuButton, doc);
  });
  node.append(menuButton);
  return node;
}

function openMenu(anchor, doc) {
  const menu = el('div', { class: 'menu' },
    el('button', { type: 'button', onclick: () => { closeFloating(); rename(doc); } }, 'Rename'),
    el('button', { type: 'button', onclick: () => { closeFloating(); restart(doc); } }, 'Start over'),
    el('button', { type: 'button', class: 'danger', onclick: () => { closeFloating(); remove(doc); } }, 'Delete'),
  );
  openFloating(anchor, menu);
}

async function rename(doc) {
  const title = window.prompt('Rename document', doc.title);
  if (!title || !title.trim() || title.trim() === doc.title) return;
  try {
    await api.updateDocument(doc.id, { title: title.trim() });
    await store.loadDocuments();
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

async function restart(doc) {
  try {
    await api.updateDocument(doc.id, { position: 0, finished: false });
    if (player.doc && player.doc.id === doc.id) player.seek(0);
    await store.loadDocuments();
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

async function remove(doc) {
  const ok = await confirmDialog(`Delete "${doc.title}" from your library? Cached audio for it is removed as the cache turns over.`);
  if (!ok) return;
  try {
    await api.deleteDocument(doc.id);
    if (player.doc && player.doc.id === doc.id) player.unload();
    await store.loadDocuments();
    toast('Deleted');
  } catch (error) {
    toast(error.message, { kind: 'error' });
  }
}

function installDropZone(root) {
  let depth = 0;
  const enter = (event) => {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault();
    depth += 1;
    document.body.classList.add('dropzone-active');
  };
  const leave = () => {
    depth = Math.max(0, depth - 1);
    if (depth === 0) document.body.classList.remove('dropzone-active');
  };
  const over = (event) => {
    if (event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
  };
  const drop = async (event) => {
    event.preventDefault();
    depth = 0;
    document.body.classList.remove('dropzone-active');
    const files = Array.from(event.dataTransfer.files || []);
    if (!files.length) return;
    const { importFiles } = await import('./add.js');
    importFiles(files);
  };
  window.addEventListener('dragenter', enter);
  window.addEventListener('dragleave', leave);
  window.addEventListener('dragover', over);
  window.addEventListener('drop', drop);
  root.addEventListener('view-unmount', () => {
    window.removeEventListener('dragenter', enter);
    window.removeEventListener('dragleave', leave);
    window.removeEventListener('dragover', over);
    window.removeEventListener('drop', drop);
    document.body.classList.remove('dropzone-active');
  }, { once: true });
}
