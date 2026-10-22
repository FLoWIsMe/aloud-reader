// Entry point: boot, routing, global keyboard shortcuts, progress saving.

import { api } from './api.js';
import { store } from './store.js';
import { player, clampSpeed } from './player.js';
import { closeFloating, closeSheet, debounce, el, icon, isSheetOpen, toast } from './ui.js';
import { renderLibrary } from './views/library.js';
import { renderReader } from './views/reader.js';
import { mountPlayerBar } from './views/playerbar.js';
import { openSettingsSheet } from './views/settings.js';

const view = document.getElementById('view');
let unmount = null;

async function route() {
  closeFloating();
  closeSheet();
  if (unmount) {
    view.dispatchEvent(new Event('view-unmount'));
    unmount();
    unmount = null;
  }
  const hash = window.location.hash || '#/';
  const match = hash.match(/^#\/doc\/([A-Za-z0-9_-]+)/);
  window.scrollTo({ top: 0 });
  if (match) {
    unmount = await renderReader(view, match[1]);
  } else {
    unmount = renderLibrary(view);
  }
}

function installTtsPill() {
  const pill = document.getElementById('tts-pill');
  const paint = () => {
    const status = store.tts;
    pill.dataset.state = status.state;
    if (status.state === 'ready' || status.engine === 'stub') {
      pill.hidden = true;
      return;
    }
    pill.hidden = false;
    let text = 'Natural voices';
    if (status.state === 'downloading') text = `Downloading voices ${Math.round(status.progress * 100)}%`;
    else if (status.state === 'loading') text = 'Preparing voices';
    else if (status.state === 'error') text = 'Voice download failed';
    else if (!store.online) text = 'Server unreachable';
    else text = 'Voices not downloaded';
    pill.replaceChildren(el('span', { class: 'dot' }), el('span', { class: 'text', text }));
    pill.title = status.state === 'error' ? status.error || '' : 'Open voice settings';
  };
  pill.addEventListener('click', () => openSettingsSheet());
  store.on('tts', paint);
  paint();
}

function installShortcuts() {
  window.addEventListener('keydown', (event) => {
    const target = event.target;
    const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
    if (event.key === 'Escape') {
      closeFloating();
      closeSheet();
      return;
    }
    if (typing || isSheetOpen() || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!player.doc) return;
    switch (event.key) {
      case ' ':
        if (target && target.classList && target.classList.contains('s')) return; // handled by the reader
        event.preventDefault();
        player.toggle();
        break;
      case 'ArrowRight':
        event.preventDefault();
        player.next();
        break;
      case 'ArrowLeft':
        event.preventDefault();
        player.prev();
        break;
      case ']':
        player.setSpeed(player.speed + 0.1);
        store.saveSettings({ speed: player.speed });
        toast(`${player.speed.toFixed(1)}x`, { duration: 900 });
        break;
      case '[':
        player.setSpeed(player.speed - 0.1);
        store.saveSettings({ speed: player.speed });
        toast(`${player.speed.toFixed(1)}x`, { duration: 900 });
        break;
      default:
        break;
    }
  });
}

function installProgressSaving() {
  const save = debounce(() => {
    if (!player.doc) return;
    const id = player.doc.id;
    api.updateDocument(id, { position: player.index, finished: false }).catch(() => {});
    store.patchDocumentLocally(id, { position: player.index, finished_at: null });
  }, 700);
  player.on('index', () => {
    if (player.state !== 'idle') save();
  });
  player.on('state', ({ state }) => {
    if (state === 'paused') save();
  });
  player.on('ended', ({ doc }) => {
    if (!doc) return;
    api.updateDocument(doc.id, { finished: true, position: doc.chunks.length - 1 }).catch(() => {});
    store.patchDocumentLocally(doc.id, { finished_at: new Date().toISOString(), position: doc.chunks.length - 1 });
  });
}

function installMediaSession() {
  if (!('mediaSession' in navigator)) return;
  const sync = () => {
    if (!player.doc) return;
    try {
      navigator.mediaSession.metadata = new MediaMetadata({ title: player.doc.title, artist: 'Aloud' });
      navigator.mediaSession.playbackState = player.isActive ? 'playing' : 'paused';
    } catch (error) {
      // optional
    }
  };
  const handlers = {
    play: () => player.play(),
    pause: () => player.pause(),
    previoustrack: () => player.prev(),
    nexttrack: () => player.next(),
  };
  for (const [action, handler] of Object.entries(handlers)) {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch (error) {
      // unsupported action
    }
  }
  player.on('doc', sync);
  player.on('state', sync);
}

async function boot() {
  document.getElementById('settings-button').append(icon('gear'));
  document.getElementById('settings-button').addEventListener('click', () => openSettingsSheet());
  mountPlayerBar(document.getElementById('player'));
  installShortcuts();
  installProgressSaving();
  installMediaSession();
  installTtsPill();
  let lastError = { message: '', at: 0 };
  player.on('error', ({ message }) => {
    if (message === lastError.message && Date.now() - lastError.at < 4000) return;
    lastError = { message, at: Date.now() };
    toast(message, { kind: 'error', duration: 4500 });
  });
  store.loadBrowserVoices();
  try {
    await store.loadSettings();
  } catch (error) {
    toast('Could not load settings. Is the Aloud server running?', { kind: 'error', duration: 6000 });
  }
  player.setSpeed(clampSpeed(store.settings.speed));
  store.on('settings', (settings) => {
    if (clampSpeed(settings.speed) !== player.speed) player.setSpeed(settings.speed);
  });
  store.refreshTts();
  window.addEventListener('hashchange', route);
  await route();
}

boot();
