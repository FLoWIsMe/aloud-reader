// Voice picker: natural voices from the server (grouped by language) and the browser's own.

import { api } from '../api.js';
import { store } from '../store.js';
import { player } from '../player.js';
import { clear, el, formatBytes, icon, openSheet, toast } from '../ui.js';

let previewAudio = null;

export function openVoiceSheet() {
  const body = el('div');
  const tabs = el('div', { class: 'tabs' });
  const natural = el('div');
  const browser = el('div');
  const show = (name) => {
    natural.hidden = name !== 'natural';
    browser.hidden = name !== 'browser';
    for (const button of tabs.children) button.classList.toggle('active', button.dataset.tab === name);
  };
  tabs.append(
    el('button', { type: 'button', dataset: { tab: 'natural' }, onclick: () => show('natural') }, 'Natural'),
    el('button', { type: 'button', dataset: { tab: 'browser' }, onclick: () => show('browser') }, 'Browser'),
  );
  body.append(tabs, natural, browser);
  const paint = () => {
    paintNatural(natural);
    paintBrowser(browser);
  };
  paint();
  const onChange = () => paint();
  store.addEventListener('tts', onChange);
  store.addEventListener('voices', onChange);
  store.addEventListener('settings', onChange);
  openSheet('Voice', body, {
    onClose: () => {
      stopPreview();
      store.removeEventListener('tts', onChange);
      store.removeEventListener('voices', onChange);
      store.removeEventListener('settings', onChange);
    },
  });
  show(store.settings.voice === 'browser' ? 'browser' : 'natural');
}

function statusNotice() {
  const status = store.tts;
  if (status.state === 'ready') return null;
  if (status.state === 'downloading') {
    const have = formatBytes(status.downloaded_bytes);
    const total = status.total_bytes ? formatBytes(status.total_bytes) : '';
    return el('div', { class: 'notice' },
      el('div', { class: 'row' }, el('span', {}, `Downloading the voice model (${status.current_file || 'files'})`), el('span', {}, total ? `${have} of ${total}` : have)),
      el('div', { class: 'progress' }, el('span', { style: { width: `${Math.round(status.progress * 100)}%` } })),
      el('div', { style: { marginTop: '8px' } }, 'Your browser voice reads in the meantime. Natural voices switch in at the next sentence once they are ready.'),
    );
  }
  if (status.state === 'loading') {
    return el('div', { class: 'notice' }, 'Loading the voice model into memory. This takes a few seconds.');
  }
  const retry = el('button', { class: 'btn small', type: 'button', onclick: () => store.startDownload().catch((error) => toast(error.message, { kind: 'error' })) }, icon('refresh', { size: 16 }), 'Retry download');
  return el('div', { class: `notice ${status.state === 'error' ? 'error' : ''}` },
    el('div', { class: 'row' },
      el('span', {}, status.state === 'error' ? `The voice model could not be downloaded. ${status.error || ''}` : 'The voice model has not been downloaded yet.'),
      retry),
  );
}

function paintNatural(root) {
  clear(root);
  const notice = statusNotice();
  if (notice) root.append(notice);
  if (!store.voices.length) {
    if (!notice) root.append(el('p', { class: 'subtle' }, 'No natural voices are available.'));
    return;
  }
  const groups = new Map();
  for (const voice of store.voices) {
    if (!groups.has(voice.language_name)) groups.set(voice.language_name, []);
    groups.get(voice.language_name).push(voice);
  }
  const selected = store.settings.voice === 'browser' ? null : (store.voiceById(store.settings.voice) || store.voices[0]).id;
  for (const [language, voices] of groups) {
    const group = el('div', { class: 'voice-group' }, el('h4', { text: language }));
    for (const voice of voices) {
      group.append(naturalRow(voice, voice.id === selected));
    }
    root.append(group);
  }
}

function naturalRow(voice, selected) {
  const preview = el('button', { class: 'preview', type: 'button', 'aria-label': `Preview ${voice.name}` }, icon('play', { filled: true }));
  preview.addEventListener('click', (event) => {
    event.stopPropagation();
    if (!store.naturalReady) {
      toast('Natural voices are not ready yet');
      return;
    }
    playPreview(api.previewUrl(voice.id), preview);
  });
  const row = el('button', { class: `voice-row ${selected ? 'selected' : ''}`, type: 'button' },
    icon('check', { size: 18 }),
    el('div', {},
      el('div', { class: 'voice-name', text: voice.name }),
      el('div', { class: 'voice-sub', text: `${voice.language_name} · ${voice.gender}` })),
    voice.quality === 'best' || voice.quality === 'good'
      ? el('span', { class: `tag ${voice.quality === 'best' ? 'best' : ''}`, text: voice.quality === 'best' ? 'Top pick' : 'Clear' })
      : el('span'),
    preview,
  );
  row.querySelector('.icon').classList.add('check');
  row.addEventListener('click', () => {
    store.saveSettings({ voice: voice.id });
    player.voiceChanged();
  });
  return row;
}

function paintBrowser(root) {
  clear(root);
  if (!('speechSynthesis' in window) || !store.browserVoices.length) {
    root.append(el('p', { class: 'subtle' }, 'This browser does not offer any built-in voices.'));
    return;
  }
  root.append(el('div', { class: 'notice' }, 'Built-in voices come from your operating system and browser. They work before the natural voice model is ready and cost no CPU.'));
  const groups = new Map();
  for (const voice of store.browserVoices) {
    const key = voice.lang || 'other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(voice);
  }
  const current = player.browserVoice();
  const selected = store.settings.voice === 'browser' && current ? current.name : null;
  for (const [lang, voices] of groups) {
    const group = el('div', { class: 'voice-group' }, el('h4', { text: lang }));
    for (const voice of voices) group.append(browserRow(voice, voice.name === selected));
    root.append(group);
  }
}

function browserRow(voice, selected) {
  const preview = el('button', { class: 'preview', type: 'button', 'aria-label': `Preview ${voice.name}` }, icon('play', { filled: true }));
  preview.addEventListener('click', (event) => {
    event.stopPropagation();
    stopPreview();
    player.pause();
    const utterance = new SpeechSynthesisUtterance('Natural voices, right on your computer. This is how I sound.');
    utterance.voice = voice;
    utterance.lang = voice.lang;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  });
  const row = el('button', { class: `voice-row ${selected ? 'selected' : ''}`, type: 'button' },
    icon('check', { size: 18 }),
    el('div', {},
      el('div', { class: 'voice-name', text: voice.name }),
      el('div', { class: 'voice-sub', text: `${voice.lang}${voice.localService ? ' · on device' : ''}` })),
    voice.default ? el('span', { class: 'tag', text: 'Default' }) : el('span'),
    preview,
  );
  row.querySelector('.icon').classList.add('check');
  row.addEventListener('click', () => {
    store.saveSettings({ voice: 'browser', browser_voice: voice.name });
    player.voiceChanged();
  });
  return row;
}

function playPreview(url, button) {
  stopPreview();
  player.pause();
  previewAudio = new Audio();
  previewAudio.src = url;
  button.classList.add('busy');
  const done = () => button.classList.remove('busy');
  previewAudio.addEventListener('ended', done);
  previewAudio.addEventListener('error', () => { done(); toast('Preview failed', { kind: 'error' }); });
  previewAudio.addEventListener('playing', done);
  previewAudio.play().catch(() => { done(); });
}

function stopPreview() {
  if (previewAudio) {
    previewAudio.pause();
    previewAudio = null;
  }
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}
