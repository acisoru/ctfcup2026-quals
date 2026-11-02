package main

// Данные портала: папки и документы в памяти (demo-режим).
// Все мутации идут через docStore с мьютексом — обработчики конкурентны.

import (
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

type Doc struct {
	ID      string
	Folder  string // ID папки, "" — корень
	Title   string
	Owner   string
	Updated string
	Version string // WOPI LastModifiedTime: меняется только при сохранении
	Content string
}

type Folder struct {
	ID    string
	Name  string
	Owner string
}

type docStore struct {
	mu      sync.Mutex
	folders []Folder
	docs    []Doc
	shares  []Share
	seq     int
}

// Share — from открыл docID пользователю to.
type Share struct {
	DocID   string
	From    string
	To      string
	CanEdit bool
}

type SharedDoc struct {
	Share
	Title string
}

var store = &docStore{}

var (
	errNotFound    = errors.New("не найдено")
	errNotEmpty    = errors.New("папка не пуста")
	errExists      = errors.New("папка с таким названием уже есть")
	errShareBad    = errors.New("нет такого пользователя")
	errShareExists = errors.New("уже расшарено этому пользователю")
)

func today() string { return time.Now().Format("2006-01-02") }

// wopiTimeFormat — coolwsd парсит только ISO8601 с дробными секундами.
const wopiTimeFormat = "2006-01-02T15:04:05.000000Z"

func wopiNow() string { return time.Now().UTC().Format(wopiTimeFormat) }

func wopiAt(date string) string {
	t, err := time.Parse("2006-01-02", date)
	if err != nil {
		return wopiNow()
	}
	return t.UTC().Format(wopiTimeFormat)
}

func (s *docStore) Folders() []Folder {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Folder, len(s.folders))
	copy(out, s.folders)
	return out
}

func (s *docStore) DocsIn(folderID string) []Doc {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Doc
	for _, d := range s.docs {
		if d.Folder == folderID {
			out = append(out, d)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Title < out[j].Title })
	return out
}

func (s *docStore) DocByID(id string) (Doc, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, d := range s.docs {
		if d.ID == id {
			return d, true
		}
	}
	return Doc{}, false
}

func (s *docStore) CreateFolder(name, owner string) (Folder, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return Folder{}, errors.New("введите название папки")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, f := range s.folders {
		if strings.EqualFold(f.Name, name) {
			return Folder{}, errExists
		}
	}
	s.seq++
	f := Folder{ID: fmt.Sprintf("f%d", s.seq), Name: name, Owner: owner}
	s.folders = append(s.folders, f)
	return f, nil
}

func (s *docStore) CreateDoc(title, folderID, owner string) (Doc, error) {
	title = strings.TrimSpace(title)
	if title == "" {
		return Doc{}, errors.New("введите название документа")
	}
	if !strings.HasSuffix(strings.ToLower(title), "."+docExt) {
		title += "." + docExt
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if folderID != "" {
		if _, ok := s.folderLocked(folderID); !ok {
			return Doc{}, errNotFound
		}
	}
	s.seq++
	d := Doc{ID: fmt.Sprintf("d%d", s.seq), Folder: folderID, Title: title, Owner: owner, Updated: today(), Version: wopiNow()}
	s.docs = append(s.docs, d)
	return d, nil
}

func (s *docStore) folderLocked(id string) (Folder, bool) {
	for _, f := range s.folders {
		if f.ID == id {
			return f, true
		}
	}
	return Folder{}, false
}

// DeleteDoc: вместе с документом удаляются его шары.
func (s *docStore) DeleteDoc(id, user string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	for i, d := range s.docs {
		if d.ID == id {
			if d.Owner != user {
				return false
			}
			s.docs = append(s.docs[:i], s.docs[i+1:]...)
			out := s.shares[:0]
			for _, sh := range s.shares {
				if sh.DocID != id {
					out = append(out, sh)
				}
			}
			s.shares = out
			return true
		}
	}
	return false
}

// CanAccess — может ли email работать с документом и в каком режиме.
// Внутренние документы читать может любой сотрудник; редактировать —
// владелец или получатель шары «может редактировать».
func (s *docStore) CanAccess(email, docID string) (canEdit, ok bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, d := range s.docs {
		if d.ID != docID {
			continue
		}
		if d.Owner == email {
			return true, true
		}
		for _, sh := range s.shares {
			if sh.DocID == docID && sh.To == email {
				return sh.CanEdit, true
			}
		}
		return false, true
	}
	return false, false
}

func (s *docStore) SharesFor(email string) []SharedDoc {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []SharedDoc
	for _, sh := range s.shares {
		if sh.To != email {
			continue
		}
		for _, d := range s.docs {
			if d.ID == sh.DocID {
				out = append(out, SharedDoc{Share: sh, Title: d.Title})
				break
			}
		}
	}
	return out
}

func (s *docStore) SharesByDoc(docID string) []Share {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Share
	for _, sh := range s.shares {
		if sh.DocID == docID {
			out = append(out, sh)
		}
	}
	return out
}

// Получатель шара может быть ещё не зарегистрирован — шар сработает,
// когда такая почта появится (SharesFor ищет по email).
func (s *docStore) AddShare(docID, from, to string, canEdit bool) error {
	to = strings.TrimSpace(strings.ToLower(to))
	if to == "" {
		return errShareBad
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	var doc *Doc
	for i := range s.docs {
		if s.docs[i].ID == docID {
			doc = &s.docs[i]
			break
		}
	}
	if doc == nil || doc.Owner != from {
		return errNotFound
	}
	if to == from {
		return errShareBad
	}
	if !validCorpEmail(to) {
		return errShareBad
	}
	for _, sh := range s.shares {
		if sh.DocID == docID && sh.To == to {
			return errShareExists
		}
	}
	s.shares = append(s.shares, Share{DocID: docID, From: from, To: to, CanEdit: canEdit})
	return nil
}

func (s *docStore) RemoveShare(docID, to, actor string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	owner := ""
	for _, d := range s.docs {
		if d.ID == docID {
			owner = d.Owner
			break
		}
	}
	if owner == "" {
		return false
	}
	if actor != owner && actor != to {
		return false
	}
	for i, sh := range s.shares {
		if sh.DocID == docID && sh.To == to {
			s.shares = append(s.shares[:i], s.shares[i+1:]...)
			return true
		}
	}
	return false
}

func (s *docStore) DeleteFolder(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, d := range s.docs {
		if d.Folder == id {
			return errNotEmpty
		}
	}
	for i, f := range s.folders {
		if f.ID == id {
			s.folders = append(s.folders[:i], s.folders[i+1:]...)
			return nil
		}
	}
	return errNotFound
}

func (s *docStore) SaveDoc(id, content string) (string, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range s.docs {
		if s.docs[i].ID == id {
			s.docs[i].Content = content
			s.docs[i].Updated = today()
			s.docs[i].Version = wopiNow()
			return s.docs[i].Version, true
		}
	}
	return "", false
}

func (s *docStore) DocVersion(id string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	if d, ok := s.docLocked(id); ok {
		if d.Version != "" {
			return d.Version
		}
		return wopiAt(d.Updated)
	}
	return wopiNow()
}

// docLocked — поиск документа; мьютекс уже захвачен.
func (s *docStore) docLocked(id string) (Doc, bool) {
	for _, d := range s.docs {
		if d.ID == id {
			return d, true
		}
	}
	return Doc{}, false
}
