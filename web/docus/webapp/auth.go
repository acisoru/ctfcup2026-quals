package main

// Аутентификация портала: корпоративные учётки, сессии в cookie,
// WOPI access_token (HMAC от user+doc — как положено в WOPI, Collabora
// ходит на CheckFileInfo без cookie портала, только с токеном).

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"html"
	"net/http"
	"os"
	"strings"
	"sync"
)

type User struct {
	Email    string
	Name     string
	Password string
}

var users []User

// usersMu защищает users: регистрация и шеры читают список конкурентно.
var usersMu sync.RWMutex

var (
	errEmailTaken  = errors.New("такая почта уже зарегистрирована")
	errEmailFormat = errors.New("ведите корректную рабочую почту вида name@corp")
)

func validCorpEmail(email string) bool {
	return strings.HasSuffix(email, "@corp") &&
		strings.Count(email, "@") == 1 &&
		len(email) > len("@corp")
}

func registerUser(email, name, password string) (User, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	name = strings.TrimSpace(name)
	if !validCorpEmail(email) {
		return User{}, errEmailFormat
	}
	if name == "" {
		name = strings.SplitN(email, "@", 2)[0]
	}
	usersMu.Lock()
	defer usersMu.Unlock()
	for _, u := range users {
		if u.Email == email {
			return User{}, errEmailTaken
		}
	}
	u := User{Email: email, Name: name, Password: password}
	users = append(users, u)
	return u, nil
}

func userByEmail(email string) (User, bool) {
	usersMu.RLock()
	defer usersMu.RUnlock()
	for _, u := range users {
		if u.Email == email {
			return u, true
		}
	}
	return User{}, false
}

var wopiSecret = []byte("docus-wopi-v1")

const sessionCookie = "docus_session"

var sessions = struct {
	sync.Mutex
	m map[string]string // token -> email
}{m: map[string]string{}}

func init() {
	if v := os.Getenv("WOPI_SECRET"); v != "" {
		wopiSecret = []byte(v)
	}
}

func allUsers() []User {
	usersMu.RLock()
	defer usersMu.RUnlock()
	return append([]User(nil), users...)
}

func authenticate(email, password string) (User, bool) {
	usersMu.RLock()
	defer usersMu.RUnlock()
	for _, u := range users {
		if u.Email != email {
			continue
		}
		if subtle.ConstantTimeCompare([]byte(u.Password), []byte(password)) == 1 {
			return u, true
		}
	}
	return User{}, false
}

func createSession(email string) string {
	b := make([]byte, 24)
	if _, err := rand.Read(b); err != nil {
		panic("rand: " + err.Error())
	}
	tok := base64.RawURLEncoding.EncodeToString(b)
	sessions.Lock()
	sessions.m[tok] = email
	sessions.Unlock()
	return tok
}

func dropSession(token string) {
	sessions.Lock()
	delete(sessions.m, token)
	sessions.Unlock()
}

func currentUser(r *http.Request) (User, bool) {
	c, err := r.Cookie(sessionCookie)
	if err != nil {
		return User{}, false
	}
	sessions.Lock()
	email, ok := sessions.m[c.Value]
	sessions.Unlock()
	if !ok {
		return User{}, false
	}
	return userByEmail(email)
}

func requireAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if _, ok := currentUser(r); !ok {
			http.Redirect(w, r, "/login", http.StatusSeeOther)
			return
		}
		next(w, r)
	}
}

// accessToken — WOPI access_token: HMAC от "email|docID".
func accessToken(email, docID string) string {
	mac := hmac.New(sha256.New, wopiSecret)
	mac.Write([]byte(email + "|" + docID))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func userFromToken(token, docID string) (User, bool) {
	if token == "" {
		return User{}, false
	}
	for _, u := range allUsers() {
		want := accessToken(u.Email, docID)
		if subtle.ConstantTimeCompare([]byte(want), []byte(token)) == 1 {
			return u, true
		}
	}
	return User{}, false
}

func handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		renderLogin(w, "", "", http.StatusOK)
		return
	}
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	email := strings.TrimSpace(r.PostFormValue("email"))
	user, ok := authenticate(email, r.PostFormValue("password"))
	if !ok {
		renderLogin(w, email, "Неверная почта или пароль", http.StatusUnauthorized)
		return
	}
	startSession(w, user)
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

func startSession(w http.ResponseWriter, user User) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookie,
		Value:    createSession(user.Email),
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	})
}

func handleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		renderRegister(w, registerForm{}, http.StatusOK)
		return
	}
	if err := r.ParseForm(); err != nil {
		http.Error(w, "bad form", http.StatusBadRequest)
		return
	}
	f := registerForm{
		Email: strings.TrimSpace(r.PostFormValue("email")),
		Name:  strings.TrimSpace(r.PostFormValue("name")),
	}
	password := r.PostFormValue("password")
	if len(password) < 4 {
		f.Error = "Пароль — минимум 4 символа"
		renderRegister(w, f, http.StatusBadRequest)
		return
	}
	user, err := registerUser(f.Email, f.Name, password)
	if errors.Is(err, errEmailTaken) {
		f.Error = "Такая почта уже зарегистрирована"
		renderRegister(w, f, http.StatusConflict)
		return
	}
	if err != nil {
		f.Error = "Введите почту вида name@corp"
		renderRegister(w, f, http.StatusBadRequest)
		return
	}
	startSession(w, user)
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

type registerForm struct {
	Email string
	Name  string
	Error string
}

func handleLogout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}
	if c, err := r.Cookie(sessionCookie); err == nil {
		dropSession(c.Value)
	}
	http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: "", Path: "/", MaxAge: -1})
	http.Redirect(w, r, "/login", http.StatusSeeOther)
}

func renderLogin(w http.ResponseWriter, email, errMsg string, status int) {
	page := strings.Replace(loginHTML, "__EMAIL__", html.EscapeString(email), 1)
	page = strings.Replace(page, "__ERROR__", errorBlock(errMsg), 1)
	w.WriteHeader(status)
	fmt.Fprint(w, page)
}

func renderRegister(w http.ResponseWriter, f registerForm, status int) {
	page := strings.Replace(registerHTML, "__EMAIL__", html.EscapeString(f.Email), 1)
	page = strings.Replace(page, "__NAME__", html.EscapeString(f.Name), 1)
	page = strings.Replace(page, "__ERROR__", errorBlock(f.Error), 1)
	w.WriteHeader(status)
	fmt.Fprint(w, page)
}

func errorBlock(msg string) string {
	if msg == "" {
		return ""
	}
	return `<div class="error">` + msg + `</div>`
}
