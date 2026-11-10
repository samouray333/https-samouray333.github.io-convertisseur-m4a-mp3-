package core

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// Event : évènement diffusé à l'interface et aux coques (Electron / Android).
type Event struct {
	Type string `json:"type"`
	Data any    `json:"data"`
}

type persisted struct {
	Token      string      `json:"token"`
	Settings   Settings    `json:"settings"`
	Categories []Category  `json:"categories"`
	Queues     []*Queue    `json:"queues"`
	Downloads  []*Download `json:"downloads"`
}

// Manager : cœur de l'application.
type Manager struct {
	mu         sync.Mutex
	dataDir    string
	Platform   string // windows, android, linux...
	Token      string
	S          Settings
	Cats       []Category
	Queues     []*Queue
	dls        map[string]*Download
	subs       map[chan Event]struct{}
	dirty      bool
	global     *Limiter
	client     *http.Client
	blocked    bool
	autoP      map[string]bool // mis en pause automatiquement (réseau)
	grabs      map[string]*GrabJob
	pairs      map[string]*pairReq
	refreshID  string    // téléchargement qui attend une nouvelle adresse (lien expiré)
	upd         *UpdateInfo
	updBusy     bool
	updNotified string
	refreshTil time.Time // fin de l'attente
	orderSeq   int64
	stop       chan struct{}
	// OnEvent : rappel optionnel (utilisé par la coque Android).
	OnEvent func(Event)
}

// NewManager charge l'état depuis dataDir (ou crée un état neuf).
func NewManager(dataDir, defaultDownloadDir, platform string) (*Manager, error) {
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		return nil, err
	}
	m := &Manager{dataDir: dataDir, Platform: platform, dls: map[string]*Download{}, subs: map[chan Event]struct{}{},
		autoP: map[string]bool{}, grabs: map[string]*GrabJob{}, pairs: map[string]*pairReq{}, stop: make(chan struct{})}
	m.S = defaultSettings(defaultDownloadDir)
	m.Cats = defaultCategories()
	m.Queues = defaultQueues()
	if b, err := os.ReadFile(m.statePath()); err == nil {
		var p persisted
		p.Settings = m.S
		if err := json.Unmarshal(b, &p); err == nil {
			m.loadPersisted(&p)
		} else if b2, err2 := os.ReadFile(m.statePath() + ".bak"); err2 == nil {
			p = persisted{Settings: m.S}
			if json.Unmarshal(b2, &p) == nil {
				m.loadPersisted(&p)
			}
		}
	}
	if m.Token == "" {
		m.Token = newToken()
	}
	if m.S.DownloadDir == "" {
		m.S.DownloadDir = defaultDownloadDir
	}
	m.global = NewLimiter(0)
	m.applySettings()
	var resume []string
	for _, d := range m.dls {
		d.Speed, d.Conns = 0, 0
		if d.Status == StDownloading || d.Status == StMerging {
			d.Status = StPaused
			if m.S.AutoResume {
				resume = append(resume, d.ID)
			}
		}
		if d.Order > m.orderSeq {
			m.orderSeq = d.Order
		}
	}
	for _, q := range m.Queues {
		q.Running = false
	}
	m.dirty = true
	go m.loop()
	for _, id := range resume {
		m.Start(id)
	}
	return m, nil
}

func (m *Manager) loadPersisted(p *persisted) {
	m.Token = p.Token
	m.S = p.Settings
	if len(p.Categories) > 0 {
		m.Cats = p.Categories
	}
	if len(p.Queues) > 0 {
		m.Queues = p.Queues
	}
	for _, d := range p.Downloads {
		if d != nil && d.ID != "" {
			m.dls[d.ID] = d
		}
	}
}

func (m *Manager) statePath() string { return filepath.Join(m.dataDir, "state.json") }

// applySettings reconstruit le client HTTP et le limiteur global (verrou tenu ou init).
func (m *Manager) applySettings() {
	if m.S.MaxConn < 1 {
		m.S.MaxConn = 1
	}
	if m.S.MaxConn > 32 {
		m.S.MaxConn = 32
	}
	if m.S.HLSConn < 1 {
		m.S.HLSConn = 6
	}
	if m.S.TimeoutSec < 5 {
		m.S.TimeoutSec = 30
	}
	if m.S.UserAgent == "" {
		m.S.UserAgent = defaultUA
	}
	if m.S.SpeedLimitOn && m.S.SpeedLimit > 0 {
		m.global.SetRate(m.S.SpeedLimit)
	} else {
		m.global.SetRate(0)
	}
	tr := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		MaxIdleConnsPerHost:   32,
		IdleConnTimeout:       60 * time.Second,
		ResponseHeaderTimeout: time.Duration(m.S.TimeoutSec) * time.Second,
		TLSHandshakeTimeout:   20 * time.Second,
		DisableCompression:    true,
		// HTTP/1.1 uniquement : une vraie connexion TCP par segment (c'est ce qui accélère).
		TLSNextProto: map[string]func(string, *tls.Conn) http.RoundTripper{},
	}
	if p := strings.TrimSpace(m.S.Proxy); p != "" {
		if !strings.Contains(p, "://") {
			p = "http://" + p
		}
		if pu, err := url.Parse(p); err == nil {
			tr.Proxy = http.ProxyURL(pu)
		}
	}
	m.client = &http.Client{Transport: tr, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 15 {
			return errors.New("trop de redirections")
		}
		return nil
	}}
}

func (m *Manager) httpClient() *http.Client {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.client
}

// ---------- évènements ----------

func (m *Manager) Subscribe() chan Event {
	ch := make(chan Event, 512)
	m.mu.Lock()
	m.subs[ch] = struct{}{}
	m.mu.Unlock()
	return ch
}

func (m *Manager) Unsubscribe(ch chan Event) {
	m.mu.Lock()
	delete(m.subs, ch)
	m.mu.Unlock()
}

// emit diffuse un évènement (verrou tenu).
func (m *Manager) emit(t string, data any) {
	ev := Event{t, data}
	for ch := range m.subs {
		select {
		case ch <- ev:
		default:
		}
	}
	if cb := m.OnEvent; cb != nil {
		go cb(ev)
	}
}

func (m *Manager) changed(d *Download) {
	m.dirty = true
	m.emit("download", m.snap(d))
}

// snap : copie cohérente d'un téléchargement (verrou tenu).
func (m *Manager) snap(d *Download) *Download {
	c := &Download{}
	copyPublic(c, d)
	if d.Status == StDownloading || d.Status == StMerging {
		c.Downloaded = d.dlCount.Load()
	}
	d.mu.Lock()
	c.Segments = make([]*Segment, len(d.Segments))
	for i, s := range d.Segments {
		c.Segments[i] = &Segment{Start: s.Start, End: s.end(), Pos: s.pos()}
	}
	if d.HLS != nil {
		h := *d.HLS
		h.DoneBits = append([]byte(nil), d.HLS.DoneBits...)
		c.HLS = &h
	}
	d.mu.Unlock()
	return c
}

func copyPublic(c, d *Download) {
	c.ID, c.URL, c.FinalURL, c.Kind, c.FileName, c.Dir, c.Category, c.Queue = d.ID, d.URL, d.FinalURL, d.Kind, d.FileName, d.Dir, d.Category, d.Queue
	c.Status, c.Size, c.Downloaded, c.Speed, c.Resumable, c.Probed = d.Status, d.Size, d.Downloaded, d.Speed, d.Resumable, d.Probed
	c.MaxConn, c.SpeedLimit, c.Headers, c.Referer, c.UserAgent, c.Cookies = d.MaxConn, d.SpeedLimit, d.Headers, d.Referer, d.UserAgent, d.Cookies
	c.Username, c.Password, c.Checksum, c.Description, c.Error, c.ETag, c.LastMod = d.Username, d.Password, d.Checksum, d.Description, d.Error, d.ETag, d.LastMod
	c.MimeType, c.AddedAt, c.CompletedAt, c.ElapsedMs, c.Conns, c.Order = d.MimeType, d.AddedAt, d.CompletedAt, d.ElapsedMs, d.Conns, d.Order
	c.NameLocked, c.CatAuto, c.ErrorAt, c.AutoRetries, c.ViaQueue = d.NameLocked, d.CatAuto, d.ErrorAt, d.AutoRetries, d.ViaQueue
}

// ---------- boucle : progression, sauvegarde, planification ----------

func (m *Manager) loop() {
	tick := time.NewTicker(500 * time.Millisecond)
	defer tick.Stop()
	n := 0
	for {
		select {
		case <-m.stop:
			return
		case <-tick.C:
		}
		n++
		m.mu.Lock()
		type prog struct {
			ID         string     `json:"id"`
			Status     string     `json:"status"`
			Downloaded int64      `json:"downloaded"`
			Size       int64      `json:"size"`
			Speed      int64      `json:"speed"`
			Conns      int        `json:"conns"`
			Segs       [][3]int64 `json:"segs,omitempty"`
			HLSDone    int        `json:"hlsDone,omitempty"`
			HLSTotal   int        `json:"hlsTotal,omitempty"`
		}
		var ps []prog
		active := false
		for _, d := range m.dls {
			if d.Status != StDownloading && d.Status != StMerging {
				continue
			}
			active = true
			cur := d.dlCount.Load()
			inst := (cur - d.lastDl) * 2
			if inst < 0 {
				inst = 0
			}
			d.lastDl = cur
			d.Speed = (d.Speed*7 + inst*3) / 10
			d.Downloaded = cur
			d.ElapsedMs += 500
			p := prog{ID: d.ID, Status: d.Status, Downloaded: cur, Size: d.Size, Speed: d.Speed}
			d.mu.Lock()
			for _, s := range d.Segments {
				a := int64(0)
				if s.isActive() {
					a = 1
					p.Conns++
				}
				p.Segs = append(p.Segs, [3]int64{s.Start, s.pos(), s.end()*2 + a})
			}
			if d.HLS != nil {
				p.HLSDone, p.HLSTotal = d.HLS.Done, d.HLS.Total
				p.Conns = d.Conns
			}
			d.mu.Unlock()
			d.Conns = p.Conns
			ps = append(ps, p)
		}
		if len(ps) > 0 {
			m.emit("progress", ps)
		}
		if n == 40 || n%172800 == 40 { // 20 s après le lancement, puis une fois par jour
			go m.autoCheckUpdate()
		}
		if n%40 == 0 { // toutes les 20 s
			m.checkSchedules()
			m.checkAutoRetry(time.Now())
		}
		var data []byte
		if (m.dirty || active) && n%6 == 0 {
			data = m.marshalState()
			m.dirty = false
		}
		m.mu.Unlock()
		if data != nil {
			m.writeState(data)
		}
	}
}

func (m *Manager) marshalState() []byte {
	p := persisted{Token: m.Token, Settings: m.S, Categories: m.Cats, Queues: m.Queues}
	for _, d := range m.dls {
		p.Downloads = append(p.Downloads, m.snap(d))
	}
	sort.Slice(p.Downloads, func(i, j int) bool { return p.Downloads[i].Order < p.Downloads[j].Order })
	b, _ := json.Marshal(p)
	return b
}

var writeMu sync.Mutex

func (m *Manager) writeState(b []byte) {
	writeMu.Lock()
	defer writeMu.Unlock()
	tmp := m.statePath() + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return
	}
	os.Rename(m.statePath(), m.statePath()+".bak")
	os.Rename(tmp, m.statePath())
}

// Flush enregistre l'état immédiatement.
func (m *Manager) Flush() {
	m.mu.Lock()
	b := m.marshalState()
	m.dirty = false
	m.mu.Unlock()
	m.writeState(b)
}

// Shutdown met tout en pause proprement et enregistre.
func (m *Manager) Shutdown() {
	m.mu.Lock()
	var chans []chan struct{}
	for _, d := range m.dls {
		if d.Status == StDownloading || d.Status == StMerging {
			d.Status = StPaused
			if d.cancel != nil {
				d.cancel()
			}
			if d.doneCh != nil {
				chans = append(chans, d.doneCh)
			}
		}
	}
	m.mu.Unlock()
	for _, c := range chans {
		select {
		case <-c:
		case <-time.After(3 * time.Second):
		}
	}
	select {
	case <-m.stop:
	default:
		close(m.stop)
	}
	m.Flush()
}

// ---------- catégories / dossiers ----------

func (m *Manager) categoryFor(name string) string {
	e := extOf(name)
	for _, c := range m.Cats {
		for _, x := range c.Exts {
			if x == e {
				return c.ID
			}
		}
	}
	return "other"
}

func (m *Manager) dirFor(cat string) string {
	for _, c := range m.Cats {
		if c.ID == cat {
			if filepath.IsAbs(c.Dir) {
				return c.Dir
			}
			return filepath.Join(m.S.DownloadDir, c.Dir)
		}
	}
	return m.S.DownloadDir
}

func (m *Manager) queueByID(id string) *Queue {
	for _, q := range m.Queues {
		if q.ID == id {
			return q
		}
	}
	return nil
}

// ---------- ajout ----------

// AddReq : demande d'ajout d'un téléchargement.
type AddReq struct {
	URL         string            `json:"url"`
	FileName    string            `json:"fileName"`
	Dir         string            `json:"dir"`
	Category    string            `json:"category"`
	Queue       string            `json:"queue"`
	Start       bool              `json:"start"`
	Headers     map[string]string `json:"headers"`
	Referer     string            `json:"referer"`
	UserAgent   string            `json:"userAgent"`
	Cookies     string            `json:"cookies"`
	Username    string            `json:"username"`
	Password    string            `json:"password"`
	MaxConn     int               `json:"maxConn"`
	SpeedLimit  int64             `json:"speedLimit"`
	ChecksumAlg string            `json:"checksumAlgo"`
	Checksum    string            `json:"checksum"`
	Description string            `json:"description"`
	VariantURL  string            `json:"variantUrl"` // HLS : playlist média choisie
	AudioURL    string            `json:"audioUrl"`
	Quality     string            `json:"quality"`
	Size        int64             `json:"size"`
	AllowDup    bool              `json:"allowDup"` // ajouter même si l'adresse est déjà dans la liste
}

func (m *Manager) Add(r AddReq) (*Download, error) {
	r.URL = strings.TrimSpace(r.URL)
	if !isHTTP(r.URL) && !isFTP(r.URL) {
		return nil, fmt.Errorf("adresse non prise en charge (http, https ou ftp attendu)")
	}
	if _, err := url.Parse(r.URL); err != nil {
		return nil, fmt.Errorf("adresse invalide")
	}
	m.mu.Lock()
	if !r.AllowDup {
		for _, o := range m.dls {
			if o.URL == r.URL && (r.VariantURL == "" || o.HLS == nil || o.HLS.MediaURL == r.VariantURL) {
				m.mu.Unlock()
				return nil, ErrDuplicate{ID: o.ID, Status: o.Status}
			}
		}
	}
	d := &Download{ID: newID(), URL: r.URL, Kind: "http", Status: StQueued, Size: -1, AddedAt: time.Now().UnixMilli(),
		Headers: r.Headers, Referer: r.Referer, UserAgent: r.UserAgent, Cookies: r.Cookies, Username: r.Username, Password: r.Password,
		MaxConn: r.MaxConn, SpeedLimit: r.SpeedLimit, Description: r.Description}
	if r.Size > 0 {
		d.Size = r.Size
	}
	if isFTP(r.URL) {
		d.Kind = "ftp"
	} else if looksStream(r.URL) || r.VariantURL != "" {
		d.Kind = "hls"
		d.HLS = &HLSState{MediaURL: r.VariantURL, AudioURL: r.AudioURL, Quality: r.Quality}
	}
	name := sanitizeName(r.FileName)
	if r.FileName == "" {
		name = nameFromURL(r.URL)
	} else {
		d.NameLocked = true
	}
	if d.Kind == "hls" {
		base := strings.TrimSuffix(name, filepath.Ext(name))
		if e := extOf(name); e == "m3u8" || e == "mpd" || e == "" || !d.NameLocked {
			name = base + ".mp4"
		}
	}
	d.FileName = name
	d.Category = r.Category
	if d.Category == "" {
		d.Category = m.categoryFor(name)
		d.CatAuto = true
	}
	d.Dir = r.Dir
	if d.Dir == "" {
		d.Dir = m.dirFor(d.Category)
	} else {
		d.CatAuto = false
	}
	d.Queue = r.Queue
	if m.queueByID(d.Queue) == nil {
		d.Queue = "main"
	}
	if a := strings.ToLower(r.ChecksumAlg); r.Checksum != "" && (a == "md5" || a == "sha1" || a == "sha256") {
		d.Checksum = Checksum{Algo: a, Expected: strings.ToLower(strings.TrimSpace(r.Checksum))}
	}
	m.orderSeq++
	d.Order = m.orderSeq
	m.dls[d.ID] = d
	m.changed(d)
	m.mu.Unlock()
	if r.Start {
		m.Start(d.ID)
	} else {
		m.mu.Lock()
		m.pump()
		m.mu.Unlock()
	}
	return d, nil
}

// ---------- démarrage / pause / suppression ----------

func (m *Manager) Start(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if d := m.dls[id]; d != nil {
		d.AutoRetries = 0
		d.ViaQueue = false
	}
	return m.startLocked(id)
}

func (m *Manager) startLocked(id string) error {
	d := m.dls[id]
	if d == nil {
		return errors.New("téléchargement introuvable")
	}
	if d.Status == StDownloading || d.Status == StMerging {
		return nil
	}
	if d.Status == StCompleted {
		return errors.New("déjà terminé (utiliser « Retélécharger »)")
	}
	if m.blocked {
		d.Status = StQueued
		m.autoP[id] = true
		m.changed(d)
		return nil
	}
	prev := d.doneCh
	ctx, cancel := context.WithCancel(context.Background())
	d.cancel = cancel
	d.doneCh = make(chan struct{})
	done := d.doneCh
	d.Status = StDownloading
	d.Error = ""
	d.ErrorAt = 0
	d.Speed = 0
	d.startedAt = time.Now()
	d.limiter = NewLimiter(d.SpeedLimit)
	d.dlCount.Store(d.Downloaded)
	d.lastDl = d.Downloaded
	m.changed(d)
	go func() {
		if prev != nil {
			<-prev
		}
		var err error
		if ctx.Err() == nil {
			err = m.run(ctx, d)
		}
		cancel()
		m.mu.Lock()
		d.Speed, d.Conns = 0, 0
		d.Downloaded = d.dlCount.Load()
		paused := d.Status != StDownloading && d.Status != StMerging // pause/suppression demandée
		var note map[string]any
		if !paused {
			if err != nil {
				d.Status = StError
				d.Error = err.Error()
				d.ErrorAt = time.Now().UnixMilli()
				note = map[string]any{"kind": "error", "id": d.ID, "title": "Échec du téléchargement", "body": d.FileName + " : " + d.Error}
			} else {
				d.Status = StCompleted
				d.CompletedAt = time.Now().UnixMilli()
				d.AutoRetries, d.ErrorAt = 0, 0
				if d.Size < 0 || d.Kind == "hls" {
					d.Size = d.Downloaded
				}
				d.Downloaded = d.Size
				note = map[string]any{"kind": "done", "id": d.ID, "title": "Téléchargement terminé", "body": d.FileName, "path": filepath.Join(d.Dir, d.FileName)}
			}
		}
		m.changed(d)
		if note != nil {
			m.emit("notify", note)
		}
		close(done)
		av := m.S.AntivirusCmd
		m.pump()
		m.mu.Unlock()
		if !paused && err == nil && av != "" {
			go runPostCommand(av, filepath.Join(d.Dir, d.FileName))
		}
	}()
	return nil
}

func (m *Manager) run(ctx context.Context, d *Download) error {
	if err := os.MkdirAll(d.Dir, 0o755); err != nil {
		return fmt.Errorf("impossible de créer le dossier : %v", err)
	}
	var err error
	switch d.Kind {
	case "hls":
		err = m.runHLS(ctx, d)
	case "ftp":
		err = m.runFTP(ctx, d)
	default:
		err = m.runHTTP(ctx, d)
	}
	if err == nil && ctx.Err() == nil {
		err = m.verifyChecksum(d)
	}
	return err
}

func (m *Manager) Pause(id string) error {
	m.mu.Lock()
	d := m.dls[id]
	if d == nil {
		m.mu.Unlock()
		return errors.New("téléchargement introuvable")
	}
	delete(m.autoP, id)
	var wait chan struct{}
	switch d.Status {
	case StDownloading, StMerging:
		d.Status = StPaused
		if d.cancel != nil {
			d.cancel()
		}
		wait = d.doneCh
	case StQueued:
		d.Status = StPaused
	}
	m.changed(d)
	m.mu.Unlock()
	if wait != nil {
		select {
		case <-wait:
		case <-time.After(5 * time.Second):
		}
	}
	return nil
}

// Enqueue remet un téléchargement en attente dans sa file.
func (m *Manager) Enqueue(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	d := m.dls[id]
	if d == nil {
		return errors.New("téléchargement introuvable")
	}
	if d.Status == StPaused || d.Status == StError {
		d.Status = StQueued
		d.Error = ""
		m.changed(d)
		m.pump()
	}
	return nil
}

func (m *Manager) partPath(d *Download) string { return filepath.Join(d.Dir, d.FileName+".tlpart") }

func (m *Manager) Remove(id string, deleteFile bool) error {
	m.mu.Lock()
	d := m.dls[id]
	if d == nil {
		m.mu.Unlock()
		return errors.New("téléchargement introuvable")
	}
	wasDone := d.Status == StCompleted
	var wait chan struct{}
	if d.Status == StDownloading || d.Status == StMerging {
		d.Status = StPaused
		if d.cancel != nil {
			d.cancel()
		}
		wait = d.doneCh
	}
	delete(m.dls, id)
	delete(m.autoP, id)
	m.dirty = true
	m.emit("removed", id)
	m.mu.Unlock()
	go func() {
		if wait != nil {
			<-wait
		}
		os.Remove(m.partPath(d))
		os.RemoveAll(m.partPath(d) + "s")
		if deleteFile && wasDone {
			os.Remove(filepath.Join(d.Dir, d.FileName))
		}
	}()
	return nil
}

// Restart : recommence le téléchargement depuis zéro.
func (m *Manager) Restart(id string) error {
	m.Pause(id)
	m.mu.Lock()
	d := m.dls[id]
	if d == nil {
		m.mu.Unlock()
		return errors.New("téléchargement introuvable")
	}
	os.Remove(m.partPath(d))
	os.RemoveAll(m.partPath(d) + "s")
	if d.Status == StCompleted {
		os.Remove(filepath.Join(d.Dir, d.FileName)) // « Retélécharger » remplace le fichier existant
	}
	d.mu.Lock()
	d.Segments = nil
	if d.HLS != nil {
		d.HLS.Done, d.HLS.DoneBits, d.HLS.Total = 0, nil, 0
	}
	d.mu.Unlock()
	d.Downloaded, d.Probed, d.CompletedAt, d.ElapsedMs, d.Error = 0, false, 0, 0, ""
	d.Checksum.Actual, d.Checksum.OK = "", nil
	d.Status = StPaused
	m.mu.Unlock()
	return m.Start(id)
}

// Refresh : remplace l'adresse (lien expiré) en gardant la progression.
func (m *Manager) Refresh(id, newURL string) error {
	newURL = strings.TrimSpace(newURL)
	if !isHTTP(newURL) && !isFTP(newURL) {
		return errors.New("adresse invalide")
	}
	m.Pause(id)
	m.mu.Lock()
	defer m.mu.Unlock()
	d := m.dls[id]
	if d == nil {
		return errors.New("téléchargement introuvable")
	}
	d.URL = newURL
	d.ETag, d.LastMod = "", "" // la validation se fera sur la taille
	d.Error = ""
	m.changed(d)
	return nil
}

// UpdateReq : modification des propriétés.
type UpdateReq struct {
	FileName    *string `json:"fileName"`
	Dir         *string `json:"dir"`
	Category    *string `json:"category"`
	Queue       *string `json:"queue"`
	MaxConn     *int    `json:"maxConn"`
	SpeedLimit  *int64  `json:"speedLimit"`
	Referer     *string `json:"referer"`
	Cookies     *string `json:"cookies"`
	UserAgent   *string `json:"userAgent"`
	Username    *string `json:"username"`
	Password    *string `json:"password"`
	Description *string `json:"description"`
	ChecksumAlg *string `json:"checksumAlgo"`
	Checksum    *string `json:"checksum"`
}

func (m *Manager) Update(id string, r UpdateReq) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	d := m.dls[id]
	if d == nil {
		return errors.New("téléchargement introuvable")
	}
	running := d.Status == StDownloading || d.Status == StMerging
	if (r.FileName != nil && *r.FileName != d.FileName) || (r.Dir != nil && *r.Dir != d.Dir) {
		if running {
			return errors.New("mettre en pause avant de changer le nom ou le dossier")
		}
		nn, nd := d.FileName, d.Dir
		if r.FileName != nil && *r.FileName != "" {
			nn = sanitizeName(*r.FileName)
		}
		if r.Dir != nil && *r.Dir != "" {
			nd = *r.Dir
		}
		if err := os.MkdirAll(nd, 0o755); err != nil {
			return err
		}
		if d.Status == StCompleted {
			if err := moveFile(filepath.Join(d.Dir, d.FileName), filepath.Join(nd, nn)); err != nil {
				return err
			}
		} else {
			moveFile(m.partPath(d), filepath.Join(nd, nn+".tlpart"))
			os.Rename(m.partPath(d)+"s", filepath.Join(nd, nn+".tlparts"))
		}
		d.FileName, d.Dir, d.NameLocked, d.CatAuto = nn, nd, true, false
	}
	if r.Category != nil {
		d.Category = *r.Category
		d.CatAuto = false
	}
	if r.Queue != nil && m.queueByID(*r.Queue) != nil {
		d.Queue = *r.Queue
	}
	if r.MaxConn != nil {
		d.MaxConn = *r.MaxConn
	}
	if r.SpeedLimit != nil {
		d.SpeedLimit = *r.SpeedLimit
		if d.limiter != nil {
			d.limiter.SetRate(d.SpeedLimit)
		}
	}
	setS := func(dst *string, src *string) {
		if src != nil {
			*dst = *src
		}
	}
	setS(&d.Referer, r.Referer)
	setS(&d.Cookies, r.Cookies)
	setS(&d.UserAgent, r.UserAgent)
	setS(&d.Username, r.Username)
	setS(&d.Password, r.Password)
	setS(&d.Description, r.Description)
	if r.Checksum != nil {
		a := ""
		if r.ChecksumAlg != nil {
			a = strings.ToLower(*r.ChecksumAlg)
		}
		d.Checksum = Checksum{Algo: a, Expected: strings.ToLower(strings.TrimSpace(*r.Checksum))}
	}
	m.changed(d)
	return nil
}

func moveFile(from, to string) error {
	if from == to {
		return nil
	}
	if _, err := os.Stat(from); err != nil {
		return nil
	}
	if err := os.Rename(from, to); err == nil {
		return nil
	}
	return copyThenRemove(from, to)
}

// Move déplace un téléchargement dans l'ordre de la liste (dir = -1 monter, +1 descendre).
func (m *Manager) Move(id string, dir int) {
	m.mu.Lock()
	defer m.mu.Unlock()
	d := m.dls[id]
	if d == nil {
		return
	}
	var best *Download
	for _, o := range m.dls {
		if o == d || o.Queue != d.Queue {
			continue
		}
		if dir < 0 && o.Order < d.Order && (best == nil || o.Order > best.Order) {
			best = o
		}
		if dir > 0 && o.Order > d.Order && (best == nil || o.Order < best.Order) {
			best = o
		}
	}
	if best != nil {
		d.Order, best.Order = best.Order, d.Order
		m.changed(d)
		m.changed(best)
	}
}

// ---------- files d'attente ----------

// pump lance les téléchargements en attente des files actives (verrou tenu).
func (m *Manager) pump() {
	if m.blocked {
		return
	}
	for _, q := range m.Queues {
		if !q.Running {
			continue
		}
		active := 0
		var waiting []*Download
		for _, d := range m.dls {
			if d.Queue != q.ID {
				continue
			}
			switch d.Status {
			case StDownloading, StMerging:
				active++
			case StQueued:
				waiting = append(waiting, d)
			}
		}
		sort.Slice(waiting, func(i, j int) bool { return waiting[i].Order < waiting[j].Order })
		max := q.MaxActive
		if max < 1 {
			max = 1
		}
		for _, d := range waiting {
			if active >= max {
				break
			}
			d.ViaQueue = true
			m.startLocked(d.ID)
			active++
		}
		if active == 0 && len(waiting) == 0 {
			q.Running = false
			m.dirty = true
			m.emit("queues", m.Queues)
			m.emit("queueDone", map[string]any{"id": q.ID, "name": q.Name, "postAction": q.PostAction})
		}
	}
}

func (m *Manager) StartQueue(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	q := m.queueByID(id)
	if q == nil {
		return errors.New("file introuvable")
	}
	n := 0
	for _, d := range m.dls {
		if d.Queue == id && d.Status == StQueued {
			n++
		}
	}
	if n == 0 {
		return errors.New("aucun téléchargement en attente dans cette file")
	}
	q.Running = true
	m.emit("queues", m.Queues)
	m.pump()
	return nil
}

func (m *Manager) StopQueue(id string) error {
	m.mu.Lock()
	q := m.queueByID(id)
	if q == nil {
		m.mu.Unlock()
		return errors.New("file introuvable")
	}
	q.Running = false
	var ids []string
	for _, d := range m.dls {
		if d.Queue == id && (d.Status == StDownloading || d.Status == StMerging) {
			ids = append(ids, d.ID)
		}
	}
	m.emit("queues", m.Queues)
	m.mu.Unlock()
	for _, i := range ids {
		m.Pause(i)
		m.Enqueue2(i)
	}
	return nil
}

// Enqueue2 : repasse en attente sans relancer la pompe.
func (m *Manager) Enqueue2(id string) {
	m.mu.Lock()
	if d := m.dls[id]; d != nil && d.Status == StPaused {
		d.Status = StQueued
		m.changed(d)
	}
	m.mu.Unlock()
}

func (m *Manager) checkSchedules() {
	now := time.Now()
	hm := now.Format("15:04")
	day := now.Format("2006-01-02")
	for _, q := range m.Queues {
		s := &q.Schedule
		if !s.Enabled {
			continue
		}
		okDay := len(s.Days) == 0
		for _, d := range s.Days {
			if d == int(now.Weekday()) {
				okDay = true
			}
		}
		if okDay && s.Start == hm && s.lastStart != day+hm && !q.Running {
			s.lastStart = day + hm
			q.Running = true
			m.emit("queues", m.Queues)
			m.pump()
		}
		if s.Stop != "" && s.Stop == hm && s.lastStop != day+hm && q.Running {
			s.lastStop = day + hm
			id := q.ID
			go m.StopQueue(id)
		}
	}
}

// ---------- actions groupées ----------

func (m *Manager) StartAll() {
	m.mu.Lock()
	var ids []string
	for _, d := range m.dls {
		if d.Status == StPaused || d.Status == StError || d.Status == StQueued {
			ids = append(ids, d.ID)
		}
	}
	m.mu.Unlock()
	for _, id := range ids {
		m.Start(id)
	}
}

func (m *Manager) PauseAll() {
	m.mu.Lock()
	var ids []string
	for _, q := range m.Queues {
		q.Running = false
	}
	for _, d := range m.dls {
		if d.Status == StDownloading || d.Status == StMerging || d.Status == StQueued {
			ids = append(ids, d.ID)
		}
	}
	m.emit("queues", m.Queues)
	m.mu.Unlock()
	var wg sync.WaitGroup
	for _, id := range ids {
		wg.Add(1)
		go func(id string) { defer wg.Done(); m.Pause(id) }(id)
	}
	wg.Wait()
}

func (m *Manager) RemoveCompleted() {
	m.mu.Lock()
	var ids []string
	for _, d := range m.dls {
		if d.Status == StCompleted {
			ids = append(ids, d.ID)
		}
	}
	m.mu.Unlock()
	for _, id := range ids {
		m.Remove(id, false)
	}
}

// SetBlocked : la coque signale que le réseau n'est pas autorisé (Wi-Fi uniquement, hors ligne).
func (m *Manager) SetBlocked(b bool) {
	m.mu.Lock()
	if m.blocked == b {
		m.mu.Unlock()
		return
	}
	m.blocked = b
	var ids []string
	if b {
		for _, d := range m.dls {
			if d.Status == StDownloading || d.Status == StMerging {
				ids = append(ids, d.ID)
			}
		}
		m.mu.Unlock()
		for _, id := range ids {
			m.Pause(id)
			m.mu.Lock()
			if d := m.dls[id]; d != nil {
				d.Status = StQueued
				d.Error = "En attente du réseau"
				m.autoP[id] = true
				m.changed(d)
			}
			m.mu.Unlock()
		}
		return
	}
	for id := range m.autoP {
		ids = append(ids, id)
	}
	m.autoP = map[string]bool{}
	m.mu.Unlock()
	for _, id := range ids {
		m.Start(id)
	}
}

// Summary : résumé pour la notification Android / l'icône de la barre des tâches.
type Summary struct {
	Active  int   `json:"active"`
	Queued  int   `json:"queued"`
	Speed   int64 `json:"speed"`
	Percent int   `json:"percent"`
}

func (m *Manager) Summary() Summary {
	m.mu.Lock()
	defer m.mu.Unlock()
	var s Summary
	var tot, got int64
	for _, d := range m.dls {
		switch d.Status {
		case StDownloading, StMerging:
			s.Active++
			s.Speed += d.Speed
			if d.Kind == "hls" && d.HLS != nil && d.HLS.Total > 0 {
				tot += int64(d.HLS.Total) * 1000
				got += int64(d.HLS.Done) * 1000
			} else if d.Size > 0 {
				tot += d.Size
				got += d.dlCount.Load()
			}
		case StQueued:
			s.Queued++
		}
	}
	if tot > 0 {
		s.Percent = int(got * 100 / tot)
		if s.Percent > 100 {
			s.Percent = 100
		}
	} else {
		s.Percent = -1
	}
	return s
}

// List : copie triée de tous les téléchargements.
func (m *Manager) List() []*Download {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]*Download, 0, len(m.dls))
	for _, d := range m.dls {
		out = append(out, m.snap(d))
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Order < out[j].Order })
	return out
}

func (m *Manager) Get(id string) *Download {
	m.mu.Lock()
	defer m.mu.Unlock()
	if d := m.dls[id]; d != nil {
		return m.snap(d)
	}
	return nil
}

// checkAutoRetry relance les téléchargements en erreur (coupure réseau, serveur saturé...) après le délai réglé (verrou tenu).
func (m *Manager) checkAutoRetry(now time.Time) {
	if m.S.AutoRetryMin <= 0 || m.blocked {
		return
	}
	for _, d := range m.dls {
		if d.Status != StError || d.ErrorAt == 0 || d.AutoRetries >= 5 || !retryable(d.Error) {
			continue
		}
		if now.Sub(time.UnixMilli(d.ErrorAt)) >= time.Duration(m.S.AutoRetryMin)*time.Minute {
			d.AutoRetries++
			d.ViaQueue = true
			m.startLocked(d.ID)
		}
	}
}

// retryable : erreurs passagères (les erreurs définitives ne sont pas relancées).
func retryable(e string) bool {
	for _, k := range []string{"404", "401", "DRM", "direct", "empreinte", "disque plein", "introuvable dans", "non pris en charge", "invalide"} {
		if strings.Contains(e, k) {
			return false
		}
	}
	return true
}

// ErrDuplicate : l'adresse est déjà dans la liste.
type ErrDuplicate struct {
	ID     string
	Status string
}

func (e ErrDuplicate) Error() string { return "Ce lien est déjà dans la liste" }

// WaitRefresh : la fenêtre « Actualiser l'adresse » est ouverte ; le prochain lien capté remplacera l'adresse de ce téléchargement.
func (m *Manager) WaitRefresh(id string, on bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if on {
		m.refreshID, m.refreshTil = id, time.Now().Add(5*time.Minute)
	} else if m.refreshID == id {
		m.refreshID = ""
	}
}

func (m *Manager) takeRefresh() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	id := m.refreshID
	m.refreshID = ""
	if id == "" || time.Now().After(m.refreshTil) || m.dls[id] == nil {
		return ""
	}
	return id
}

// RefreshFrom remplace l'adresse (et les cookies, la page d'origine) puis reprend le téléchargement.
func (m *Manager) RefreshFrom(id string, r AddReq) error {
	if err := m.Refresh(id, r.URL); err != nil {
		return err
	}
	m.mu.Lock()
	if d := m.dls[id]; d != nil {
		if r.Cookies != "" {
			d.Cookies = r.Cookies
		}
		if r.Referer != "" {
			d.Referer = r.Referer
		}
		if r.UserAgent != "" {
			d.UserAgent = r.UserAgent
		}
		m.emit("refreshed", map[string]string{"id": id, "url": r.URL})
	}
	m.mu.Unlock()
	return m.Start(id)
}
