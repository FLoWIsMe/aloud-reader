// The player bar at the bottom: transport, progress, speed and voice.

import { store } from '../store.js';
import { player, clampSpeed } from '../player.js';
import { clear, closeFloating, el, formatMinutes, formatSpeed, icon, minutesForWords, openFloating } from '../ui.js';
import { openVoiceSheet } from './voices.js';

const PRESETS = [0.8, 1.0, 1.2, 1.5, 2.0, 3.0];

export function mountPlayerBar(root) {
  clear(root);
  const fill = el('span');
  const track = el('div', { class: 'player-track', role: 'slider', 'aria-label': 'Position' }, el('div', { class: 'bar' }, fill));
  track.addEventListener('click', (event) => {
    if (!player.doc) return;
    const rect = track.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    player.seek(Math.floor(ratio * player.count));
  });

  const title = el('button', { class: 'now-title', type: 'button', onclick: () => {
    if (player.doc) window.location.hash = `#/doc/${player.doc.id}`;
  } });
  const metaLine = el('div', { class: 'now-meta' });

  const prev = el('button', { class: 'skip', type: 'button', 'aria-label': 'Previous sentence', onclick: () => player.prev() }, icon('prev', { filled: true }));
  const play = el('button', { class: 'play', type: 'button', 'aria-label': 'Play', onclick: () => player.toggle() }, icon('play', { filled: true }));
  const next = el('button', { class: 'skip', type: 'button', 'aria-label': 'Next sentence', onclick: () => player.next() }, icon('next', { filled: true }));

  const voiceChip = el('button', { class: 'chip', type: 'button', 'aria-label': 'Choose voice', onclick: () => openVoiceSheet() }, icon('wave', { size: 16 }), el('span', { class: 'chip-text' }));
  const speedChip = el('button', { class: 'chip mono', type: 'button', 'aria-label': 'Speed', text: '1.0x' });
  speedChip.addEventListener('click', () => openSpeedPopover(speedChip));

  root.append(
    track,
    el('div', { class: 'player-inner' },
      el('div', { class: 'player-now' }, title, metaLine),
      el('div', { class: 'player-controls' }, prev, play, next),
      el('div', { class: 'player-side' }, voiceChip, speedChip),
    ),
  );

  const paintVoice = () => {
    const label = voiceChip.querySelector('.chip-text');
    if (store.settings.voice === 'browser') {
      const voice = player.browserVoice();
      label.textContent = voice ? voice.name.replace(/\(.*\)/, '').trim() : 'Browser voice';
    } else {
      const voice = store.voiceById(store.settings.voice) || store.voices[0];
      if (voice && store.naturalReady) label.textContent = voice.name;
      else if (store.tts.state === 'downloading') label.textContent = `Voices ${Math.round(store.tts.progress * 100)}%`;
      else if (store.tts.state === 'loading') label.textContent = 'Preparing voices';
      else label.textContent = 'Browser voice';
    }
  };

  const paint = () => {
    const doc = player.doc;
    root.hidden = !doc;
    if (!doc) return;
    title.textContent = doc.title;
    const count = player.count;
    const position = Math.min(player.index + (player.state === 'ended' ? 1 : 0), count);
    fill.style.width = `${count ? (position / count) * 100 : 0}%`;
    const remaining = minutesForWords(player.wordsRemaining(), player.speed);
    const stateText = player.state === 'loading' ? 'Loading' : player.state === 'ended' ? 'Finished' : `${formatMinutes(remaining)} left`;
    metaLine.textContent = `${Math.min(player.index + 1, count)} of ${count} · ${stateText}`;
    clear(play);
    play.append(icon(player.isActive ? 'pause' : 'play', { filled: true }));
    play.classList.toggle('loading', player.state === 'loading');
    play.setAttribute('aria-label', player.isActive ? 'Pause' : 'Play');
    speedChip.textContent = formatSpeed(player.speed);
    paintVoice();
  };

  player.on('doc', paint);
  player.on('index', paint);
  player.on('state', paint);
  player.on('speed', paint);
  store.on('settings', paintVoice);
  store.on('tts', paintVoice);
  store.on('voices', paintVoice);
  paint();
}

export function openSpeedPopover(anchor) {
  const value = el('div', { class: 'speed-value', text: formatSpeed(player.speed) });
  const slider = el('input', { type: 'range', min: '0.5', max: '5', step: '0.1', value: String(player.speed), 'aria-label': 'Speed' });
  const presets = el('div', { class: 'presets' });
  const paint = () => {
    value.textContent = formatSpeed(player.speed);
    slider.value = String(player.speed);
    for (const button of presets.children) {
      button.classList.toggle('active', Number(button.dataset.speed) === player.speed);
    }
  };
  const apply = (speed) => {
    player.setSpeed(speed);
    store.saveSettings({ speed: clampSpeed(speed) });
    paint();
  };
  for (const preset of PRESETS) {
    presets.append(el('button', { type: 'button', dataset: { speed: String(preset) }, onclick: () => apply(preset) }, formatSpeed(preset)));
  }
  slider.addEventListener('input', () => apply(slider.value));
  const minus = el('button', { class: 'stepper', type: 'button', 'aria-label': 'Slower', onclick: () => apply(player.speed - 0.1) }, '−');
  const plus = el('button', { class: 'stepper', type: 'button', 'aria-label': 'Faster', onclick: () => apply(player.speed + 0.1) }, '+');
  const popover = el('div', { class: 'popover' },
    el('div', { class: 'speed-row' }, minus, value, plus),
    slider,
    presets,
  );
  openFloating(anchor, popover, { align: 'right', above: true });
  paint();
  return () => closeFloating();
}
