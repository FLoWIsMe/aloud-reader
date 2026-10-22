// The reader: the document as sentences, the current one highlighted, click to jump.

import { api } from '../api.js';
import { store } from '../store.js';
import { player } from '../player.js';
import { clear, el, formatMinutes, formatWords, icon, minutesForWords, toast } from '../ui.js';

const SOURCE_LABEL = { upload: 'Uploaded file', paste: 'Pasted text', url: 'Web page', bundled: 'Included with Aloud' };

export async function renderReader(root, documentId) {
  root.className = 'view view-reader';
  clear(root);
  root.append(el('p', { class: 'subtle', text: 'Opening…' }));
  let doc;
  try {
    doc = await api.getDocument(documentId);
  } catch (error) {
    toast(error.message, { kind: 'error' });
    window.location.hash = '#/';
    return () => {};
  }
  clear(root);

  const chunks = doc.blocks.flatMap((block) => block.sentences);
  const playable = { id: doc.id, title: doc.title, chunks, word_count: doc.word_count };
  const startAt = doc.finished_at ? 0 : doc.position;
  player.load(playable, startAt);

  const spans = [];
  const article = el('article', { class: 'reader' });
  let index = 0;
  const fillBlock = (node, block) => {
    block.sentences.forEach((sentence, position) => {
      const span = el('span', { class: 's', dataset: { i: String(index) }, tabindex: '0', text: sentence });
      spans.push(span);
      node.append(span);
      if (position < block.sentences.length - 1) node.append(' ');
      index += 1;
    });
    return node;
  };
  // When the document opens with a heading that is its title, that heading is the title.
  const first = doc.blocks[0];
  const titleIsFirstBlock = first && first.kind === 'heading' && first.sentences.join(' ') === doc.title;
  const titleNode = titleIsFirstBlock
    ? fillBlock(el('h1', { class: 'reader-title reader' }), first)
    : el('h1', { class: 'reader-title', text: doc.title });
  for (const block of doc.blocks.slice(titleIsFirstBlock ? 1 : 0)) {
    const tag = block.kind === 'heading' ? `h${Math.min(4, Math.max(1, block.level || 2))}` : 'p';
    article.append(fillBlock(el(tag), block));
  }

  const minutes = minutesForWords(doc.word_count, player.speed);
  const source = doc.source_kind === 'url' && doc.source_name
    ? el('a', { href: doc.source_name, target: '_blank', rel: 'noopener', text: ' Open original' })
    : null;
  const meta = el('div', { class: 'reader-meta' },
    `${SOURCE_LABEL[doc.source_kind] || doc.source_kind} · ${formatWords(doc.word_count)} · ${formatMinutes(minutes)} at ${player.speed.toFixed(1)}x`,
    source,
  );

  root.append(
    el('div', { class: 'reader-head' },
      el('a', { class: 'back', href: '#/' }, icon('back'), 'Library'),
    ),
    titleNode,
    meta,
    article,
    el('div', { class: 'reader-end' },
      el('button', { class: 'btn', type: 'button', onclick: () => { player.seek(0); player.play(); } }, 'Listen again from the top'),
    ),
  );

  // Click or keyboard on a sentence jumps there and starts playing.
  const onSentenceClick = (event) => {
    const span = event.target.closest('.s');
    if (!span) return;
    player.seek(Number(span.dataset.i));
    player.play();
  };
  article.addEventListener('click', onSentenceClick);
  titleNode.addEventListener('click', onSentenceClick);
  article.addEventListener('keydown', (event) => {
    const span = event.target.closest('.s');
    if (!span || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    player.seek(Number(span.dataset.i));
    player.play();
  });

  // Highlighting and auto-scroll.
  let lastUserScroll = 0;
  let returnPill = null;
  const onUserScroll = () => { lastUserScroll = Date.now(); };
  window.addEventListener('wheel', onUserScroll, { passive: true });
  window.addEventListener('touchmove', onUserScroll, { passive: true });
  window.addEventListener('keydown', (event) => {
    if (['PageUp', 'PageDown', 'Home', 'End'].includes(event.key)) onUserScroll();
  });

  const showReturn = (show) => {
    if (show && !returnPill) {
      returnPill = el('button', { class: 'return-pill', type: 'button', onclick: () => { lastUserScroll = 0; highlight(player.index, true); } }, icon('down', { size: 16 }), 'Back to the current sentence');
      document.body.append(returnPill);
    } else if (!show && returnPill) {
      returnPill.remove();
      returnPill = null;
    }
  };

  let current = -1;
  const highlight = (i, force = false) => {
    if (current >= 0 && spans[current]) spans[current].classList.remove('active');
    current = i;
    const span = spans[i];
    if (!span) return;
    span.classList.add('active');
    spans.forEach((node, position) => node.classList.toggle('done', position < i && player.state !== 'idle'));
    const recentlyScrolled = Date.now() - lastUserScroll < 4000;
    if (store.settings.autoscroll && (force || !recentlyScrolled)) {
      const rect = span.getBoundingClientRect();
      const viewTop = 70;
      const viewBottom = window.innerHeight - 120;
      if (force || rect.top < viewTop || rect.bottom > viewBottom) {
        span.scrollIntoView({ block: 'center', behavior: force ? 'smooth' : 'smooth' });
      }
      showReturn(false);
    } else if (store.settings.autoscroll) {
      const rect = span.getBoundingClientRect();
      showReturn(rect.top < 70 || rect.bottom > window.innerHeight - 120);
    }
  };

  const onIndex = ({ detail }) => {
    if (!player.doc || player.doc.id !== doc.id) return;
    highlight(detail.index);
  };
  const onState = () => {
    if (!player.doc || player.doc.id !== doc.id) return;
    if (player.state === 'ended') showReturn(false);
  };
  player.addEventListener('index', onIndex);
  player.addEventListener('state', onState);

  // First paint: jump to where they left off without animation.
  requestAnimationFrame(() => {
    const span = spans[player.index];
    if (span && player.index > 0) {
      span.classList.add('active');
      current = player.index;
      span.scrollIntoView({ block: 'center', behavior: 'auto' });
    } else if (span) {
      span.classList.add('active');
      current = player.index;
    }
  });

  return () => {
    player.removeEventListener('index', onIndex);
    player.removeEventListener('state', onState);
    window.removeEventListener('wheel', onUserScroll);
    window.removeEventListener('touchmove', onUserScroll);
    showReturn(false);
  };
}
