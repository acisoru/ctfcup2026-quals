'use strict';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const scope = UUID_RE.test(location.pathname.slice(1)) ? location.pathname.slice(1) : null;
if (scope) localStorage.setItem('codex.uuid', scope);
else if (localStorage.getItem('codex.uuid')) location.replace('/' + localStorage.getItem('codex.uuid') + location.search);

const els = [...document.querySelectorAll('[id]')].reduce((a, el) => ((a[el.id] = el), a), {});
const state = { toc: [], ch: [], total: 0, spread: 0, page: 0, single: false, busy: false, note: null };
const cache = new Map();
const notesCache = new Map(); 
const mq = matchMedia('(max-width: 760px)');
const flipMs = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--flip-ms')) * 1000 || 700;


const api = async (url, opts) => {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'HTTP ' + res.status);
  return data;
};
const chapter = (book, n) => {
  const k = book + '.' + n;
  return cache.get(k) || cache.set(k, api(`/api/chapter/${book}/${n}`)).get(k);
};
const notes = (pid, fresh) => {
  if (fresh) notesCache.delete(pid);
  return notesCache.get(pid) || notesCache.set(pid, api('/api/comments?page=' + pid + (scope ? '&scope=' + scope : '')).catch(() => [])).get(pid);
};

const meta = (i) => i ? state.ch[i - 1] : { pid: 'title', title: true };
const cursor = () => state.single ? state.page : state.spread * 2 + 1;
const refOf = (pid, anchor) => {
  const b = state.toc.find((x) => x.id === pid.split('.')[0]);
  return (b ? `${b.name} ${+pid.split('.')[1]}` : 'титульный лист') + (anchor ? ':' + anchor : '');
};

function fillPage(el, i) {
  const m = meta(i);
  el.innerHTML = '';
  el.dataset.pid = m.pid;

  const margin = document.createElement('div');
  margin.className = 'margin-notes';
  const add = Object.assign(document.createElement('button'), { className: 'note-add', textContent: '+ заметка' });
  add.onclick = () => openNote(m.pid, null);
  margin.append(add);

  const text = Object.assign(document.createElement('div'), { className: 'verses-wrap' });
  const body = Object.assign(document.createElement('div'), { className: 'page-body' });
  body.append(margin, text);
  el.append(body);

  if (m.title) {
    text.classList.add('titlepage-holder');
    text.innerHTML = `<div class="titlepage"><div class="t-name">Библия</div><hr class="t-rule">
      <div class="t-sub">синодальный перевод</div><div class="t-sub">66 книг · 1189 глав</div>
      <div class="t-note">${scope
        ? 'Приватный режим — заметки видны только по этой ссылке.'
        : 'Заметки на полях видны всем читателям —<br>оставьте и вы свою.'}</div></div>`;
  } else {
    const head = Object.assign(document.createElement('div'), { className: 'page-head',
      innerHTML: `<span class="bname">${m.name}</span><span class="chnum">Глава ${m.ch}</span>` });
    const num = Object.assign(document.createElement('div'), { className: 'page-num', textContent: i });
    el.prepend(head);
    el.append(num);
    el.classList.add('loading');
    chapter(m.book, m.ch).then((d) => {
      if (el.dataset.pid !== m.pid) return;
      el.classList.remove('loading');
      const vs = document.createElement('div');
      vs.className = 'verses';
      d.verses.forEach((t, n) => {
        const p = Object.assign(document.createElement('p'), { className: 'verse' + (n ? '' : ' v1') });
        if (n) p.append(Object.assign(document.createElement('sup'), { textContent: n + 1 }));
        p.onclick = () => openNote(m.pid, n + 1);
        let em = false;
        for (const s of t.split(/(<\/?i>)/)) {
          if (s === '<i>') em = true;
          else if (s === '</i>') em = false;
          else if (s) p.append(em ? Object.assign(document.createElement('i'), { textContent: s }) : s);
        }
        vs.append(p);
      });
      text.append(vs);
      layoutNotes(el); 
    });
  }
  layoutNotes(el);
  return el;
}

async function layoutNotes(el) {
  const pid = el.dataset.pid;
  const list = await notes(pid);
  if (el.dataset.pid !== pid || !el.isConnected) return;
  const margin = el.querySelector('.margin-notes');
  margin.querySelectorAll('.note').forEach((n) => n.remove());
  const items = list.map((c) => ({ c, el: noteEl(c, el) }));
  items.forEach((n) => { n.el.style.cssText = 'visibility:hidden;top:0'; margin.append(n.el); });

  const pr = el.getBoundingClientRect();
  const base = margin.getBoundingClientRect().top - pr.top;
  let bottom = -1e9;
  const verseY = (a) => {
    const v = el.querySelector(`.verses .verse:nth-child(${a})`);
    return v ? v.getBoundingClientRect().top - pr.top - base - 8 : null;
  };
  const place = (n, y) => {
    n.y = Math.max(10, y ?? bottom - 7, bottom - 14);
    bottom = n.y + n.el.offsetHeight + 7;
  };
  items.filter((n) => n.c.anchor != null).sort((a, b) => a.c.anchor - b.c.anchor)
    .forEach((n) => place(n, verseY(n.c.anchor)));
  items.filter((n) => n.c.anchor == null).forEach((n) => place(n, bottom - 7));
  items.forEach((n) => { n.el.style.top = n.y + 'px'; n.el.style.visibility = ''; });

  margin.style.minHeight = Math.max(bottom + 70, margin.clientHeight) + 'px';
  margin.querySelector('.note-add').style.top = Math.max(bottom + 16, 10) + 'px';
}

function noteEl(c, page) {
  const n = Object.assign(document.createElement('div'), { className: 'note' });
  n.onclick = () => openNote(c.page, c.anchor, c);
  if (c.anchor != null) {
    const a = Object.assign(document.createElement('span'), { className: 'note-anchor', textContent: 'ст. ' + c.anchor });
    a.onclick = (e) => {
      e.stopPropagation();
      const v = page.querySelector(`.verse:nth-child(${c.anchor})`);
      if (v) {
        v.scrollIntoView({ behavior: 'smooth', block: 'center' });
        v.classList.add('selected');
        setTimeout(() => v.classList.remove('selected'), 1500);
      }
    };
    n.append(a);
  }
  const p = document.createElement('p');
  p.innerHTML = c.text;
  n.append(p, Object.assign(document.createElement('span'), { className: 'note-author', textContent: c.author }));
  return n;
}

function flip(fwd) {
  const ok = fwd ? cursor() < state.total - 1 : state.single ? state.page > 0 : state.spread > 0;
  if (state.busy || !ok) return;
  state.busy = true;
  const mk = (side, i) => fillPage(Object.assign(document.createElement('div'), { className: 'page ' + side }), i);
  const leaf = (front, back) => {
    const l = Object.assign(document.createElement('div'), { className: 'leaf ' + (fwd ? 'fwd' : 'bwd') });
    for (const [cls, child] of [['front', front], ['back', back]]) {
      const f = Object.assign(document.createElement('div'), { className: 'face ' + cls });
      f.append(child);
      l.append(f);
    }
    els.leafLayer.append(l);
  };
  let done;

  if (state.single) {
    const q = state.page + (fwd ? 1 : -1);
    leaf(els.pageR.cloneNode(true), mk('right', q));
    done = () => { state.page = q; fillPage(els.pageR, q); };
  } else {
    const t = state.spread + (fwd ? 1 : -1);
    if (fwd) {
      leaf(els.pageR.cloneNode(true), mk('left', t * 2));
      fillPage(els.pageR, t * 2 + 1);
      done = () => { state.spread = t; fillPage(els.pageL, t * 2); };
    } else {
      leaf(els.pageL.cloneNode(true), mk('right', t * 2 + 1));
      fillPage(els.pageL, t * 2);
      done = () => { state.spread = t; fillPage(els.pageR, t * 2 + 1); };
    }
  }
  setTimeout(() => {
    done();
    els.leafLayer.innerHTML = '';
    state.busy = false;
    updateUI();
  }, flipMs());
}

function jump(i) {
  i = Math.max(0, Math.min(state.total - 1, i));
  if (state.single) { state.page = i; fillPage(els.pageR, i); }
  else {
    state.spread = i >> 1;
    fillPage(els.pageL, state.spread * 2);
    fillPage(els.pageR, state.spread * 2 + 1);
  }
  updateUI();
}

function updateUI() {
  els.prevBtn.disabled = els.cornerL.disabled = !(state.single ? state.page > 0 : state.spread > 0);
  els.nextBtn.disabled = els.cornerR.disabled = !(cursor() < state.total - 1);
  const m = meta(cursor());
  els.positionLabel.textContent = m.title ? 'титульный лист'
    : `${m.name}, глава ${m.ch} · стр. ${cursor()} из ${state.total - 1}`;
  localStorage.setItem('codex.pos', state.single ? state.page : state.spread);
  els.tocBody.querySelectorAll('.current').forEach((r) => r.classList.remove('current'));
  const cur = els.tocBody.querySelector(`.toc-book[data-id="${m.book}"] .toc-book-row`);
  if (cur) cur.classList.add('current');
}

let toastT;
const toast = (msg) => {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (els.toast.hidden = true), 2000);
};
const stats = () => api('/api/stats' + (scope ? '?scope=' + scope : '')).then((s) => (els.stats.textContent = 'заметки: ' + s.total)).catch(() => {});
const closeNote = () => { els.noteModal.hidden = true; state.note = null; };
const refreshNotes = () =>
  [els.pageL, els.pageR].forEach((el) => el.dataset.pid && notes(el.dataset.pid, true).then(() => layoutNotes(el)));

function openNote(pid, anchor, edit) {
  state.note = { pid, anchor, id: edit ? edit.id : null };
  els.noteModalTitle.textContent = edit ? 'Редактирование заметки' : anchor ? 'Заметка к стиху' : 'Заметка на полях';
  els.noteModalRef.textContent = refOf(pid, anchor);
  els.noteAuthor.value = edit ? edit.author : localStorage.getItem('codex.author') || '';
  els.noteText.value = edit ? edit.text : '';
  els.notePreview.innerHTML = els.noteText.value;
  els.noteError.textContent = '';
  els.noteModal.hidden = false;
  if (edit) history.replaceState(null, '', location.pathname + '?note=' + edit.id);
  setTimeout(() => els.noteText.focus(), 30);
}

async function submitNote() {
  const { pid, anchor, id } = state.note || {};
  const author = els.noteAuthor.value.trim();
  const text = els.noteText.value.trim();
  if (!pid) return;
  if (!author) return (els.noteError.textContent = 'Представьтесь');
  if (!text) return (els.noteError.textContent = 'Заметка пуста');
  els.noteSubmit.disabled = true;
  try {
    await api(id ? '/api/comment/' + id : '/api/comments', {
      method: id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(id ? { author, text, scope } : { page: pid, author, text, anchor, scope }),
    });
    localStorage.setItem('codex.author', author);
    closeNote();
    toast(id ? 'Заметка сохранена' : 'Заметка оставлена');
    stats();
    notes(pid, true);
    [els.pageL, els.pageR].forEach((el) => el.dataset.pid === pid && layoutNotes(el));
  } catch (e) {
    els.noteError.textContent = e.message;
  }
  els.noteSubmit.disabled = false;
}

function buildToc(q = '') {
  q = q.trim().toLowerCase();
  els.tocBody.innerHTML = '';
  for (const [test, label] of [['OT', 'Ветхий Завет'], ['NT', 'Новый Завет']]) {
    const found = state.toc.filter((b) => b.testament === test &&
      (!q || b.name.toLowerCase().includes(q) || b.abbrev.toLowerCase().includes(q)));
    if (!found.length) continue;
    const h = Object.assign(document.createElement('div'), { className: 'toc-section', textContent: label });
    els.tocBody.append(h);
    for (const b of found) {
      const wrap = Object.assign(document.createElement('div'), { className: 'toc-book' });
      wrap.dataset.id = b.id;
      const row = Object.assign(document.createElement('button'), { className: 'toc-book-row',
        innerHTML: `<span class="abbr">${b.abbrev}</span><span>${b.name}</span><span class="cnt">${b.chapters}</span>` });
      row.onclick = () => {
        const open = wrap.querySelector('.toc-chapters');
        els.tocBody.querySelectorAll('.toc-chapters').forEach((c) => c.remove());
        if (open) return;
        const grid = Object.assign(document.createElement('div'), { className: 'toc-chapters' });
        for (let c = 1; c <= b.chapters; c++) {
          const btn = Object.assign(document.createElement('button'), { className: 'toc-ch', textContent: c });
          btn.onclick = () => { els.toc.hidden = true; jump(state.ch.findIndex((x) => x.pid === `${b.id}.${c}`) + 1); };
          grid.append(btn);
        }
        wrap.append(grid);
      };
      wrap.append(row);
      els.tocBody.append(wrap);
    }
  }
  updateUI();
}

function applyMode() {
  const was = state.single;
  state.single = mq.matches;
  if (was === state.single) return;
  if (state.single) { state.page = Math.min(state.spread * 2 + 1, state.total - 1); fillPage(els.pageR, state.page); }
  else { state.spread = state.page >> 1; fillPage(els.pageL, state.spread * 2); fillPage(els.pageR, state.spread * 2 + 1); }
  updateUI();
}

function bind() {
  els.nextBtn.onclick = els.cornerR.onclick = () => flip(true);
  els.prevBtn.onclick = els.cornerL.onclick = () => flip(false);
  els.tocBtn.onclick = () => { els.toc.hidden = false; els.tocSearch.focus(); };
  els.tocClose.onclick = els.tocBackdrop.onclick = () => (els.toc.hidden = true);
  els.tocSearch.oninput = () => buildToc(els.tocSearch.value);
  els.visitBtn.onclick = async () => {
    els.visitBtn.disabled = true;
    try {
      await api('/api/visit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: location.href }),
      });
      toast('Бот посетил ссылку');
    } catch (e) { toast(e.message); }
    els.visitBtn.disabled = false;
  };
  els.modeBtn.textContent = scope ? 'Выйти из приватного' : 'Приватный режим';
  els.modeBtn.onclick = () => {
    if (scope) { localStorage.removeItem('codex.uuid'); location.href = '/'; }
    else { localStorage.setItem('codex.uuid', crypto.randomUUID()); location.href = '/' + localStorage.getItem('codex.uuid'); }
  };
  els.noteClose.onclick = closeNote;
  els.noteSubmit.onclick = submitNote;
  els.noteModal.onclick = (e) => { if (e.target === els.noteModal) closeNote(); };
  els.noteText.onkeydown = (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submitNote(); };
  els.noteText.oninput = () => (els.notePreview.innerHTML = els.noteText.value);
  document.onkeydown = (e) => {
    if (e.target.matches('input, textarea')) { if (e.key === 'Escape') closeNote(); return; }
    if (e.key === 'ArrowRight') flip(true);
    else if (e.key === 'ArrowLeft') flip(false);
    else if (e.key === 'Escape') { els.toc.hidden = true; closeNote(); }
  };
  let tx;
  els.book.ontouchstart = (e) => (tx = e.touches[0].clientX);
  els.book.ontouchend = (e) => {
    if (tx != null && Math.abs(e.changedTouches[0].clientX - tx) > 60) flip(e.changedTouches[0].clientX < tx);
    tx = null;
  };
  mq.addEventListener('change', applyMode);
  let t;
  const relayout = () => { clearTimeout(t); t = setTimeout(refreshNotes, 120); };
  document.addEventListener('scroll', (e) => e.target.classList && e.target.classList.contains('verses-wrap') && relayout(), true);
  onresize = relayout;
  setInterval(refreshNotes, 12000);
  setInterval(stats, 30000);
}

(async () => {
  state.toc = await api('/api/books');
  for (const b of state.toc)
    for (let c = 1; c <= b.chapters; c++)
      state.ch.push({ pid: `${b.id}.${c}`, book: b.id, ch: c, name: b.name });
  state.total = state.ch.length + 1;

  state.single = mq.matches;
  const pos = Math.max(0, +localStorage.getItem('codex.pos') || 0);
  if (state.single) state.page = Math.min(pos, state.total - 1);
  else state.spread = Math.min(pos, (state.total - 1) >> 1);
  if (state.single) fillPage(els.pageR, state.page);
  else { fillPage(els.pageL, state.spread * 2); fillPage(els.pageR, state.spread * 2 + 1); }

  buildToc();
  bind();
  updateUI();
  stats();

const nid = new URLSearchParams(location.search).get('note');
  if (nid) api('/api/comment/' + nid + (scope ? '?scope=' + scope : ''))
    .then((c) => {
      jump(c.page === 'title' ? 0 : state.ch.findIndex((x) => x.pid === c.page) + 1);
      openNote(c.page, c.anchor, c);
    })
    .catch(() => toast('Заметка не найдена'));
})();
