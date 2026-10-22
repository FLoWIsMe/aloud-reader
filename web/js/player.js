// Plays a document one sentence at a time, with natural voices from the server when they
// are ready and the browser's own voice otherwise. Both paths share the same chunk index,
// so highlighting, seeking and progress never care which one is speaking.

import { api } from './api.js';
import { store } from './store.js';

const SILENT_WAV = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAA'
  + 'A'.repeat(212);
const PREFETCH_AHEAD = 3;
const KEEP_BEHIND = 2;
const KEEP_AHEAD = 10;
const MIN_SPEED = 0.5;
const MAX_SPEED = 5.0;

export function clampSpeed(speed) {
  const value = Math.round(Number(speed) * 10) / 10;
  if (Number.isNaN(value)) return 1.0;
  return Math.min(MAX_SPEED, Math.max(MIN_SPEED, value));
}

export class Player extends EventTarget {
  constructor() {
    super();
    this.doc = null;
    this.index = 0;
    this.state = 'idle'; // idle | loading | playing | paused | ended
    this.speed = 1.0;
    this.activeSource = null; // 'natural' | 'browser' for the sentence that last played
    this.pausedMidSentence = false;
    this.token = 0;
    this.unlocked = false;
    this.prefetched = new Map();
    this.wordsAt = [];
    this.speechFailures = 0;

    this.audio = new Audio();
    this.audio.preload = 'auto';
    this.audio.addEventListener('ended', () => {
      if (this.state === 'playing' && this.activeSource === 'natural') this.advance();
    });
    this.audio.addEventListener('error', () => {
      if (this.state === 'playing' && this.activeSource === 'natural') {
        this.emitError('Audio playback failed, continuing with the browser voice');
        this.speakChunk(this.index, ++this.token);
      }
    });
  }

  emit(name, detail = {}) {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }

  on(name, handler) {
    this.addEventListener(name, (event) => handler(event.detail));
  }

  emitError(message) {
    this.emit('error', { message });
  }

  setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.emit('state', { state });
  }

  // Loading

  load(doc, startIndex = 0) {
    if (this.doc && this.doc.id === doc.id) {
      this.doc = doc;
      return;
    }
    this.stop();
    this.doc = doc;
    this.wordsAt = [];
    let total = 0;
    for (const chunk of doc.chunks) {
      total += chunk.split(/\s+/).filter(Boolean).length;
      this.wordsAt.push(total);
    }
    this.index = Math.min(Math.max(0, startIndex), Math.max(0, doc.chunks.length - 1));
    this.pausedMidSentence = false;
    this.setState('idle');
    this.emit('doc', { doc });
    this.emit('index', { index: this.index });
  }

  unload() {
    this.stop();
    this.doc = null;
    this.setState('idle');
    this.emit('doc', { doc: null });
  }

  get count() {
    return this.doc ? this.doc.chunks.length : 0;
  }

  get isActive() {
    return this.state === 'playing' || this.state === 'loading';
  }

  wordsRemaining() {
    if (!this.doc || !this.wordsAt.length) return 0;
    const total = this.wordsAt[this.wordsAt.length - 1];
    const before = this.index > 0 ? this.wordsAt[this.index - 1] : 0;
    return Math.max(0, total - before);
  }

  // Transport

  play() {
    if (!this.doc || !this.count) return;
    if (this.state === 'playing' || this.state === 'loading') return;
    this.unlock();
    if (this.state === 'ended') {
      this.index = 0;
      this.pausedMidSentence = false;
    }
    if (this.state === 'paused' && this.pausedMidSentence && this.activeSource === 'natural') {
      this.pausedMidSentence = false;
      const token = ++this.token;
      this.audio.playbackRate = this.speed;
      this.audio.play().then(() => {
        if (token === this.token) this.setState('playing');
      }).catch(() => {
        if (token === this.token) this.playChunk(this.index);
      });
      this.setState('playing');
      return;
    }
    this.playChunk(this.index);
  }

  pause() {
    if (this.state !== 'playing' && this.state !== 'loading') return;
    this.token += 1;
    if (this.activeSource === 'natural' && this.state === 'playing') {
      this.audio.pause();
      this.pausedMidSentence = !this.audio.ended && this.audio.currentTime > 0;
    } else {
      this.pausedMidSentence = false;
      this.cancelSpeech();
    }
    this.setState('paused');
  }

  toggle() {
    if (this.isActive) this.pause();
    else this.play();
  }

  stop() {
    this.token += 1;
    this.cancelSpeech();
    try {
      this.audio.pause();
      this.audio.removeAttribute('src');
      this.audio.load();
    } catch (error) {
      // some browsers throw on load() with no source; nothing to do
    }
    this.clearPrefetch();
    this.pausedMidSentence = false;
    this.activeSource = null;
  }

  seek(index) {
    if (!this.doc) return;
    const target = Math.min(Math.max(0, index), this.count - 1);
    this.pausedMidSentence = false;
    if (this.isActive) {
      this.playChunk(target);
      return;
    }
    this.index = target;
    if (this.state === 'ended') this.setState('paused');
    this.emit('index', { index: this.index });
  }

  next() {
    if (!this.doc) return;
    if (this.index + 1 >= this.count) {
      this.finish();
      return;
    }
    this.seek(this.index + 1);
  }

  prev() {
    if (!this.doc) return;
    this.seek(Math.max(0, this.index - 1));
  }

  setSpeed(speed) {
    const next = clampSpeed(speed);
    if (next === this.speed) return;
    this.speed = next;
    this.audio.playbackRate = next;
    if (this.state === 'playing' && this.activeSource === 'browser') {
      this.playChunk(this.index); // utterance rate cannot change mid-sentence
    }
    this.emit('speed', { speed: next });
  }

  voiceChanged() {
    this.clearPrefetch();
    this.pausedMidSentence = false;
    if (this.isActive) this.playChunk(this.index);
  }

  // Internals

  unlock() {
    if (this.unlocked) return;
    this.unlocked = true;
    try {
      this.audio.src = SILENT_WAV;
      this.audio.play().catch(() => {});
    } catch (error) {
      // the first real play() will ask for a gesture again if this did not take
    }
  }

  async playChunk(index) {
    const token = ++this.token;
    this.index = index;
    this.pausedMidSentence = false;
    this.emit('index', { index });
    this.setState('loading');
    const wantsNatural = this.voiceKind() === 'natural' && store.naturalReady;
    if (wantsNatural) {
      try {
        const url = await this.fetchChunk(index);
        if (token !== this.token) return;
        this.cancelSpeech();
        this.audio.src = url;
        this.audio.playbackRate = this.speed;
        await this.audio.play();
        if (token !== this.token) return;
        this.activeSource = 'natural';
        this.speechFailures = 0;
        this.setState('playing');
        this.prefetchAround(index);
        return;
      } catch (error) {
        if (token !== this.token) return;
        if (!this.warnedFallback) {
          this.warnedFallback = true;
          this.emitError('Natural voice unavailable for this sentence, using the browser voice');
        }
      }
    }
    this.speakChunk(index, token);
  }

  speakChunk(index, token) {
    if (!('speechSynthesis' in window)) {
      this.setState('paused');
      this.emitError('This browser has no speech voices and natural voices are not ready yet');
      return;
    }
    const text = this.doc.chunks[index];
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = Math.min(this.speed, 4.0);
    const voice = this.browserVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }
    utterance.onend = () => {
      this.speechFailures = 0;
      if (token === this.token && this.state === 'playing') this.advance();
    };
    utterance.onerror = (event) => {
      if (token !== this.token) return;
      if (event.error === 'interrupted' || event.error === 'canceled') return;
      this.speechFailures += 1;
      if (this.speechFailures >= 2) {
        // Nothing can read right now (no system voices, or synthesis is broken). Stop
        // instead of racing through the document with an error on every sentence.
        this.speechFailures = 0;
        this.token += 1;
        this.setState('paused');
        this.emitError(store.tts.state === 'ready'
          ? 'The browser voice is not working. Pick a natural voice from the voice picker.'
          : 'The browser voice is not working, and natural voices are not ready yet. Press play again once the voice model has downloaded.');
        return;
      }
      setTimeout(() => {
        if (token === this.token && this.state === 'playing') this.advance();
      }, 300);
    };
    this.cancelSpeech();
    this.activeSource = 'browser';
    this.setState('playing');
    window.speechSynthesis.speak(utterance);
  }

  cancelSpeech() {
    if ('speechSynthesis' in window && (window.speechSynthesis.speaking || window.speechSynthesis.pending)) {
      window.speechSynthesis.cancel();
    }
  }

  advance() {
    if (!this.doc) return;
    if (this.index + 1 >= this.count) {
      this.finish();
      return;
    }
    this.playChunk(this.index + 1);
  }

  finish() {
    this.token += 1;
    this.cancelSpeech();
    this.audio.pause();
    this.pausedMidSentence = false;
    this.setState('ended');
    this.emit('ended', { doc: this.doc });
  }

  voiceKind() {
    return store.settings.voice === 'browser' ? 'browser' : 'natural';
  }

  naturalVoiceId() {
    const wanted = store.settings.voice;
    if (wanted && wanted !== 'browser' && store.voiceById(wanted)) return wanted;
    return store.voices.length ? store.voices[0].id : wanted;
  }

  browserVoice() {
    const voices = store.browserVoices;
    if (!voices.length) return null;
    const wanted = store.settings.browser_voice;
    if (wanted) {
      const match = voices.find((voice) => voice.name === wanted);
      if (match) return match;
    }
    const language = (navigator.language || 'en').toLowerCase();
    return voices.find((voice) => voice.default && voice.lang.toLowerCase().startsWith(language.slice(0, 2)))
      || voices.find((voice) => voice.lang.toLowerCase().startsWith(language.slice(0, 2)))
      || voices.find((voice) => voice.default)
      || voices[0];
  }

  fetchChunk(index) {
    const existing = this.prefetched.get(index);
    if (existing) return existing.promise;
    const voice = this.naturalVoiceId();
    const promise = fetch(api.audioUrl(this.doc.id, index, voice)).then(async (response) => {
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          detail = (await response.json()).detail || detail;
        } catch (error) {
          // not JSON
        }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const entry = this.prefetched.get(index);
      if (entry) entry.url = url;
      return url;
    });
    promise.catch(() => this.prefetched.delete(index));
    this.prefetched.set(index, { promise, url: null });
    return promise;
  }

  prefetchAround(index) {
    for (const [key, entry] of this.prefetched) {
      if (key < index - KEEP_BEHIND || key > index + KEEP_AHEAD) {
        if (entry.url) URL.revokeObjectURL(entry.url);
        this.prefetched.delete(key);
      }
    }
    for (let next = index + 1; next <= Math.min(this.count - 1, index + PREFETCH_AHEAD); next += 1) {
      if (!this.prefetched.has(next)) this.fetchChunk(next).catch(() => {});
    }
  }

  clearPrefetch() {
    for (const entry of this.prefetched.values()) {
      if (entry.url) URL.revokeObjectURL(entry.url);
    }
    this.prefetched.clear();
  }
}

export const player = new Player();
