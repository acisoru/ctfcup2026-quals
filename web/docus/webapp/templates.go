package main

// HTML-шаблоны портала. Палитра и типографика повторяют UI Collabora COOL

const baseCSS = `:root {
  --color-primary: #1d2d44;
  --color-accent: #0082c9;
  --color-accent-dark: #006aa3;
  --color-main-background: #f5f5f5;
  --color-main-text: #333333;
  --color-text-muted: #888888;
  --color-border: #e0e0e0;
  --color-border-darker: #bdbdbd;
  --color-background-hover: #f0f0f0;
  --color-background-document: #ffffff;
  --color-topbar: #35537a;
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-main-background);
  color: var(--color-main-text);
  font-family: "Open Sans", "Segoe UI", Arial, system-ui, sans-serif;
  font-size: 13px;
  line-height: 1.4;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes slideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes flashIn { 0% { opacity: 0; transform: translateY(-10px); } 60% { transform: translateY(2px); } 100% { opacity: 1; transform: translateY(0); } }
@keyframes glowPulse {
  0%, 100% { box-shadow: 0 0 0 rgba(0,130,201,.0); }
  50% { box-shadow: 0 0 8px rgba(0,130,201,.55); }
}
.anim-fade { animation: fadeIn .45s ease-out both; }
.anim-slide { animation: slideDown .35s ease-out both; }
.anim-slide-row { animation: slideUp .4s ease-out both; }
.anim-glow { animation: glowPulse 2.2s ease-in-out infinite; }

.topbar {
  background: linear-gradient(to bottom, #3b5a85, var(--color-topbar));
  border-bottom: 1px solid #2a405f;
  box-shadow: 0 1px 3px rgba(0,0,0,.25);
  -webkit-user-select: none;
  user-select: none;
  position: relative;
  z-index: 5;
}
.tb-main { display: flex; align-items: center; gap: 14px; padding: 0 20px; height: 52px; }
.brand { display: flex; align-items: center; gap: 10px; font-size: 17px; font-weight: 700; letter-spacing: -.01em; color: #fff; text-shadow: 0 1px 1px rgba(0,0,0,.35); }
.brand-badge {
  width: 30px; height: 30px; border-radius: 4px;
  background: linear-gradient(to bottom, #339bd6, var(--color-accent));
  border: 1px solid rgba(0,0,0,.25);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.35);
}
.brand small { color: #b9c7da; font-weight: 400; font-size: 12px; margin-left: 2px; text-shadow: none; }
.tb-actions { margin-left: auto; display: flex; gap: 10px; align-items: center; }
.userbox { display: flex; align-items: center; gap: 8px; color: #d6dfe9; font-size: 12.5px; text-shadow: 0 1px 1px rgba(0,0,0,.3); }
.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(to bottom, #339bd6, #1f7cb5);
  border: 1px solid rgba(0,0,0,.3);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.3);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
}
.btn {
  border: 1px solid var(--color-border-darker); border-radius: 3px;
  background: linear-gradient(to bottom, #ffffff, #f1f1f1);
  color: var(--color-main-text);
  font: inherit; padding: 6px 14px; cursor: pointer; text-decoration: none;
  display: inline-block;
  transition: background .15s ease, box-shadow .15s ease;
}
.btn:hover { background: linear-gradient(to bottom, #f6f6f6, #e8e8e8); box-shadow: inset 0 1px 2px rgba(0,0,0,.08); }
.btn.primary {
  background: linear-gradient(to bottom, #339bd6, var(--color-accent));
  border-color: var(--color-accent-dark);
  color: #fff;
  text-shadow: 0 1px 1px rgba(0,0,0,.25);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.3);
}
.btn.primary:hover { background: linear-gradient(to bottom, #2b8cc2, #0075b4); }
.topbar .btn { background: rgba(255,255,255,.12); border-color: rgba(0,0,0,.35); color: #fff; text-shadow: 0 1px 1px rgba(0,0,0,.3); }
.topbar .btn:hover { background: rgba(255,255,255,.22); }

.layout { flex: 1; display: flex; min-height: 0; }
.sidebar {
  width: 230px; flex: none;
  background: var(--color-background-document);
  border-right: 1px solid var(--color-border);
  padding: 16px 10px;
}
.sidebar h3 {
  margin: 0 0 8px; padding: 0 10px;
  font-size: 11px; font-weight: 600; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: .05em;
}
.nav-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; margin: 1px 0; border-radius: 3px;
  color: var(--color-main-text); text-decoration: none; font-size: 13px;
  transition: background .12s ease;
}
.nav-item:hover { background: var(--color-background-hover); }
.nav-item.active {
  background: #e8f4fb; color: var(--color-accent-dark); font-weight: 600;
  box-shadow: inset 2px 0 0 var(--color-accent);
}
.nav-item .icon { color: var(--color-accent); flex: none; }

.nav-item .del {
  margin-left: auto; border: 0; background: none; cursor: pointer;
  color: var(--color-text-muted); font-size: 13px; padding: 0 2px; border-radius: 3px;
}
.nav-item .del:hover { color: #a12622; background: #fdecea; }
.sidebar form.newfolder { display: flex; gap: 6px; padding: 8px 10px 0; }
.sidebar input[type=text] {
  flex: 1; min-width: 0; padding: 6px 8px; font: inherit;
  border: 1px solid var(--color-border-darker); border-radius: 4px;
  background: var(--color-background-document); color: var(--color-main-text);
}
.sidebar input[type=text]:focus { outline: 2px solid var(--color-primary); outline-offset: -1px; border-color: var(--color-primary); }

main.content { flex: 1; padding: 26px 28px; overflow: auto; }
.content-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.content-head h2 { margin: 0; }
.content-head form { display: flex; gap: 8px; margin-left: auto; }
.content-head input[type=text] {
  width: 220px; padding: 6px 10px; font: inherit;
  border: 1px solid var(--color-border-darker); border-radius: 3px;
  background: var(--color-background-document); color: var(--color-main-text);
  box-shadow: inset 0 1px 2px rgba(0,0,0,.06);
}
.content-head input[type=text]:focus { outline: 2px solid var(--color-accent); outline-offset: -1px; border-color: var(--color-accent); }
.doc-row { position: relative; display: flex; align-items: center; gap: 10px; padding: 12px 16px; }
a.doc-link { display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0; color: inherit; text-decoration: none; }
.doc-row:hover > a.doc-link { background: var(--color-background-hover); }
.doc-row form { margin: 0; }
.doc-row .doc-meta { margin-left: auto; color: var(--color-text-muted); font-size: 12px; white-space: nowrap; }
.doc-row .del {
  margin-left: 0; border: 0; background: none; cursor: pointer;
  color: var(--color-text-muted); font-size: 15px; padding: 2px 6px; border-radius: 3px;
}
.doc-row .del:hover { color: #a12622; background: #fdecea; }
.share-btn {
  padding: 3px 10px; border-radius: 3px;
  border: 1px solid var(--color-border-darker);
  background: linear-gradient(to bottom, #ffffff, #f1f1f1);
  color: var(--color-accent-dark); font-size: 11.5px; text-decoration: none;
  white-space: nowrap;
}
.share-btn:hover { background: linear-gradient(to bottom, #f0f6fb, #e2eef7); border-color: var(--color-accent); }
.flash {
  margin: 0 0 12px; padding: 9px 14px; border-radius: 3px; font-size: 12.5px;
  background: #fdecea; border: 1px solid #f5c6c0; color: #a12622;
  animation: flashIn .4s ease-out both;
}
.flash.info { background: #e8f4fb; border-color: #bcdsf0; color: #005d8f; }
h2 {
  margin: 0 0 12px; font-size: 14px; font-weight: 600;
  color: var(--color-text-muted); text-transform: uppercase; letter-spacing: .05em;
}
.docs {
  background: var(--color-background-document);
  border: 1px solid var(--color-border); border-radius: 6px; overflow: hidden;
}
.doc-row { border-bottom: 1px solid var(--color-border); }
.doc-row:last-child { border-bottom: 0; }
.doc-icon {
  flex: none; width: 34px; height: 34px; border-radius: 4px;
  background: #e6f2fc; color: var(--color-primary-dark);
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700;
}
.doc-name { font-weight: 600; font-size: 13.5px; }
.doc-sub { color: var(--color-text-muted); font-size: 12px; }
.doc-meta { margin-left: auto; text-align: right; color: var(--color-text-muted); font-size: 12px; white-space: nowrap; }
.empty { color: var(--color-text-muted); padding: 24px 16px; text-align: center; }

.statusbar {
  display: flex; align-items: center; gap: 16px;
  padding: 5px 16px;
  background: var(--color-background-document);
  border-top: 1px solid var(--color-border);
  color: var(--color-text-muted); font-size: 12px;
  -webkit-user-select: none; user-select: none;
}
.statusbar .sep { color: var(--color-border-darker); }
.statusbar .right { margin-left: auto; display: flex; gap: 16px; }
.saved::before {
  content: ""; display: inline-block; width: 7px; height: 7px;
  border-radius: 50%; background: #2da44e; margin-right: 6px;
}`

const favicon = `<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%230082c9'/%3E%3Ctext x='8' y='11.5' font-size='8' font-weight='700' font-family='Arial' fill='%23fff' text-anchor='middle'%3ED%3C/text%3E%3C/svg%3E">`

func topbarHTML(u User) string {
	initial := "С"
	if len(u.Name) > 0 {
		initial = u.Name[:1]
	}
	return `<header class="topbar"><div class="tb-main">
  <div class="brand"><span class="brand-badge anim-glow">D</span>Docus <small>корпоративный портал документов</small></div>
  <div class="tb-actions">
    <span class="userbox"><span class="avatar">` + initial + `</span>` + u.Name + ` · ` + u.Email + `</span>
    <form method="post" action="/logout" style="margin:0"><button class="btn" type="submit">Выйти</button></form>
  </div>
</div></header>`
}

const indexHTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Docus — Документы</title>
` + favicon + `
<style>` + baseCSS + `</style>
</head>
<body>
__USERBAR__
<div class="layout">
  <nav class="sidebar">
    <h3>Папки</h3>
__NAV__
    <form class="newfolder" method="post" action="/folders/create">
      <input type="text" name="name" placeholder="Новая папка…" autocomplete="off">
      <button class="btn" type="submit" title="Создать папку">+</button>
    </form>
  </nav>
  <main class="content">
    <div class="content-head">
      <h2>__TITLE__</h2>
      <form method="post" action="/docs/create">
        <input type="hidden" name="folder" value="__FOLDER__">
        <input type="text" name="title" placeholder="Новый документ…" autocomplete="off">
        <button class="btn primary" type="submit">Создать</button>
      </form>
    </div>
    __FLASH__
    <div class="docs anim-fade">
__ROWS__
    </div>
  </main>
</div>
<footer class="statusbar">
  <span class="saved">Все изменения сохранены</span>
  <span class="sep">|</span>
  <span>Русский (Россия)</span>
  <div class="right">
    <span>Совместное редактирование: включено</span>
    <span class="sep">|</span>
    <span>100%</span>
  </div>
</footer>
</body>
</html>
`

const loginHTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Docus — вход</title>
` + favicon + `
<style>` + baseCSS + `
.login-wrap { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.login-card {
  width: 360px;
  background: var(--color-background-document);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 28px 30px;
}
.login-card h1 { margin: 0 0 4px; font-size: 19px; }
.login-card .sub { color: var(--color-text-muted); margin: 0 0 20px; font-size: 12.5px; }
.field { margin-bottom: 14px; }
.field label { display: block; margin-bottom: 5px; font-size: 12px; color: var(--color-text-muted); }
.field input {
  width: 100%; padding: 8px 10px;
  border: 1px solid var(--color-border-darker); border-radius: 4px;
  font: inherit; background: var(--color-background-document); color: var(--color-main-text);
}
.field input:focus { outline: 2px solid var(--color-primary); outline-offset: -1px; border-color: var(--color-primary); }
.login-btn { width: 100%; margin-top: 6px; padding: 9px; font-size: 14px; }
.error {
  background: #fdecea; border: 1px solid #f5c6c0; border-radius: 4px;
  color: #a12622; padding: 9px 12px; margin-bottom: 14px; font-size: 12.5px;
}
.hint {
  margin-top: 18px; padding-top: 14px;
  border-top: 1px solid var(--color-border);
  color: var(--color-text-muted); font-size: 11.5px; line-height: 1.6;
}
.hint code { background: var(--color-background-hover); border-radius: 3px; padding: 1px 5px; }
</style>
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <h1>Docus</h1>
    <p class="sub">Войдите корпоративной учётной записью</p>
    __ERROR__
    <form method="post" action="/login">
      <div class="field">
        <label for="email">Рабочая почта</label>
        <input id="email" name="email" type="text" value="__EMAIL__" autofocus autocomplete="username">
      </div>
      <div class="field">
        <label for="password">Пароль</label>
        <input id="password" name="password" type="password" autocomplete="current-password">
      </div>
      <button class="btn primary login-btn" type="submit">Войти</button>
    </form>
    <div class="hint">Нет учётки? <a href="/register">Зарегистрируйтесь</a> — внутренний портал, любая почта <code>@corp</code>.</div>
  </div>
</div>
</body>
</html>
`

const registerHTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Docus — регистрация</title>
` + favicon + `
<style>` + baseCSS + `
.login-wrap { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.login-card {
  width: 360px;
  background: var(--color-background-document);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 28px 30px;
}
.login-card h1 { margin: 0 0 4px; font-size: 19px; }
.login-card .sub { color: var(--color-text-muted); margin: 0 0 20px; font-size: 12.5px; }
.field { margin-bottom: 14px; }
.field label { display: block; margin-bottom: 5px; font-size: 12px; color: var(--color-text-muted); }
.field input {
  width: 100%; padding: 8px 10px;
  border: 1px solid var(--color-border-darker); border-radius: 4px;
  font: inherit; background: var(--color-background-document); color: var(--color-main-text);
}
.field input:focus { outline: 2px solid var(--color-primary); outline-offset: -1px; border-color: var(--color-primary); }
.login-btn { width: 100%; margin-top: 6px; padding: 9px; font-size: 14px; }
.error {
  background: #fdecea; border: 1px solid #f5c6c0; border-radius: 4px;
  color: #a12622; padding: 9px 12px; margin-bottom: 14px; font-size: 12.5px;
}
.hint {
  margin-top: 18px; padding-top: 14px;
  border-top: 1px solid var(--color-border);
  color: var(--color-text-muted); font-size: 11.5px; line-height: 1.6;
}
.hint a { color: var(--color-accent-dark); }
</style>
</head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <h1>Docus</h1>
    <p class="sub">Новая учётная запись сотрудника</p>
    __ERROR__
    <form method="post" action="/register">
      <div class="field">
        <label for="email">Рабочая почта</label>
        <input id="email" name="email" type="text" value="__EMAIL__" placeholder="ivanov@corp" autofocus autocomplete="username">
      </div>
      <div class="field">
        <label for="name">Как показывать имя коллегам</label>
        <input id="name" name="name" type="text" value="__NAME__" placeholder="Иван Иванов" autocomplete="name">
      </div>
      <div class="field">
        <label for="password">Пароль</label>
        <input id="password" name="password" type="password" autocomplete="new-password">
      </div>
      <button class="btn primary login-btn" type="submit">Создать учётную запись</button>
    </form>
    <div class="hint">Уже есть доступ? <a href="/login">Войти</a></div>
  </div>
</div>
</body>
</html>
`

const shareHTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Docus — Поделиться</title>
` + favicon + `
<style>` + baseCSS + `
table.share { width: 100%; border-collapse: collapse; background: var(--color-background-document); border: 1px solid var(--color-border); border-radius: 6px; overflow: hidden; }
table.share th, table.share td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--color-border); font-size: 13px; }
table.share th { background: var(--color-background-tabs-group); color: var(--color-text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
.unshare { border: 0; background: none; color: var(--color-primary); cursor: pointer; font: inherit; font-size: 12px; padding: 0; text-decoration: underline; }
.unshare:hover { color: var(--color-primary-dark); }
.share-form { display: flex; gap: 8px; align-items: center; margin: 14px 0; flex-wrap: wrap; }
.share-form input[type=text] {
  width: 280px; padding: 7px 10px; font: inherit;
  border: 1px solid var(--color-border-darker); border-radius: 4px;
  background: var(--color-background-document); color: var(--color-main-text);
}
.share-form input[type=text]:focus { outline: 2px solid var(--color-accent); outline-offset: -1px; border-color: var(--color-accent); }
.share .member, .share .pending { font-size: 11px; border-radius: 3px; padding: 2px 7px; white-space: nowrap; }
.share .member { background: #e6f2fc; color: var(--color-accent-dark); }
.share .pending { background: #fdf3e0; border: 1px solid #f0ddb8; color: #8a6d3b; }
.share-form label { display: flex; gap: 6px; align-items: center; color: var(--color-text-muted); font-size: 12.5px; }
.back { display: inline-block; margin-bottom: 14px; color: var(--color-primary); text-decoration: none; font-size: 13px; }
.back:hover { text-decoration: underline; }
</style>
</head>
<body>
__USERBAR__
<div class="layout">
  <nav class="sidebar">
    <h3>Папки</h3>
__NAV__
  </nav>
  <main class="content">
    <a class="back" href="/">← Ко всем документам</a>
    <h2>__TITLE__</h2>
    __FLASH__
    <form class="share-form" method="post" action="/share/create">
      <input type="hidden" name="doc" value="__DOC__">
      <input type="text" name="to" placeholder="почта коллеги, например petrov@corp" autocomplete="off">
      <label><input type="checkbox" name="canedit"> может редактировать</label>
      <button class="btn primary" type="submit">Поделиться</button>
    </form>
    <table class="share">
      <thead><tr><th>Кому</th><th>Доступ</th><th>Статус</th><th></th></tr></thead>
      <tbody>
__ROWS__
      </tbody>
    </table>
  </main>
</div>
</body>
</html>
`

const editorHTML = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Docus — редактор</title>
` + favicon + `
<style>` + baseCSS + `
.editbar {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 14px;
  background: var(--color-background-document);
  border-bottom: 1px solid var(--color-border);
  -webkit-user-select: none; user-select: none;
}
.editbar .crumbs { font-size: 12.5px; color: var(--color-text-muted); }
.editbar .crumbs a { color: var(--color-accent-dark); text-decoration: none; }
.editbar .crumbs a:hover { text-decoration: underline; }
.editbar .doc-title { font-weight: 600; color: var(--color-main-text); }
html, body { margin: 0; height: 100%; overflow: hidden; }
body { display: flex; flex-direction: column; }
iframe { border: 0; width: 100%; flex: 1; }
</style>
</head>
<body>
<div class="editbar">
  <span class="crumbs"><a href="__BACK_URL__">Все документы</a> / <span class="doc-title">__DOC_TITLE__</span></span>
</div>
<iframe src="__FRAME_URL__" allow="clipboard-read; clipboard-write"></iframe>
<script>
window.addEventListener("message", function (e) {
  var msg = e.data;
  if (typeof msg === "string") { try { msg = JSON.parse(msg); } catch (err) { return; } }
  if (msg && msg.MessageId === "close") { location.href = "__BACK_URL__"; }
});
</script>
</body>
</html>
`
