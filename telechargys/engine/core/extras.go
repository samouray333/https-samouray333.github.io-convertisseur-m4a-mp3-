package core

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// ---------- statistiques ----------

// DayStat : volume téléchargé un jour donné.
type DayStat struct {
	Bytes int64 `json:"bytes"`
	Files int   `json:"files"`
}

// Stats : compteurs conservés d'une session à l'autre.
type Stats struct {
	Days       map[string]*DayStat `json:"days"` // clé AAAA-MM-JJ
	TotalBytes int64               `json:"totalBytes"`
	TotalFiles int                 `json:"totalFiles"`
	PeakSpeed  int64               `json:"peakSpeed"`
	Since      int64               `json:"since"`
}

func (m *Manager) statDay(now time.Time) *DayStat {
	if m.stats.Days == nil {
		m.stats.Days = map[string]*DayStat{}
	}
	if m.stats.Since == 0 {
		m.stats.Since = now.UnixMilli()
	}
	k := now.Format("2006-01-02")
	d := m.stats.Days[k]
	if d == nil {
		d = &DayStat{}
		m.stats.Days[k] = d
		if len(m.stats.Days) > 400 { // on garde environ un an
			keys := make([]string, 0, len(m.stats.Days))
			for x := range m.stats.Days {
				keys = append(keys, x)
			}
			sort.Strings(keys)
			for _, x := range keys[:len(keys)-370] {
				delete(m.stats.Days, x)
			}
		}
	}
	return d
}

// addBytes / addFile : appelés verrou tenu.
func (m *Manager) addBytes(n int64) {
	if n <= 0 {
		return
	}
	m.statDay(time.Now()).Bytes += n
	m.stats.TotalBytes += n
	m.dirty = true
}

func (m *Manager) addFile() {
	m.statDay(time.Now()).Files++
	m.stats.TotalFiles++
}

// StatsView : statistiques prêtes à afficher (30 derniers jours).
type StatsView struct {
	Days       []map[string]any `json:"days"`
	TotalBytes int64            `json:"totalBytes"`
	TotalFiles int              `json:"totalFiles"`
	PeakSpeed  int64            `json:"peakSpeed"`
	Since      int64            `json:"since"`
	Today      DayStat          `json:"today"`
	Week       DayStat          `json:"week"`
	Month      DayStat          `json:"month"`
}

func (m *Manager) StatsView() StatsView {
	m.mu.Lock()
	defer m.mu.Unlock()
	v := StatsView{TotalBytes: m.stats.TotalBytes, TotalFiles: m.stats.TotalFiles, PeakSpeed: m.stats.PeakSpeed, Since: m.stats.Since}
	now := time.Now()
	for i := 29; i >= 0; i-- {
		day := now.AddDate(0, 0, -i)
		k := day.Format("2006-01-02")
		var d DayStat
		if x := m.stats.Days[k]; x != nil {
			d = *x
		}
		v.Days = append(v.Days, map[string]any{"date": k, "bytes": d.Bytes, "files": d.Files})
		v.Month.Bytes += d.Bytes
		v.Month.Files += d.Files
		if i < 7 {
			v.Week.Bytes += d.Bytes
			v.Week.Files += d.Files
		}
		if i == 0 {
			v.Today = d
		}
	}
	return v
}

// ---------- limiteur planifié ----------

// LimitSched : débit réduit sur une plage horaire (peut passer minuit).
type LimitSched struct {
	Enabled bool   `json:"enabled"`
	Start   string `json:"start"` // HH:MM
	Stop    string `json:"stop"`
	Rate    int64  `json:"rate"` // octets/s
}

func inWindow(now, start, stop string) bool {
	if start == "" || stop == "" || start == stop {
		return false
	}
	if start < stop {
		return now >= start && now < stop
	}
	return now >= start || now < stop // plage à cheval sur minuit
}

// effectiveRate : débit global à appliquer maintenant (verrou tenu).
func (m *Manager) effectiveRate(now time.Time) int64 {
	var r int64
	if m.S.SpeedLimitOn && m.S.SpeedLimit > 0 {
		r = m.S.SpeedLimit
	}
	s := m.S.LimitSched
	if s.Enabled && s.Rate > 0 && inWindow(now.Format("15:04"), s.Start, s.Stop) && (r == 0 || s.Rate < r) {
		r = s.Rate
	}
	return r
}

func (m *Manager) applyRate() {
	r := m.effectiveRate(time.Now())
	if m.global.Rate() != r {
		m.global.SetRate(r)
		m.emit("rate", r)
	}
}

// ---------- décompression des archives zip ----------

// Unzip décompresse un téléchargement terminé dans un dossier du même nom.
func (m *Manager) Unzip(id string) (string, error) {
	d := m.Get(id)
	if d == nil || d.Status != StCompleted {
		return "", errors.New("téléchargement non terminé")
	}
	src := filepath.Join(d.Dir, d.FileName)
	if extOf(src) != "zip" {
		return "", errors.New("seules les archives .zip peuvent être décompressées")
	}
	dst := uniquePath(strings.TrimSuffix(src, filepath.Ext(src)), nil)
	n, err := unzipTo(src, dst)
	if err != nil {
		os.RemoveAll(dst)
		return "", fmt.Errorf("décompression impossible : %v", err)
	}
	m.mu.Lock()
	m.emit("notify", map[string]any{"kind": "info", "id": id, "title": "Archive décompressée", "body": fmt.Sprintf("%d fichier(s) dans %s", n, filepath.Base(dst)), "path": dst})
	m.mu.Unlock()
	return dst, nil
}

func unzipTo(src, dst string) (int, error) {
	r, err := zip.OpenReader(src)
	if err != nil {
		return 0, err
	}
	defer r.Close()
	if len(r.File) > 200000 {
		return 0, errors.New("archive trop volumineuse")
	}
	root := filepath.Clean(dst) + string(os.PathSeparator)
	n := 0
	var total int64
	for _, f := range r.File {
		name := filepath.FromSlash(strings.ReplaceAll(f.Name, "\\", "/"))
		p := filepath.Join(dst, name)
		if !strings.HasPrefix(filepath.Clean(p)+string(os.PathSeparator), root) && filepath.Clean(p) != filepath.Clean(dst) {
			return n, errors.New("archive suspecte (chemin hors du dossier)") // protection « zip slip »
		}
		if f.FileInfo().IsDir() {
			if err := os.MkdirAll(p, 0o755); err != nil {
				return n, err
			}
			continue
		}
		if f.Mode()&os.ModeSymlink != 0 {
			continue // liens symboliques ignorés
		}
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			return n, err
		}
		in, err := f.Open()
		if err != nil {
			return n, err
		}
		out, err := os.Create(p)
		if err != nil {
			in.Close()
			return n, err
		}
		w, err := io.Copy(out, io.LimitReader(in, 64<<30))
		in.Close()
		if e := out.Close(); err == nil {
			err = e
		}
		if err != nil {
			return n, err
		}
		total += w
		if total > 200<<30 {
			return n, errors.New("archive anormalement grosse une fois décompressée")
		}
		n++
	}
	return n, nil
}

// ---------- vérification d'une liste de liens ----------

// LinkCheck : résultat pour une adresse.
type LinkCheck struct {
	URL   string `json:"url"`
	OK    bool   `json:"ok"`
	Name  string `json:"name,omitempty"`
	Size  int64  `json:"size"`
	Error string `json:"error,omitempty"`
}

// CheckLinks interroge chaque adresse (8 à la fois) sans rien télécharger.
func (m *Manager) CheckLinks(ctx context.Context, urls []string, base AddReq) []LinkCheck {
	out := make([]LinkCheck, len(urls))
	sem := make(chan struct{}, 8)
	var wg sync.WaitGroup
	for i, u := range urls {
		wg.Add(1)
		go func(i int, u string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			r := base
			r.URL = u
			c, cancel := context.WithTimeout(ctx, 15*time.Second)
			defer cancel()
			out[i] = LinkCheck{URL: u, Size: -1}
			p, err := m.Probe(c, r)
			if err != nil {
				out[i].Error = err.Error()
				return
			}
			out[i].OK, out[i].Name, out[i].Size = true, p.FileName, p.Size
		}(i, u)
	}
	wg.Wait()
	return out
}

// ---------- envoi d'un lien à un autre appareil (téléphone -> PC, PC -> téléphone) sur le réseau local ----------

// RemotePort : port d'écoute sur le réseau local quand la réception est activée.
const RemotePort = 47700

type remote struct {
	mu    sync.Mutex
	srv   *http.Server
	port  int
	fails map[string][]time.Time
	seen  map[string]time.Time // anti-rejeu
}

func newCode() string {
	const abc = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
	b := make([]byte, 8)
	rand.Read(b)
	for i := range b {
		b[i] = abc[int(b[i])%len(abc)]
	}
	return string(b[:4]) + "-" + string(b[4:])
}

func normCode(c string) string {
	return strings.ToUpper(strings.NewReplacer("-", "", " ", "").Replace(strings.TrimSpace(c)))
}

func remoteSig(code, ts, url string) string {
	h := hmac.New(sha256.New, []byte(normCode(code)))
	h.Write([]byte(ts + "\n" + url))
	return hex.EncodeToString(h.Sum(nil))
}

// syncRemote démarre ou arrête l'écoute locale selon les réglages (verrou tenu).
func (m *Manager) syncRemote() {
	if m.S.RemoteOn && m.S.RemoteCode == "" {
		m.S.RemoteCode = newCode()
		m.dirty = true
	}
	rm := m.remote
	rm.mu.Lock()
	defer rm.mu.Unlock()
	if !m.S.RemoteOn {
		if rm.srv != nil {
			rm.srv.Close()
			rm.srv, rm.port = nil, 0
		}
		return
	}
	if rm.srv != nil {
		return
	}
	var ln net.Listener
	var err error
	for i := 0; i < 5; i++ {
		if ln, err = net.Listen("tcp", ":"+strconv.Itoa(RemotePort+i)); err == nil {
			rm.port = RemotePort + i
			break
		}
	}
	if ln == nil {
		return
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/remote/ping", func(w http.ResponseWriter, r *http.Request) {
		host, _ := os.Hostname()
		writeJSON(w, map[string]string{"app": "telechargys", "name": host, "version": Version, "platform": m.Platform})
	})
	mux.HandleFunc("/remote/add", m.remoteAdd)
	rm.srv = &http.Server{Handler: mux, ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 20 * time.Second}
	go rm.srv.Serve(ln)
}

// remoteAdd : seule action permise à distance, ajouter un lien. Signée (HMAC du code), datée, limitée en essais.
func (m *Manager) remoteAdd(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		fail(w, 405, errors.New("méthode refusée"))
		return
	}
	ip, _, _ := net.SplitHostPort(r.RemoteAddr)
	rm := m.remote
	now := time.Now()
	rm.mu.Lock()
	recent := rm.fails[ip][:0]
	for _, t := range rm.fails[ip] {
		if now.Sub(t) < 10*time.Minute {
			recent = append(recent, t)
		}
	}
	rm.fails[ip] = recent
	blocked := len(recent) >= 8
	rm.mu.Unlock()
	if blocked {
		fail(w, 429, errors.New("trop d'essais, réessaie dans 10 minutes"))
		return
	}
	var in struct {
		URL     string `json:"url"`
		Referer string `json:"referer"`
		TS      string `json:"ts"`
		Sig     string `json:"sig"`
		From    string `json:"from"`
	}
	if err := json.NewDecoder(io.LimitReader(r.Body, 64<<10)).Decode(&in); err != nil {
		fail(w, 400, errors.New("demande illisible"))
		return
	}
	m.mu.Lock()
	code := m.S.RemoteCode
	m.mu.Unlock()
	ts, _ := strconv.ParseInt(in.TS, 10, 64)
	okSig := code != "" && hmac.Equal([]byte(in.Sig), []byte(remoteSig(code, in.TS, in.URL)))
	fresh := now.Sub(time.UnixMilli(ts)) < 3*time.Minute && time.UnixMilli(ts).Sub(now) < 3*time.Minute
	rm.mu.Lock()
	_, replay := rm.seen[in.Sig]
	if okSig && fresh && !replay {
		rm.seen[in.Sig] = now
		for k, t := range rm.seen {
			if now.Sub(t) > 10*time.Minute {
				delete(rm.seen, k)
			}
		}
	} else {
		rm.fails[ip] = append(rm.fails[ip], now)
	}
	rm.mu.Unlock()
	if !okSig || !fresh || replay {
		fail(w, 403, errors.New("code incorrect"))
		return
	}
	in.From = strings.TrimSpace(in.From)
	if r := []rune(in.From); len(r) > 40 {
		in.From = string(r[:40])
	}
	if in.From == "" {
		in.From = "un autre appareil"
	}
	d, err := m.Add(AddReq{URL: in.URL, Referer: in.Referer, Start: true, AllowDup: true, Description: "Reçu de " + in.From})
	if err != nil {
		fail(w, 400, err)
		return
	}
	m.mu.Lock()
	m.emit("notify", map[string]any{"kind": "info", "id": d.ID, "title": "Lien reçu de " + in.From, "body": d.FileName})
	m.mu.Unlock()
	writeJSON(w, map[string]string{"ok": "1", "fileName": d.FileName})
}

// RemoteInfo : ce qu'il faut saisir sur l'autre appareil.
type RemoteInfo struct {
	On    bool     `json:"on"`
	Port  int      `json:"port"`
	Code  string   `json:"code"`
	Addrs []string `json:"addrs"`
}

func (m *Manager) RemoteInfo() RemoteInfo {
	m.mu.Lock()
	info := RemoteInfo{On: m.S.RemoteOn, Code: m.S.RemoteCode}
	m.mu.Unlock()
	m.remote.mu.Lock()
	info.Port = m.remote.port
	m.remote.mu.Unlock()
	if ifs, err := net.InterfaceAddrs(); err == nil {
		var other []string
		for _, a := range ifs {
			ipn, ok := a.(*net.IPNet)
			if !ok || ipn.IP.To4() == nil || ipn.IP.IsLoopback() || ipn.IP.IsLinkLocalUnicast() {
				continue
			}
			if ipn.IP.IsPrivate() { // 192.168.x.x, 10.x.x.x... : l'adresse du Wi-Fi de la maison
				info.Addrs = append(info.Addrs, ipn.IP.String())
			} else {
				other = append(other, ipn.IP.String())
			}
		}
		if len(info.Addrs) == 0 {
			info.Addrs = other
		}
	}
	return info
}

// SendToPeer envoie un lien à l'autre appareil enregistré dans les réglages.
func (m *Manager) SendToPeer(ctx context.Context, rawURL, referer string) (string, error) {
	m.mu.Lock()
	host, code := strings.TrimSpace(m.S.PeerHost), m.S.PeerCode
	m.mu.Unlock()
	if host == "" || normCode(code) == "" {
		return "", errors.New("aucun appareil enregistré (Réglages > Appareils)")
	}
	if !isHTTP(rawURL) && !isFTP(rawURL) {
		return "", errBadURL
	}
	host = strings.TrimPrefix(strings.TrimPrefix(host, "http://"), "https://")
	if !strings.Contains(host, ":") {
		host += ":" + strconv.Itoa(RemotePort)
	}
	me, _ := os.Hostname()
	if m.Platform == "android" {
		me = "ton téléphone"
	}
	ts := strconv.FormatInt(time.Now().UnixMilli(), 10)
	body, _ := json.Marshal(map[string]string{"url": rawURL, "referer": referer, "ts": ts, "sig": remoteSig(code, ts, rawURL), "from": me})
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "POST", "http://"+host+"/remote/add", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{}).Do(req) // connexion directe, sans proxy : c'est le réseau local
	if err != nil {
		return "", errors.New("appareil injoignable : vérifie qu'il est allumé, sur le même Wi-Fi, avec Telechargys ouvert et la réception activée")
	}
	defer resp.Body.Close()
	var out struct {
		FileName string `json:"fileName"`
		Error    string `json:"error"`
	}
	json.NewDecoder(io.LimitReader(resp.Body, 64<<10)).Decode(&out)
	if resp.StatusCode != 200 {
		if out.Error == "" {
			out.Error = fmt.Sprintf("refus (%d)", resp.StatusCode)
		}
		return "", errors.New(out.Error)
	}
	return out.FileName, nil
}

// ---------- aperçu : sert un fichier terminé à l'interface (lecture vidéo, image, PDF) ----------

func (m *Manager) serveFile(w http.ResponseWriter, r *http.Request, id string) {
	d := m.Get(id)
	if d == nil || d.Status != StCompleted {
		fail(w, 404, errors.New("fichier indisponible"))
		return
	}
	p := filepath.Join(d.Dir, d.FileName)
	if st, err := os.Stat(p); err != nil || st.IsDir() {
		fail(w, 404, errors.New("fichier introuvable (déplacé ou supprimé)"))
		return
	}
	w.Header().Set("Content-Disposition", "inline")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Content-Security-Policy", "sandbox") // un fichier HTML téléchargé ne peut rien exécuter ici
	http.ServeFile(w, r, p)
}
