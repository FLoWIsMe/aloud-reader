// App-wide state with a tiny subscription model.

import { api } from './api.js';

const DEFAULT_SETTINGS = {
  voice: 'af_heart',
  browser_voice: null,
  speed: 1.0,
  theme: 'system',
  autoscroll: true,
  text_size: 'medium',
};

class Store extends EventTarget {
  constructor() {
    super();
    this.settings = { ...DEFAULT_SETTINGS };
    this.tts = { state: 'missing', progress: 0, downloaded_bytes: 0, total_bytes: 0, error: null };
    this.voices = [];
    this.browserVoices = [];
    this.documents = [];
    this.online = true;
    this._pollTimer = null;
  }

  emit(name, detail) {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }

  on(name, handler) {
    this.addEventListener(name, (event) => handler(event.detail));
  }

  // Settings

  async loadSettings() {
    this.settings = { ...DEFAULT_SETTINGS, ...(await api.getSettings()) };
    this.applyTheme();
    this.emit('settings', this.settings);
    return this.settings;
  }

  async saveSettings(patch) {
    this.settings = { ...this.settings, ...patch };
    this.applyTheme();
    this.emit('settings', this.settings);
    try {
      this.settings = { ...DEFAULT_SETTINGS, ...(await api.updateSettings(patch)) };
    } catch (error) {
      console.warn('Settings were not saved', error);
    }
    return this.settings;
  }

  applyTheme() {
    const root = document.documentElement;
    const theme = this.settings.theme || 'system';
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    root.setAttribute('data-text-size', this.settings.text_size || 'medium');
  }

  // Voices and model status

  async refreshTts() {
    try {
      const status = await api.ttsStatus();
      const becameReady = status.state === 'ready' && this.tts.state !== 'ready';
      this.tts = status;
      this.online = true;
      if (becameReady || (status.state === 'ready' && this.voices.length === 0)) {
        await this.loadVoices();
      }
    } catch (error) {
      this.online = false;
    }
    this.emit('tts', this.tts);
    this.schedulePoll();
    return this.tts;
  }

  schedulePoll() {
    clearTimeout(this._pollTimer);
    if (this.tts.state === 'ready') return;
    const wait = this.tts.state === 'downloading' || this.tts.state === 'loading' ? 1500 : 8000;
    this._pollTimer = setTimeout(() => this.refreshTts(), wait);
  }

  async loadVoices() {
    try {
      const payload = await api.voices();
      this.voices = payload.voices || [];
      this.emit('voices', this.voices);
    } catch (error) {
      console.warn('Could not load voices', error);
    }
  }

  async startDownload() {
    this.tts = await api.startDownload();
    this.emit('tts', this.tts);
    this.schedulePoll();
  }

  loadBrowserVoices() {
    if (!('speechSynthesis' in window)) return;
    const read = () => {
      const voices = window.speechSynthesis.getVoices() || [];
      if (voices.length) {
        this.browserVoices = voices.slice().sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name));
        this.emit('voices', this.voices);
      }
    };
    read();
    window.speechSynthesis.addEventListener('voiceschanged', read);
  }

  get naturalReady() {
    return this.tts.state === 'ready' && this.voices.length > 0;
  }

  voiceById(id) {
    return this.voices.find((voice) => voice.id === id) || null;
  }

  // Documents

  async loadDocuments() {
    this.documents = await api.listDocuments();
    this.emit('documents', this.documents);
    return this.documents;
  }

  patchDocumentLocally(id, patch) {
    const doc = this.documents.find((item) => item.id === id);
    if (doc) Object.assign(doc, patch);
  }
}

export const store = new Store();
