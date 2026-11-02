'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = +process.env.PORT || 3000;
const APP = process.env.APP_URL || `http://127.0.0.1:${PORT}`;
const PUBLIC = path.join(__dirname, 'public');
const { books } = require('./data/bible.json');
const byId = new Map(books.map((b) => [b.id, b]));

const CFILE = path.join(__dirname, 'data', 'comments.json');
let comments = [];
try { comments = JSON.parse(fs.readFileSync(CFILE, 'utf8')); } catch {}
let saveTimer;
const saveComments = () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => fs.writeFileSync(CFILE, JSON.stringify(comments, null, 1)), 50);
};

const MIME = {
  '.html': 'text/html', '.css': 'text/css',
  '.js': 'application/javascript', '.json': 'application/json',
};
const json = (res, code, data) => {
  const body = JSON.stringify(data);
  res.writeHead(code, { 'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body), 'Cache-Control': 'no-store' });
  res.end(body);
};
const readBody = (req) => new Promise((ok, err) => {
  let size = 0;
  const chunks = [];
  req.on('data', (c) => (size += c.length) > 1048576 ? (err(new Error('large')), req.destroy()) : chunks.push(c));
  req.on('end', () => ok(Buffer.concat(chunks).toString()));
  req.on('error', err);
});

const PAGE_RE = /^(title|[a-z0-9]+\.\d+)$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const bot = require('./bot');

function api(req, res, url) {
  const { pathname, searchParams } = url;
  const GET = req.method === 'GET', POST = req.method === 'POST';

  if (GET && pathname === '/api/books') {
    return json(res, 200, books.map((b) => ({
      id: b.id, name: b.name, abbrev: b.abbrev,
      testament: b.testament, chapters: b.chapters.length,
    })));
  }

  const m = pathname.match(/^\/api\/chapter\/([a-z0-9]+)\/(\d+)$/);
  if (GET && m) {
    const b = byId.get(m[1]), verses = b && b.chapters[+m[2] - 1];
    return verses ? json(res, 200, { verses }) : json(res, 404, { error: 'Глава не найдена' });
  }

  const n = pathname.match(/^\/api\/comment\/([0-9a-f-]{36})$/);
  const note = n && comments.find((c) => c.id === n[1]);
  if (n && GET) {
    const scope = searchParams.get('scope') || '';
    if (!note || (note.scope || '') !== scope) return json(res, 404, { error: 'Заметка не найдена' });
    return json(res, 200, note);
  }
  if (n && req.method === 'PUT') {
    return readBody(req).then((raw) => {
      const { author = '', text = '', scope } = JSON.parse(raw);
      if (!note || (note.scope || '') !== (scope || '')) return json(res, 404, { error: 'Заметка не найдена' });
      note.author = author.trim();
      note.text = text.trim();
      saveComments();
      json(res, 200, note);
    }).catch(() => json(res, 400, { error: 'Некорректный запрос' }));
  }

  if (GET && pathname === '/api/comments') {
    const page = searchParams.get('page') || '', scope = searchParams.get('scope') || '';
    if (!PAGE_RE.test(page) || (scope && !UUID_RE.test(scope))) return json(res, 400, { error: 'Неверная страница' });
    return json(res, 200, comments.filter((c) => c.page === page && (c.scope || '') === scope)
      .sort((a, b) => (a.anchor || 0) - (b.anchor || 0) || b.createdAt - a.createdAt));
  }

  if (POST && pathname === '/api/comments') {
    return readBody(req).then((raw) => {
      const { page, author = '', text = '', anchor, scope } = JSON.parse(raw);
      if (!PAGE_RE.test(page || '')) return json(res, 400, { error: 'Неверная страница' });
      if (scope && !UUID_RE.test(scope)) return json(res, 400, { error: 'Неверный ключ' });
      if (!author.trim() || author.length > 40) return json(res, 400, { error: 'Имя автора: 1–40 символов' });
      if (!text.trim() || text.length > 2000) return json(res, 400, { error: 'Текст заметки: 1–2000 символов' });
      const note = { id: crypto.randomUUID(), page, author: author.trim(), text: text.trim(),
        anchor: anchor == null ? null : +anchor, scope: scope || null, createdAt: Date.now() };
      comments.push(note);
      saveComments();
      json(res, 201, note);
    }).catch(() => json(res, 400, { error: 'Некорректный запрос' }));
  }

  if (GET && pathname === '/api/stats') {
    const scope = searchParams.get('scope') || '';
    return json(res, 200, { total: comments.filter((c) => (c.scope || '') === scope).length });
  }

  if (POST && pathname === '/api/visit') {
    return readBody(req).then((raw) => {
      let link = null;
      try {
        const u = new URL(JSON.parse(raw).url || '', APP);
        link = APP + u.pathname + u.search;
      } catch {}
      if (!link) return json(res, 400, { error: 'Некорректная ссылка' });
      return bot.visit(link).then(
        () => json(res, 200, { ok: true, message: 'Бот посетил ссылку' }),
        (e) => json(res, 500, { error: 'Бот недоступен: ' + e.message })
      );
    }).catch(() => json(res, 400, { error: 'Некорректный запрос' }));
  }
  json(res, 404, { error: 'Not found' });
}

http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname.startsWith('/api/')) {
    try { api(req, res, url); } catch (e) { console.error(e); json(res, 500, { error: 'Внутренняя ошибка' }); }
    return;
  }
  const rel = url.pathname === '/' || /^[0-9a-f-]{36}$/i.test(url.pathname.slice(1)) ? 'index.html' : url.pathname.slice(1);
  const file = path.join(PUBLIC, rel);
  if (!file.startsWith(PUBLIC + path.sep)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (e, data) => {
    if (e) { res.writeHead(404); return res.end('Not found'); }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Content-Security-Policy': "style-src 'self'; script-src 'self'; base-uri 'self'; object-src 'none'",
    });
    res.end(data);
  });
}).listen(PORT, () => console.log(`Codex: http://localhost:${PORT}`));
