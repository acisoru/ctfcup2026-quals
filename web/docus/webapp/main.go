// docus webapp: "корпоративный портал документов" — фронтенд таски.
//
// Аутентификация (сессии в cookie), папки с документами, WOPI-эндпоинты
// для Collabora и прокси /cool/*, /browser/*, /hosting/* в контейнер
// collabora, чтобы редактор открывался прямо со страницы портала.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
)

const (
	listenAddr = ":8000"
	collabURL  = "http://collabora:9980"
	docExt     = "txt" // без точки; так extension записан в discovery
	// адрес webapp с точки зрения collabora (docker-сеть)
	wopiInternalHost = "webapp:8000"
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/login", handleLogin)
	mux.HandleFunc("/register", handleRegister)
	mux.HandleFunc("/logout", handleLogout)
	mux.HandleFunc("/", requireAuth(handleIndex))
	mux.HandleFunc("/folders/create", requireAuth(handleFolderCreate))
	mux.HandleFunc("/folders/delete", requireAuth(handleFolderDelete))
	mux.HandleFunc("/docs/create", requireAuth(handleDocCreate))
	mux.HandleFunc("/docs/delete", requireAuth(handleDocDelete))
	mux.HandleFunc("/share", requireAuth(handleShare))
	mux.HandleFunc("/share/create", requireAuth(handleSharePost))
	mux.HandleFunc("/share/delete", requireAuth(handleShareDelete))
	mux.HandleFunc("/shared", requireAuth(handleShared))
	mux.HandleFunc("/edit/", requireAuth(handleEdit))
	mux.HandleFunc("/wopi/files/", handleWOPIFiles)
	mux.Handle("/cool/", proxyCool())
	mux.Handle("/browser/", proxyCool())
	mux.Handle("/hosting/", proxyCool())

	srv := &http.Server{
		Addr:              listenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}
	log.Printf("docus webapp on %s", listenAddr)
	if err := srv.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}

func flash(r *http.Request) string {
	switch r.URL.Query().Get("m") {
	case "folder-exists":
		return "Папка с таким названием уже есть"
	case "folder-not-empty":
		return "Папка не пуста — сначала удалите документы"
	case "folder-deleted":
		return "Папка удалена"
	case "doc-deleted":
		return "Документ удалён"
	case "doc-forbidden":
		return "Чужие документы удалять нельзя"
	case "doc-created":
		return "Документ создан"
	case "doc-invalid":
		return "Не удалось создать документ: пустое название или папка не существует"
	case "folder-created":
		return "Папка создана"
	case "share-ok":
		return "Документ расшарен"
	case "share-bad":
		return "Введите корректную рабочую почту вида name@corp"
	case "share-exists":
		return "Этому пользователю документ уже расшарен"
	case "share-forbidden":
		return "Шарить можно только свои документы"
	case "share-deleted":
		return "Доступ отозван"
	}
	return ""
}

func handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	user, _ := currentUser(r)
	folderID := r.URL.Query().Get("folder")

	title := "Все документы"
	nav := strings.Replace(navHTML(""),
		`<a class="nav-item" href="/shared">`,
		foldersNavHTML(folderID, user.Email)+`<a class="nav-item" href="/shared">`, 1)

	rows := ""
	for _, d := range store.DocsIn(folderID) {
		rows += docRow(d, user)
	}
	if rows == "" {
		rows = `<div class="empty">В этой папке пока нет документов</div>`
	}

	page := strings.Replace(indexHTML, "__NAV__", nav, 1)
	page = strings.Replace(page, "__TITLE__", title, 1)
	page = strings.Replace(page, "__ROWS__", rows, 1)
	page = strings.Replace(page, "__USERBAR__", topbarHTML(user), 1)
	page = strings.Replace(page, "__FOLDER__", html.EscapeString(folderID), 1)
	page = strings.Replace(page, "__FLASH__", flashBlock(r), 1)
	fmt.Fprint(w, page)
}

func flashBlock(r *http.Request) string {
	msg := flash(r)
	if msg == "" {
		return ""
	}
	cls := "flash"
	switch r.URL.Query().Get("m") {
	case "folder-deleted", "doc-deleted", "doc-created", "folder-created",
		"share-ok", "share-deleted":
		cls += " info"
	}
	return `<div class="` + cls + `">` + msg + `</div>`
}

func activeClass(active bool) string {
	if active {
		return ` active`
	}
	return ""
}

func docRow(d Doc, user User) string {
	delay := fmt.Sprintf("%d", (len(d.ID)*7)%210)
	// строка — div: форму нельзя вложить в <a>
	row := `<div class="doc-row anim-slide-row" style="animation-delay:` + delay + `ms">` +
		`<a class="doc-link" href="/edit/` + d.ID + `">` +
		`<span class="doc-icon">TXT</span>` +
		`<span><span class="doc-name">` + html.EscapeString(d.Title) + `</span><br>` +
		`<span class="doc-sub">` + html.EscapeString(d.Owner) + `</span></span>` +
		`<span class="doc-meta">изменён ` + d.Updated + `</span></a>`
	if d.Owner == user.Email {
		row += `<a class="share-btn" href="/share?doc=` + d.ID + `" title="Поделиться">Поделиться</a>` +
			`<form method="post" action="/docs/delete">` +
			`<input type="hidden" name="id" value="` + d.ID + `">` +
			`<input type="hidden" name="folder" value="` + d.Folder + `">` +
			`<button class="del" type="submit" title="Удалить документ">×</button></form>`
	}
	return row + `</div>`
}

func handleFolderCreate(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	_, err := store.CreateFolder(r.PostFormValue("name"), user.Email)
	if err != nil {
		redirectWith(w, r, "/?m=folder-exists")
		return
	}
	redirectWith(w, r, "/?m=folder-created")
}

func handleFolderDelete(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	err := store.DeleteFolder(r.PostFormValue("id"))
	if errors.Is(err, errNotEmpty) {
		redirectWith(w, r, "/?m=folder-not-empty")
		return
	}
	redirectWith(w, r, "/?m=folder-deleted")
}

func handleDocCreate(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	doc, err := store.CreateDoc(r.PostFormValue("title"), r.PostFormValue("folder"), user.Email)
	if err != nil {
		redirectWith(w, r, "/?m=doc-invalid")
		return
	}
	http.Redirect(w, r, "/edit/"+doc.ID, http.StatusSeeOther)
}

func handleDocDelete(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	id := r.PostFormValue("id")
	back := "/?m=doc-deleted"
	if folder := r.PostFormValue("folder"); folder != "" {
		back = "/?folder=" + url.QueryEscape(folder) + "&m=doc-deleted"
	}
	if !store.DeleteDoc(id, user.Email) {
		redirectWith(w, r, strings.Replace(back, "doc-deleted", "doc-forbidden", 1))
		return
	}
	redirectWith(w, r, back)
}

func redirectWith(w http.ResponseWriter, r *http.Request, target string) {
	http.Redirect(w, r, target, http.StatusSeeOther)
}

func handleShare(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	docID := r.URL.Query().Get("doc")
	doc, ok := store.DocByID(docID)
	if !ok || doc.Owner != user.Email {
		redirectWith(w, r, "/?m=share-forbidden")
		return
	}
	title := "Поделиться: " + doc.Title
	nav := navHTML("")
	rows := ""
	for _, sh := range store.SharesByDoc(doc.ID) {
		cls := "только просмотр"
		if sh.CanEdit {
			cls = "может редактировать"
		}
		status := `<span class="pending">приглашён — зарегистрируется с этой почтой</span>`
		if _, known := userByEmail(sh.To); known {
			status = `<span class="member">участник</span>`
		}
		rows += `<tr><td>` + html.EscapeString(sh.To) + `</td><td>` + cls + `</td><td>` + status + `</td>` +
			`<td><form method="post" action="/share/delete" style="display:inline">` +
			`<input type="hidden" name="doc" value="` + doc.ID + `">` +
			`<input type="hidden" name="to" value="` + html.EscapeString(sh.To) + `">` +
			`<button class="unshare" type="submit">отозвать</button></form></td></tr>`
	}
	if rows == "" {
		rows = `<tr><td colspan="4" class="empty">Пока ни с кем не расшарено</td></tr>`
	}
	page := strings.Replace(shareHTML, "__TITLE__", html.EscapeString(title), 1)
	page = strings.Replace(page, "__USERBAR__", topbarHTML(user), 1)
	page = strings.Replace(page, "__NAV__", nav, 1)
	page = strings.Replace(page, "__ROWS__", rows, 1)
	page = strings.Replace(page, "__DOC__", doc.ID, 1)
	page = strings.Replace(page, "__FLASH__", flashBlock(r), 1)
	fmt.Fprint(w, page)
}

func handleShareDelete(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	store.RemoveShare(r.PostFormValue("doc"), r.PostFormValue("to"), user.Email)
	back := "/share?doc=" + url.QueryEscape(r.PostFormValue("doc")) + "&m=share-deleted"
	if r.PostFormValue("to") == user.Email {
		back = "/shared?m=share-deleted"
	}
	redirectWith(w, r, back)
}

func handleShared(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	title := "Мне расшарено"
	nav := navHTML("shared")
	rows := ""
	for _, sh := range store.SharesFor(user.Email) {
		cls := "просмотр"
		if sh.CanEdit {
			cls = "редактирование"
		}
		rows += `<div class="doc-row anim-slide-row"><a class="doc-link" href="/edit/` + sh.DocID + `">` +
			`<span class="doc-icon">TXT</span>` +
			`<span><span class="doc-name">` + html.EscapeString(sh.Title) + `</span><br>` +
			`<span class="doc-sub">от ` + html.EscapeString(sh.From) + ` · ` + cls + `</span></span>` +
			`<span class="doc-meta"></span></a>` +
			`<form method="post" action="/share/delete">` +
			`<input type="hidden" name="doc" value="` + sh.DocID + `">` +
			`<input type="hidden" name="to" value="` + user.Email + `">` +
			`<button class="del" type="submit" title="Убрать из «Мне расшарено»">×</button></form></div>`
	}
	if rows == "" {
		rows = `<div class="empty">Никто пока не поделился с вами документами</div>`
	}
	page := strings.Replace(indexHTML, "__NAV__", nav, 1)
	page = strings.Replace(page, "__TITLE__", title, 1)
	page = strings.Replace(page, "__ROWS__", rows, 1)
	page = strings.Replace(page, "__USERBAR__", topbarHTML(user), 1)
	page = strings.Replace(page, "__FOLDER__", "", 1)
	page = strings.Replace(page, "__FLASH__", flashBlock(r), 1)
	// кнопка «Создать документ» на этой странице не нужна
	page = strings.Replace(page,
		`<form method="post" action="/docs/create">`, `<form style="display:none">`, 1)
	fmt.Fprint(w, page)
}

// navHTML — сайдбар без папок; extra == "shared" активирует пункт шары.
func navHTML(extra string) string {
	nav := `<a class="nav-item` + activeClass(extra != "shared") + `" href="/"><span class="icon">▣</span>Все документы</a>`
	nav += `<a class="nav-item` + activeClass(extra == "shared") +
		`" href="/shared"><span class="icon">✦</span>Мне расшарено</a>`
	return nav
}

// foldersNavHTML — пункты папок с кнопками удаления своих.
func foldersNavHTML(activeFolder, email string) string {
	out := ""
	for _, f := range store.Folders() {
		del := ""
		if f.Owner == email {
			del = `<form method="post" action="/folders/delete" style="display:contents">` +
				`<input type="hidden" name="id" value="` + f.ID + `">` +
				`<button class="del" type="submit" title="Удалить папку">×</button></form>`
		}
		out += `<a class="nav-item` + activeClass(activeFolder == f.ID) +
			`" href="/?folder=` + url.QueryEscape(f.ID) +
			`"><span class="icon">▤</span>` + html.EscapeString(f.Name) + del + `</a>`
	}
	return out
}

func handleSharePost(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	docID := r.PostFormValue("doc")
	back := func(m string) string {
		return "/share?doc=" + url.QueryEscape(docID) + "&m=" + m
	}
	canEdit := r.PostFormValue("canedit") == "on"
	err := store.AddShare(docID, user.Email, r.PostFormValue("to"), canEdit)
	switch {
	case errors.Is(err, errShareExists):
		redirectWith(w, r, back("share-exists"))
	case err != nil:
		redirectWith(w, r, back("share-bad"))
	default:
		redirectWith(w, r, back("share-ok"))
	}
}

func handleEdit(w http.ResponseWriter, r *http.Request) {
	user, _ := currentUser(r)
	docID := strings.TrimPrefix(r.URL.Path, "/edit/")
	doc, ok := store.DocByID(docID)
	if !ok {
		http.NotFound(w, r)
		return
	}
	canEdit, ok := store.CanAccess(user.Email, docID)
	if !ok {
		http.NotFound(w, r)
		return
	}
	resp, err := http.Get(collabURL + "/hosting/discovery")
	if err != nil {
		http.Error(w, "collabora discovery failed", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	actionURL, ok := parseDiscovery(string(body), docExt)
	if !ok {
		http.Error(w, "discovery parse failed", http.StatusBadGateway)
		return
	}
	// WOPISrc Collabora резолвит из своей сети, токен — WOPI access_token
	token := accessToken(user.Email, doc.ID)
	perm := "view"
	if canEdit {
		perm = "edit"
	}
	// closebutton: клик по крестику шлёт родителю postMessage "close"
	frameURL := actionURL + "WOPISrc=" + url.QueryEscape(wopiSrc(doc.ID)) +
		"&access_token=" + url.QueryEscape(token) + "&permission=" + perm +
		"&closebutton=true"
	// urlsrc указывает на origin collabora — снаружи он проксируется webapp'ом,
	// поэтому абсолютный origin заменяем на относительный путь.
	frameURL = strings.ReplaceAll(frameURL, "https://collabora:9980", "")
	frameURL = strings.ReplaceAll(frameURL, "http://collabora:9980", "")
	page := strings.Replace(editorHTML, "__FRAME_URL__", frameURL, 1)
	page = strings.Replace(page, "__DOC_URL__", "/edit/"+doc.ID, 1)
	page = strings.ReplaceAll(page, "__BACK_URL__", backURL(doc))
	page = strings.Replace(page, "__DOC_TITLE__", html.EscapeString(doc.Title), 1)
	fmt.Fprint(w, page)
}

func backURL(doc Doc) string {
	if doc.Folder == "" {
		return "/"
	}
	return "/?folder=" + url.QueryEscape(doc.Folder)
}

// proxyCool — обратный прокси в Collabora. Host не переписываем: coolwsd
// строит WS-URL из заголовка Host, и браузер должен получать свой
// оригинальный хост (иначе получит wss://collabora:9980, который снаружи
// не резолвится).
func proxyCool() http.Handler {
	target, _ := url.Parse(collabURL)
	return httputil.NewSingleHostReverseProxy(target)
}

func wopiSrc(docID string) string {
	return fmt.Sprintf("http://%s/wopi/files/%s", wopiInternalHost, docID)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("write json: %v", err)
	}
}

// handleWOPIFiles — WOPI: GET без /contents — CheckFileInfo,
// POST /contents — PutFile. Collabora ходит сюда из своей сети
// с access_token из URL фрейма.
func handleWOPIFiles(w http.ResponseWriter, r *http.Request) {
	docID := strings.TrimPrefix(r.URL.Path, "/wopi/files/")
	docID = strings.SplitN(docID, "/", 2)[0]
	doc, ok := store.DocByID(docID)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "no such document"})
		return
	}
	user, ok := userFromToken(r.URL.Query().Get("access_token"), doc.ID)
	if !ok {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid access token"})
		return
	}
	canEdit, _ := store.CanAccess(user.Email, doc.ID)
	isContents := strings.HasSuffix(r.URL.Path, "/contents")
	switch {
	case isContents && r.Method == http.MethodGet:
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		if _, err := io.WriteString(w, doc.Content); err != nil {
			log.Printf("write contents: %v", err)
		}
	case isContents && r.Method == http.MethodPost:
		// X-COOL-WOPI-LastModifiedTime обязателен, иначе coolwsd после каждого
		// сохранения считает хранилище изменившимся и показывает конфликт.
		b, _ := io.ReadAll(r.Body)
		version, ok := store.SaveDoc(doc.ID, string(b))
		if !ok {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "save failed"})
			return
		}
		log.Printf("PutFile %s: %d bytes", doc.ID, len(b))
		w.Header().Set("X-COOL-WOPI-LastModifiedTime", version)
		w.Header().Set("X-COOL-WOPI-ItemId", doc.ID)
		writeJSON(w, http.StatusOK, map[string]string{})
	case !isContents && r.Method == http.MethodGet:
		writeJSON(w, http.StatusOK, map[string]any{
			"BaseFileName":     doc.Title,
			"Size":             len(doc.Content),
			"OwnerId":          doc.Owner,
			"UserId":           user.Email,
			"UserFriendlyName": user.Name,
			"UserCanWrite":     canEdit,
			"IsAnonymousUser":  false,
			"LastModifiedTime": store.DocVersion(doc.ID),
			"DisableCopy":      true,
			"DisableExport":    true,
			"DisablePrint":     true,
		})
	default:
		w.WriteHeader(http.StatusMethodNotAllowed)
	}
}

func parseDiscovery(xml, ext string) (string, bool) {
	needle := fmt.Sprintf(`ext="%s"`, ext)
	rest := xml
	for {
		idx := strings.Index(rest, needle)
		if idx < 0 {
			return "", false
		}
		rel := rest[idx:]
		tagEnd := strings.Index(rel, ">")
		if tagEnd < 0 {
			return "", false
		}
		tag := rel[:tagEnd]
		rest = rel[tagEnd:]
		if !strings.Contains(tag, `name="edit"`) {
			continue
		}
		urlIdx := strings.Index(tag, `urlsrc="`)
		if urlIdx < 0 {
			return "", false
		}
		val := tag[urlIdx+len(`urlsrc="`):]
		return val[:strings.Index(val, `"`)], true
	}
}
