package core

import (
	"context"
	"crypto/subtle"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

var errBadURL = errors.New("adresse invalide (http ou https attendu)")

// DefaultPort : port local par défaut (l'extension navigateur essaie DefaultPort à DefaultPort+9).
const DefaultPort = 47615

type pairReq struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	ch   chan bool
}

// Server : API locale + interface web.
type Server struct {
	M    *Manager
	Port int
	srv  *http.Server
}

// Serve démarre le serveur local sur 127.0.0.1 (premier port libre à partir de DefaultPort).
func Serve(m *Manager, ui fs.FS) (*Server, error) {
	var ln net.Listener
	var err error
	port := DefaultPort
	for i := 0; i < 10; i++ {
		ln, err = net.Listen("tcp", "127.0.0.1:"+strconv.Itoa(DefaultPort+i))
		if err == nil {
			port = DefaultPort + i
			break
		}
	}
	if ln == nil {
		if ln, err = net.Listen("tcp", "127.0.0.1:0"); err != nil {
			return nil, err
		}
		port = ln.Addr().(*net.TCPAddr).Port
	}
	s := &Server{M: m, Port: port}
	mux := http.NewServeMux()
	static := http.FileServer(http.FS(ui))
	mux.Handle("/", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		static.ServeHTTP(w, r)
	}))
	mux.HandleFunc("/api/", s.api)
	s.srv = &http.Server{Handler: s.guard(mux), ReadHeaderTimeout: 15 * time.Second}
	go s.srv.Serve(ln)
	return s, nil
}

func (s *Server) Close() { s.srv.Close() }

func extOrigin(o string) bool {
	return strings.HasPrefix(o, "chrome-extension://") || strings.HasPrefix(o, "moz-extension://")
}

// guard : protections (hôte local uniquement, origine, jeton).
func (s *Server) guard(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.Host)
		if err != nil {
			host = r.Host
		}
		if host != "127.0.0.1" && host != "localhost" { // anti DNS-rebinding
			http.Error(w, "interdit", 403)
			return
		}
		if o := r.Header.Get("Origin"); o != "" {
			same := o == "http://127.0.0.1:"+strconv.Itoa(s.Port) || o == "http://localhost:"+strconv.Itoa(s.Port)
			if !same && !extOrigin(o) {
				http.Error(w, "origine refusée", 403)
				return
			}
			if extOrigin(o) {
				w.Header().Set("Access-Control-Allow-Origin", o)
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Token")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
			}
		}
		if r.Method == "OPTIONS" {
			w.WriteHeader(204)
			return
		}
		if strings.HasPrefix(r.URL.Path, "/api/") && r.URL.Path != "/api/ping" && !(r.URL.Path == "/api/pair" && r.Method == "POST") {
			tok := r.Header.Get("X-Token")
			if tok == "" {
				tok = r.URL.Query().Get("token")
			}
			if subtle.ConstantTimeCompare([]byte(tok), []byte(s.M.Token)) != 1 {
				http.Error(w, `{"error":"jeton invalide"}`, 401)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(v)
}

func fail(w http.ResponseWriter, code int, err error) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
}

func body(r *http.Request, v any) error {
	b, err := io.ReadAll(io.LimitReader(r.Body, 32<<20))
	if err != nil {
		return err
	}
	if len(b) == 0 {
		return nil
	}
	return json.Unmarshal(b, v)
}

// State : état complet envoyé à l'interface.
type State struct {
	Version    string      `json:"version"`
	Platform   string      `json:"platform"`
	Settings   Settings    `json:"settings"`
	Categories []Category  `json:"categories"`
	Queues     []*Queue    `json:"queues"`
	Downloads  []*Download `json:"downloads"`
	Rate       int64       `json:"rate"` // débit maximal appliqué en ce moment (0 = illimité)
}

func (m *Manager) State() State {
	dl := m.List()
	m.mu.Lock()
	defer m.mu.Unlock()
	return State{Version: Version, Platform: m.Platform, Settings: m.S, Categories: m.Cats, Queues: m.Queues, Downloads: dl, Rate: m.global.Rate()}
}

func (m *Manager) SetSettings(s Settings) {
	m.mu.Lock()
	if s.DownloadDir == "" {
		s.DownloadDir = m.S.DownloadDir
	}
	m.S = s
	m.applySettings()
	m.dirty = true
	m.emit("settings", m.S)
	m.mu.Unlock()
}

func (s *Server) api(w http.ResponseWriter, r *http.Request) {
	m := s.M
	p := strings.Split(strings.Trim(strings.TrimPrefix(r.URL.Path, "/api/"), "/"), "/")
	ok := func() { writeJSON(w, map[string]bool{"ok": true}) }
	res := func(err error) {
		if err != nil {
			fail(w, 400, err)
		} else {
			ok()
		}
	}
	switch {
	case p[0] == "show" && r.Method == "POST": // second lancement de l'appli : remettre la fenêtre au premier plan
		m.mu.Lock()
		m.emit("show", nil)
		m.mu.Unlock()
		ok()
	case p[0] == "update" && len(p) == 1:
		info, err := m.CheckUpdate(r.Context())
		if err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, info)
	case p[0] == "update" && len(p) == 2 && p[1] == "download" && r.Method == "POST":
		res(m.DownloadUpdate())
	case p[0] == "stats":
		writeJSON(w, m.StatsView())
	case p[0] == "file" && len(p) == 2:
		m.serveFile(w, r, p[1])
	case p[0] == "disk":
		m.mu.Lock()
		dir := m.S.DownloadDir
		m.mu.Unlock()
		if q := r.URL.Query().Get("dir"); q != "" {
			dir = q
		}
		for dir != "" && diskFree(dir) < 0 && filepath.Dir(dir) != dir { // dossier pas encore créé : on remonte
			dir = filepath.Dir(dir)
		}
		writeJSON(w, map[string]int64{"free": diskFree(dir)})
	case p[0] == "check" && r.Method == "POST":
		var in struct {
			URLs []string `json:"urls"`
			AddReq
		}
		if err := body(r, &in); err != nil || len(in.URLs) == 0 || len(in.URLs) > 500 {
			fail(w, 400, errors.New("liste d'adresses invalide (500 au maximum)"))
			return
		}
		writeJSON(w, m.CheckLinks(r.Context(), in.URLs, in.AddReq))
	case p[0] == "remote":
		writeJSON(w, m.RemoteInfo())
	case p[0] == "sendpeer" && r.Method == "POST":
		var in struct {
			URL     string `json:"url"`
			Referer string `json:"referer"`
		}
		body(r, &in)
		name, err := m.SendToPeer(r.Context(), strings.TrimSpace(in.URL), in.Referer)
		if err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, map[string]string{"fileName": name})
	case p[0] == "ping":
		writeJSON(w, map[string]string{"app": "telechargys", "version": Version})
	case p[0] == "state":
		writeJSON(w, m.State())
	case p[0] == "events":
		s.events(w, r)
	case p[0] == "summary":
		writeJSON(w, m.Summary())
	case p[0] == "probe" && r.Method == "POST":
		var a AddReq
		if err := body(r, &a); err != nil {
			fail(w, 400, err)
			return
		}
		info, err := m.Probe(r.Context(), a)
		if err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, info)
	case p[0] == "downloads" && len(p) == 1 && r.Method == "POST":
		var in struct {
			AddReq
			Items []AddReq `json:"items"`
		}
		if err := body(r, &in); err != nil {
			fail(w, 400, err)
			return
		}
		items := in.Items
		if len(items) == 0 {
			items = []AddReq{in.AddReq}
		}
		var out []*Download
		for _, it := range items {
			d, err := m.Add(it)
			if err != nil {
				if len(items) == 1 {
					var dup ErrDuplicate
					if errors.As(err, &dup) {
						w.Header().Set("Content-Type", "application/json; charset=utf-8")
						w.WriteHeader(409)
						json.NewEncoder(w).Encode(map[string]string{"error": err.Error(), "duplicate": dup.ID, "status": dup.Status})
						return
					}
					fail(w, 400, err)
					return
				}
				continue
			}
			out = append(out, m.Get(d.ID))
		}
		writeJSON(w, out)
	case p[0] == "downloads" && len(p) == 3 && r.Method == "POST":
		id := p[1]
		var in struct {
			DeleteFile bool   `json:"deleteFile"`
			URL        string `json:"url"`
			Dir        int    `json:"dir"`
			Algo       string `json:"algo"`
			On         bool   `json:"on"`
			UpdateReq
		}
		if err := body(r, &in); err != nil {
			fail(w, 400, err)
			return
		}
		switch p[2] {
		case "start":
			res(m.Start(id))
		case "pause":
			res(m.Pause(id))
		case "queue":
			res(m.Enqueue(id))
		case "restart":
			res(m.Restart(id))
		case "remove":
			res(m.Remove(id, in.DeleteFile))
		case "refresh":
			res(m.Refresh(id, in.URL))
		case "unzip":
			dst, err := m.Unzip(id)
			if err != nil {
				fail(w, 400, err)
				return
			}
			writeJSON(w, map[string]string{"dir": dst})
		case "refreshwait":
			m.WaitRefresh(id, in.On)
			ok()
		case "update":
			res(m.Update(id, in.UpdateReq))
		case "move":
			m.Move(id, in.Dir)
			ok()
		case "hash":
			sum, err := m.Hash(id, in.Algo)
			if err != nil {
				fail(w, 400, err)
				return
			}
			writeJSON(w, map[string]string{"hash": sum})
		default:
			fail(w, 404, errors.New("action inconnue"))
		}
	case p[0] == "actions" && r.Method == "POST":
		var in struct {
			Action     string   `json:"action"`
			IDs        []string `json:"ids"`
			DeleteFile bool     `json:"deleteFile"`
		}
		body(r, &in)
		switch in.Action {
		case "startAll":
			m.StartAll()
		case "pauseAll":
			m.PauseAll()
		case "removeCompleted":
			m.RemoveCompleted()
		case "start":
			for _, id := range in.IDs {
				m.Start(id)
			}
		case "pause":
			for _, id := range in.IDs {
				m.Pause(id)
			}
		case "remove":
			for _, id := range in.IDs {
				m.Remove(id, in.DeleteFile)
			}
		}
		ok()
	case p[0] == "settings" && r.Method == "PUT":
		m.mu.Lock()
		st := m.S
		m.mu.Unlock()
		if err := body(r, &st); err != nil {
			fail(w, 400, err)
			return
		}
		m.SetSettings(st)
		ok()
	case p[0] == "categories" && r.Method == "PUT":
		var c []Category
		if err := body(r, &c); err != nil || len(c) == 0 {
			fail(w, 400, errors.New("catégories invalides"))
			return
		}
		for i := range c {
			if c[i].ID == "" {
				c[i].ID = newID()
			}
			for j, e := range c[i].Exts {
				c[i].Exts[j] = strings.ToLower(strings.TrimPrefix(strings.TrimSpace(e), "."))
			}
		}
		m.mu.Lock()
		m.Cats = c
		m.dirty = true
		m.emit("categories", m.Cats)
		m.mu.Unlock()
		ok()
	case p[0] == "queues" && len(p) == 1 && r.Method == "PUT":
		var q []*Queue
		if err := body(r, &q); err != nil {
			fail(w, 400, err)
			return
		}
		m.mu.Lock()
		hasMain := false
		for _, n := range q {
			if n.ID == "" {
				n.ID = newID()
			}
			if n.ID == "main" {
				hasMain = true
			}
			if n.MaxActive < 1 {
				n.MaxActive = 1
			}
			if o := m.queueByID(n.ID); o != nil {
				n.Running = o.Running
				n.Schedule.lastStart, n.Schedule.lastStop = o.Schedule.lastStart, o.Schedule.lastStop
			} else {
				n.Running = false
			}
		}
		if !hasMain {
			q = append(defaultQueues(), q...)
		}
		m.Queues = q
		for _, d := range m.dls {
			if m.queueByID(d.Queue) == nil {
				d.Queue = "main"
				m.changed(d)
			}
		}
		m.dirty = true
		m.emit("queues", m.Queues)
		m.pump()
		m.mu.Unlock()
		ok()
	case p[0] == "queues" && len(p) == 3 && r.Method == "POST":
		if p[2] == "start" {
			res(m.StartQueue(p[1]))
		} else {
			res(m.StopQueue(p[1]))
		}
	case p[0] == "batch" && r.Method == "POST":
		var in struct {
			Pattern string `json:"pattern"`
		}
		body(r, &in)
		urls, err := expandBatch(strings.TrimSpace(in.Pattern), 2000)
		if err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, map[string]any{"urls": urls})
	case p[0] == "grab" && len(p) == 1 && r.Method == "POST":
		var g GrabReq
		body(r, &g)
		j, err := m.StartGrab(g)
		if err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, map[string]string{"id": j.ID})
	case p[0] == "grab" && len(p) == 2:
		j := m.GrabStatus(p[1], r.Method == "DELETE")
		if j == nil {
			fail(w, 404, errors.New("exploration introuvable"))
			return
		}
		writeJSON(w, j)
	case p[0] == "capture" && r.Method == "POST":
		var in struct {
			AddReq
			Silent bool     `json:"silent"`
			URLs   []string `json:"urls"`
		}
		if err := body(r, &in); err != nil {
			fail(w, 400, err)
			return
		}
		if len(in.URLs) > 0 { // liens sélectionnés / tous les liens d'une page : fenêtre de choix
			m.mu.Lock()
			m.emit("captureBatch", map[string]any{"urls": in.URLs, "referer": in.Referer, "cookies": in.Cookies, "userAgent": in.UserAgent})
			m.mu.Unlock()
			writeJSON(w, map[string]string{"mode": "dialog"})
			return
		}
		if id := m.takeRefresh(); id != "" { // lien expiré : le nouveau clic fournit la nouvelle adresse
			if err := m.RefreshFrom(id, in.AddReq); err != nil {
				fail(w, 400, err)
				return
			}
			writeJSON(w, map[string]string{"mode": "refreshed"})
			return
		}
		m.mu.Lock()
		dialog := m.S.ShowAddDialog && !in.Silent
		if dialog {
			m.emit("capture", in.AddReq)
		}
		m.mu.Unlock()
		if dialog {
			writeJSON(w, map[string]string{"mode": "dialog"})
			return
		}
		in.AddReq.Start = true
		in.AddReq.AllowDup = true
		if _, err := m.Add(in.AddReq); err != nil {
			fail(w, 400, err)
			return
		}
		writeJSON(w, map[string]string{"mode": "added"})
	case p[0] == "pair" && len(p) == 1 && r.Method == "POST":
		var in struct {
			Name string `json:"name"`
		}
		body(r, &in)
		if len(in.Name) > 60 {
			in.Name = in.Name[:60]
		}
		pr := &pairReq{ID: newID(), Name: in.Name, ch: make(chan bool, 1)}
		m.mu.Lock()
		if len(m.pairs) > 5 {
			m.mu.Unlock()
			fail(w, 429, errors.New("trop de demandes"))
			return
		}
		m.pairs[pr.ID] = pr
		m.emit("pair", pr)
		m.mu.Unlock()
		var yes bool
		select {
		case yes = <-pr.ch:
		case <-time.After(90 * time.Second):
		case <-r.Context().Done():
		}
		m.mu.Lock()
		delete(m.pairs, pr.ID)
		m.emit("pairEnd", pr.ID)
		m.mu.Unlock()
		if !yes {
			fail(w, 403, errors.New("association refusée"))
			return
		}
		writeJSON(w, map[string]string{"token": m.Token})
	case p[0] == "pair" && len(p) == 2 && r.Method == "POST":
		var in struct {
			Approve bool `json:"approve"`
		}
		body(r, &in)
		m.mu.Lock()
		pr := m.pairs[p[1]]
		m.mu.Unlock()
		if pr != nil {
			select {
			case pr.ch <- in.Approve:
			default:
			}
		}
		ok()
	case p[0] == "export.csv":
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		w.Header().Set("Content-Disposition", `attachment; filename="telechargys-historique.csv"`)
		w.Write([]byte{0xEF, 0xBB, 0xBF})
		cw := csv.NewWriter(w)
		cw.Comma = ';'
		cw.Write([]string{"Nom", "Adresse", "Dossier", "Taille (octets)", "État", "Catégorie", "Ajouté le", "Terminé le"})
		for _, d := range m.List() {
			done := ""
			if d.CompletedAt > 0 {
				done = time.UnixMilli(d.CompletedAt).Format("02/01/2006 15:04")
			}
			cw.Write([]string{d.FileName, d.URL, d.Dir, strconv.FormatInt(d.Size, 10), d.Status, d.Category, time.UnixMilli(d.AddedAt).Format("02/01/2006 15:04"), done})
		}
		cw.Flush()
	case p[0] == "export.txt":
		want := map[string]bool{}
		for _, id := range strings.Split(r.URL.Query().Get("ids"), ",") {
			if id != "" {
				want[id] = true
			}
		}
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Header().Set("Content-Disposition", `attachment; filename="telechargys-adresses.txt"`)
		for _, d := range m.List() {
			if len(want) == 0 || want[d.ID] {
				fmt.Fprintln(w, d.URL)
			}
		}
	case p[0] == "export":
		st := m.State()
		st.Settings.UpdateToken = "" // le jeton ne part jamais dans une sauvegarde
		st.Settings.RemoteCode, st.Settings.PeerCode = "", ""
		w.Header().Set("Content-Disposition", `attachment; filename="telechargys-sauvegarde.json"`)
		writeJSON(w, st)
	case p[0] == "import" && r.Method == "POST":
		var st State
		if err := body(r, &st); err != nil {
			fail(w, 400, errors.New("fichier de sauvegarde invalide"))
			return
		}
		n := m.Import(st)
		writeJSON(w, map[string]int{"imported": n})
	default:
		fail(w, 404, errors.New("introuvable"))
	}
}

// Import restaure une sauvegarde (réglages, catégories, files, liste).
func (m *Manager) Import(st State) int {
	m.mu.Lock()
	defer m.mu.Unlock()
	if st.Settings.MaxConn > 0 {
		dir, tok, rc, pc, ron := m.S.DownloadDir, m.S.UpdateToken, m.S.RemoteCode, m.S.PeerCode, m.S.RemoteOn
		m.S = st.Settings
		if m.S.UpdateToken == "" {
			m.S.UpdateToken = tok
		}
		m.S.RemoteCode, m.S.RemoteOn = rc, ron // une sauvegarde restaurée n'ouvre jamais la réception réseau
		if m.S.PeerCode == "" {
			m.S.PeerCode = pc
		}
		if m.Platform == "android" || m.S.DownloadDir == "" {
			m.S.DownloadDir = dir
		}
		m.applySettings()
	}
	if len(st.Categories) > 0 {
		m.Cats = st.Categories
	}
	if len(st.Queues) > 0 {
		for _, q := range st.Queues {
			q.Running = false
		}
		m.Queues = st.Queues
	}
	n := 0
	for _, d := range st.Downloads {
		if d == nil || d.ID == "" || m.dls[d.ID] != nil {
			continue
		}
		if d.Status == StDownloading || d.Status == StMerging || d.Status == StQueued {
			d.Status = StPaused
		}
		d.Speed, d.Conns = 0, 0
		if m.Platform == "android" && !strings.HasPrefix(d.Dir, m.S.DownloadDir) {
			d.Dir = m.dirFor(d.Category)
		}
		m.orderSeq++
		d.Order = m.orderSeq
		m.dls[d.ID] = d
		n++
	}
	m.dirty = true
	m.emit("reload", nil)
	return n
}

// events : flux SSE vers l'interface.
func (s *Server) events(w http.ResponseWriter, r *http.Request) {
	fl, okF := w.(http.Flusher)
	if !okF {
		http.Error(w, "flux non pris en charge", 500)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	ch := s.M.Subscribe()
	defer s.M.Unsubscribe(ch)
	fmt.Fprint(w, ": ok\n\n")
	fl.Flush()
	ping := time.NewTicker(20 * time.Second)
	defer ping.Stop()
	for {
		select {
		case <-r.Context().Done():
			return
		case <-ping.C:
			fmt.Fprint(w, ": ping\n\n")
			fl.Flush()
		case ev := <-ch:
			b, err := json.Marshal(ev)
			if err != nil {
				continue
			}
			fmt.Fprintf(w, "data: %s\n\n", b)
			fl.Flush()
		}
	}
}

// AddSimple : ajout direct depuis une coque (partage Android, ligne de commande).
func (m *Manager) AddSimple(ctx context.Context, rawURL, referer, cookies, ua string) error {
	req := AddReq{URL: rawURL, Referer: referer, Cookies: cookies, UserAgent: ua}
	if id := m.takeRefresh(); id != "" {
		return m.RefreshFrom(id, req)
	}
	m.mu.Lock()
	dialog := m.S.ShowAddDialog
	if dialog {
		m.emit("capture", req)
	}
	m.mu.Unlock()
	if dialog {
		return nil
	}
	req.Start = true
	req.AllowDup = true
	_, err := m.Add(req)
	return err
}

var _ = filepath.Join
