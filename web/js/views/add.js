// The Add sheet: upload a file, paste text, or fetch a link.

import { api } from '../api.js';
import { store } from '../store.js';
import { closeSheet, el, icon, openSheet, toast } from '../ui.js';

const ACCEPT = '.pdf,.docx,.epub,.txt,.md,.markdown,.html,.htm,.rtf,text/plain,application/pdf';

export function openAddSheet(initialTab = 'upload') {
  const body = el('div');
  const panels = { upload: uploadPanel(), paste: pastePanel(), link: linkPanel() };
  const tabs = el('div', { class: 'tabs' });
  const show = (name) => {
    for (const [key, panel] of Object.entries(panels)) panel.hidden = key !== name;
    for (const button of tabs.children) button.classList.toggle('active', button.dataset.tab === name);
    const focusable = panels[name].querySelector('textarea, input[type="url"]');
    if (focusable) focusable.focus();
  };
  for (const [key, label] of [['upload', 'Upload'], ['paste', 'Paste text'], ['link', 'From a link']]) {
    tabs.append(el('button', { type: 'button', dataset: { tab: key }, onclick: () => show(key) }, label));
  }
  body.append(tabs, panels.upload, panels.paste, panels.link);
  openSheet('Add to library', body);
  show(initialTab);
}

function uploadPanel() {
  const input = el('input', { type: 'file', accept: ACCEPT, multiple: true, style: { display: 'none' } });
  const box = el('div', { class: 'upload-box', tabindex: '0', role: 'button' },
    icon('upload', { size: 28 }),
    el('strong', { style: { marginTop: '10px' } }, 'Choose files or drop them here'),
    el('span', {}, 'PDF, Word (.docx), EPUB, Markdown, HTML or plain text'),
  );
  box.addEventListener('click', () => input.click());
  box.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      input.click();
    }
  });
  box.addEventListener('dragover', (event) => { event.preventDefault(); box.classList.add('over'); });
  box.addEventListener('dragleave', () => box.classList.remove('over'));
  box.addEventListener('drop', (event) => {
    event.preventDefault();
    event.stopPropagation();
    box.classList.remove('over');
    importFiles(Array.from(event.dataTransfer.files || []));
  });
  input.addEventListener('change', () => {
    importFiles(Array.from(input.files || []));
    input.value = '';
  });
  return el('div', {}, box, input);
}

function pastePanel() {
  const title = el('input', { type: 'text', placeholder: 'Optional title', maxlength: '300' });
  const text = el('textarea', { placeholder: 'Paste or type anything. Markdown headings and lists are understood.' });
  const submit = el('button', { class: 'btn primary', type: 'submit' }, 'Add text');
  const form = el('form', { class: '' },
    el('div', { class: 'field' }, el('label', { text: 'Title' }), title),
    el('div', { class: 'field' }, el('label', { text: 'Text' }), text),
    el('div', { class: 'sheet-actions' }, submit),
  );
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!text.value.trim()) {
      text.focus();
      return;
    }
    submit.disabled = true;
    try {
      const doc = await api.importText(text.value, title.value.trim() || undefined);
      finish(doc);
    } catch (error) {
      toast(error.message, { kind: 'error' });
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

function linkPanel() {
  const url = el('input', { type: 'url', placeholder: 'https://example.com/article', inputmode: 'url', autocomplete: 'off' });
  const submit = el('button', { class: 'btn primary', type: 'submit' }, 'Fetch and add');
  const hint = el('p', { class: 'subtle', style: { margin: '0 0 14px', lineHeight: '1.5' } },
    'Aloud fetches the page from this computer and keeps the article text, without the menus and footers. Pages behind a login will not work.');
  const form = el('form', {},
    el('div', { class: 'field' }, el('label', { text: 'Link' }), url),
    hint,
    el('div', { class: 'sheet-actions' }, submit),
  );
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!url.value.trim()) {
      url.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = 'Fetching…';
    try {
      const doc = await api.importUrl(url.value.trim());
      finish(doc);
    } catch (error) {
      toast(error.message, { kind: 'error', duration: 5000 });
    } finally {
      submit.disabled = false;
      submit.textContent = 'Fetch and add';
    }
  });
  return form;
}

export async function importFiles(files) {
  if (!files.length) return;
  let last = null;
  let failures = 0;
  for (const file of files) {
    try {
      toast(`Adding ${file.name}…`, { duration: 1500 });
      last = await api.uploadFile(file);
    } catch (error) {
      failures += 1;
      toast(`${file.name}: ${error.message}`, { kind: 'error', duration: 5000 });
    }
  }
  if (last) {
    if (files.length === 1) finish(last);
    else {
      closeSheet();
      await store.loadDocuments();
      toast(`Added ${files.length - failures} of ${files.length} files`);
    }
  }
}

function finish(doc) {
  closeSheet();
  store.loadDocuments().catch(() => {});
  window.location.hash = `#/doc/${doc.id}`;
}
