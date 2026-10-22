// Settings: appearance, reading, the voice model, the audio cache, and about.

import { api } from '../api.js';
import { store } from '../store.js';
import { clear, el, formatBytes, icon, openSheet, toast } from '../ui.js';

export function openSettingsSheet() {
  const body = el('div');
  const paint = () => paintSettings(body);
  paint();
  const onChange = () => paint();
  store.addEventListener('tts', onChange);
  store.addEventListener('settings', onChange);
  openSheet('Settings', body, {
    onClose: () => {
      store.removeEventListener('tts', onChange);
      store.removeEventListener('settings', onChange);
    },
  });
}

function segmented(options, current, onPick) {
  const node = el('div', { class: 'segmented' });
  for (const [value, label] of options) {
    node.append(el('button', { type: 'button', class: value === current ? 'active' : '', onclick: () => onPick(value) }, label));
  }
  return node;
}

function toggle(current, onPick) {
  const node = el('button', { class: `switch ${current ? 'on' : ''}`, type: 'button', role: 'switch', 'aria-checked': String(Boolean(current)) });
  node.addEventListener('click', () => onPick(!current));
  return node;
}

function setting(label, help, control) {
  return el('div', { class: 'setting' },
    el('div', {}, el('div', { class: 'setting-label', text: label }), help ? el('div', { class: 'setting-help', text: help }) : null),
    control);
}

function paintSettings(root) {
  clear(root);
  const s = store.settings;
  root.append(
    setting('Appearance', null, segmented([['system', 'Auto'], ['light', 'Light'], ['dark', 'Dark']], s.theme, (theme) => store.saveSettings({ theme }))),
    setting('Text size', null, segmented([['small', 'S'], ['medium', 'M'], ['large', 'L']], s.text_size, (text_size) => store.saveSettings({ text_size }))),
    setting('Follow along', 'Scroll to keep the sentence being read in view', toggle(s.autoscroll, (autoscroll) => store.saveSettings({ autoscroll }))),
    el('h3', { style: { fontFamily: 'var(--font-serif)', margin: '26px 0 6px', fontSize: '1.1rem' }, text: 'Natural voices' }),
    modelCard(),
    el('h3', { style: { fontFamily: 'var(--font-serif)', margin: '26px 0 6px', fontSize: '1.1rem' }, text: 'Audio cache' }),
    cacheCard(),
    el('h3', { style: { fontFamily: 'var(--font-serif)', margin: '26px 0 6px', fontSize: '1.1rem' }, text: 'Keyboard' }),
    el('div', { class: 'kbd-list' },
      el('kbd', { text: 'Space' }), 'Play or pause',
      el('kbd', { text: '← →' }), 'Previous or next sentence',
      el('kbd', { text: '[ ]' }), 'Slower or faster by 0.1x',
      el('kbd', { text: 'Esc' }), 'Close this panel',
    ),
    el('p', { class: 'subtle', style: { marginTop: '26px', lineHeight: '1.5' } },
      'Aloud for the web is open source. Voices by Kokoro-82M through onnxruntime; everything runs on this computer. ',
      el('a', { href: '/api/docs', target: '_blank', rel: 'noopener', text: 'API reference' }), '.'),
  );
}

function modelCard() {
  const status = store.tts;
  const node = el('div', { class: `notice ${status.state === 'error' ? 'error' : ''}` });
  if (status.engine === 'stub') {
    node.append('Running with the test engine (ALOUD_TTS_ENGINE=stub). Sentences play as tones.');
    return node;
  }
  if (status.state === 'ready') {
    node.append(el('div', { class: 'row' }, el('span', {}, `Kokoro is loaded with ${store.voices.length} voices. Synthesis runs on the CPU, so the first play of a sentence takes a moment and repeats are instant.`)));
    return node;
  }
  if (status.state === 'downloading') {
    node.append(
      el('div', { class: 'row' }, el('span', {}, `Downloading ${status.current_file || 'the voice model'}`), el('span', {}, `${formatBytes(status.downloaded_bytes)}${status.total_bytes ? ` of ${formatBytes(status.total_bytes)}` : ''}`)),
      el('div', { class: 'progress' }, el('span', { style: { width: `${Math.round(status.progress * 100)}%` } })),
    );
    return node;
  }
  if (status.state === 'loading') {
    node.append('Loading the model into memory.');
    return node;
  }
  const retry = el('button', { class: 'btn small', type: 'button', onclick: () => store.startDownload().then(() => toast('Download started')).catch((error) => toast(error.message, { kind: 'error' })) }, icon('refresh', { size: 16 }), status.state === 'error' ? 'Retry' : 'Download');
  node.append(el('div', { class: 'row' },
    el('span', {}, status.state === 'error'
      ? `Download failed: ${status.error || 'unknown error'}. The browser voice keeps reading in the meantime.`
      : 'The voice model (about 340 MB) is not on this computer yet.'),
    retry));
  return node;
}

function cacheCard() {
  const node = el('div', { class: 'notice' });
  const size = el('span', { text: 'Measuring…' });
  const clearButton = el('button', { class: 'btn small', type: 'button' }, 'Clear');
  clearButton.addEventListener('click', async () => {
    clearButton.disabled = true;
    try {
      await api.clearCache();
      toast('Audio cache cleared');
      await refresh();
    } catch (error) {
      toast(error.message, { kind: 'error' });
    } finally {
      clearButton.disabled = false;
    }
  });
  const refresh = async () => {
    try {
      const stats = await api.cacheStats();
      size.textContent = `${formatBytes(stats.bytes)} used of ${formatBytes(stats.max_bytes)}`;
    } catch (error) {
      size.textContent = 'Unavailable';
    }
  };
  refresh();
  node.append(el('div', { class: 'row' }, el('span', {}, 'Synthesized sentences are kept on disk so repeats play instantly. ', size), clearButton));
  return node;
}
