package core

import (
	"context"
	"crypto/md5"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"hash"
	"io"
	"math"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const minSplit = 512 * 1024 // un segment n'est coupé que s'il reste au moins 2 x minSplit

type statusErr struct{ code int }

func (e statusErr) Error() string {
	switch e.code {
	case 401:
		return "HTTP 401 : identifiants requis"
	case 403:
		return "HTTP 403 : accès refusé (lien expiré ?)"
	case 404:
		return "HTTP 404 : fichier introuvable"
	case 416:
		return "HTTP 416 : plage refusée par le serveur"
	case 429:
		return "HTTP 429 : trop de connexions"
	}
	return fmt.Sprintf("HTTP %d", e.code)
}

// newRequest construit une requête avec tous les en-têtes du téléchargement.
func (m *Manager) newRequest(ctx context.Context, d *Download, rawURL string, from int64) (*http.Request, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", rawURL, nil)
	if err != nil {
		return nil, err
	}
	m.mu.Lock()
	ua := m.S.UserAgent
	logins := m.S.Logins
	m.mu.Unlock()
	if d.UserAgent != "" {
		ua = d.UserAgent
	}
	req.Header.Set("User-Agent", ua)
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Accept-Encoding", "identity")
	if d.Referer != "" {
		req.Header.Set("Referer", d.Referer)
	}
	if d.Cookies != "" {
		req.Header.Set("Cookie", d.Cookies)
	}
	for k, v := range d.Headers {
		req.Header.Set(k, v)
	}
	user, pass := d.Username, d.Password
	if user == "" {
		host := req.URL.Hostname()
		for _, l := range logins {
			if l.Host != "" && (host == l.Host || strings.HasSuffix(host, "."+l.Host)) {
				user, pass = l.Username, l.Password
			}
		}
	}
	if user == "" && req.URL.User != nil {
		user = req.URL.User.Username()
		pass, _ = req.URL.User.Password()
	}
	if user != "" {
		req.SetBasicAuth(user, pass)
	}
	if from >= 0 {
		req.Header.Set("Range", "bytes="+strconv.FormatInt(from, 10)+"-")
	}
	return req, nil
}

// parseContentRange : "bytes a-b/total" -> (a, total).
func parseContentRange(h string) (start, total int64) {
	start, total = -1, -1
	h = strings.TrimPrefix(strings.TrimSpace(h), "bytes ")
	parts := strings.SplitN(h, "/", 2)
	if len(parts) != 2 {
		return
	}
	if t, err := strconv.ParseInt(parts[1], 10, 64); err == nil {
		total = t
	}
	if r := strings.SplitN(parts[0], "-", 2); len(r) == 2 {
		if s, err := strconv.ParseInt(r[0], 10, 64); err == nil {
			start = s
		}
	}
	return
}

// ProbeInfo : résultat de l'analyse d'une adresse.
type ProbeInfo struct {
	URL       string       `json:"url"`
	FinalURL  string       `json:"finalUrl"`
	Kind      string       `json:"kind"`
	FileName  string       `json:"fileName"`
	Size      int64        `json:"size"`
	Resumable bool         `json:"resumable"`
	MimeType  string       `json:"mimeType"`
	Category  string       `json:"category"`
	Dir       string       `json:"dir"`
	Variants  []HLSVariant `json:"variants,omitempty"`
}

// Probe interroge le serveur sans télécharger (fenêtre « Ajouter »).
func (m *Manager) Probe(ctx context.Context, r AddReq) (*ProbeInfo, error) {
	r.URL = strings.TrimSpace(r.URL)
	if isFTP(r.URL) {
		name := nameFromURL(r.URL)
		m.mu.Lock()
		cat := m.categoryFor(name)
		dir := m.dirFor(cat)
		m.mu.Unlock()
		return &ProbeInfo{URL: r.URL, Kind: "ftp", FileName: name, Size: -1, Resumable: true, Category: cat, Dir: dir}, nil
	}
	if !isHTTP(r.URL) {
		return nil, errors.New("adresse non prise en charge (http, https ou ftp attendu)")
	}
	d := &Download{URL: r.URL, Headers: r.Headers, Referer: r.Referer, UserAgent: r.UserAgent, Cookies: r.Cookies, Username: r.Username, Password: r.Password}
	ctx, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	req, err := m.newRequest(ctx, d, r.URL, 0)
	if err != nil {
		return nil, err
	}
	resp, err := m.httpClient().Do(req)
	if err != nil {
		return nil, friendlyErr(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, statusErr{resp.StatusCode}
	}
	p := &ProbeInfo{URL: r.URL, FinalURL: resp.Request.URL.String(), Kind: "http", Size: resp.ContentLength, MimeType: resp.Header.Get("Content-Type")}
	if resp.StatusCode == 206 {
		p.Resumable = true
		if _, t := parseContentRange(resp.Header.Get("Content-Range")); t >= 0 {
			p.Size = t
		}
	} else if strings.Contains(strings.ToLower(resp.Header.Get("Accept-Ranges")), "bytes") && p.Size > 0 {
		p.Resumable = true
	}
	p.FileName = pickName(resp, r.URL)
	ext := extFromMime(p.MimeType)
	ct := strings.ToLower(p.MimeType)
	if looksStream(r.URL) || looksStream(p.FinalURL) || ext == "m3u8" || strings.Contains(ct, "dash+xml") {
		p.Kind = "hls"
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
		pl, err := parseStream(body, p.FinalURL, r.URL, "")
		if err != nil {
			return nil, err
		}
		if pl.DRM {
			return nil, errors.New("flux protégé par DRM : non pris en charge")
		}
		if pl.Live && len(pl.Variants) == 0 {
			return nil, errors.New("flux en direct : seules les vidéos complètes sont prises en charge")
		}
		p.Variants = pl.Variants
		p.Size = -1
		p.Resumable = true
		base := strings.TrimSuffix(p.FileName, filepath.Ext(p.FileName))
		p.FileName = base + ".mp4"
	}
	m.mu.Lock()
	p.Category = m.categoryFor(p.FileName)
	p.Dir = m.dirFor(p.Category)
	m.mu.Unlock()
	return p, nil
}

func pickName(resp *http.Response, orig string) string {
	name := nameFromDisposition(resp.Header.Get("Content-Disposition"))
	if name == "" {
		name = nameFromURL(resp.Request.URL.String())
	}
	if name == "" {
		name = nameFromURL(orig)
	}
	if extOf(name) == "" || len(extOf(name)) > 8 {
		if e := extFromMime(resp.Header.Get("Content-Type")); e != "" {
			name += "." + e
		}
	}
	return name
}

func friendlyErr(err error) error {
	if err == nil {
		return nil
	}
	s := err.Error()
	var ue *url.Error
	if errors.As(err, &ue) {
		s = ue.Err.Error()
	}
	switch {
	case strings.Contains(s, "no such host"):
		return errors.New("serveur introuvable (vérifier l'adresse ou la connexion)")
	case strings.Contains(s, "connection refused"):
		return errors.New("connexion refusée par le serveur")
	case strings.Contains(s, "timeout") || strings.Contains(s, "deadline exceeded"):
		return errors.New("délai dépassé : le serveur ne répond pas")
	case strings.Contains(s, "certificate"):
		return errors.New("certificat de sécurité invalide : " + s)
	case strings.Contains(s, "network is unreachable") || strings.Contains(s, "no route"):
		return errors.New("pas de connexion réseau")
	}
	return errors.New(s)
}

// reserveName fixe le nom final (unique dans le dossier) une fois le serveur interrogé.
func (m *Manager) reserveName(d *Download, serverName string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	name := d.FileName
	if !d.NameLocked && serverName != "" {
		name = serverName
	}
	if d.CatAuto {
		nc := m.categoryFor(name)
		if nc != d.Category {
			d.Category = nc
			d.Dir = m.dirFor(nc)
			os.MkdirAll(d.Dir, 0o755)
		}
	}
	if m.S.OnDuplicate != "overwrite" {
		taken := func(p string) bool {
			for _, o := range m.dls {
				if o != d && o.Status != StCompleted && strings.EqualFold(filepath.Join(o.Dir, o.FileName), p) {
					return true
				}
			}
			return false
		}
		name = filepath.Base(uniquePath(filepath.Join(d.Dir, name), taken))
	}
	d.FileName = name
	m.changed(d)
}

// runHTTP : téléchargement HTTP(S) segmenté, avec découpage dynamique.
func (m *Manager) runHTTP(ctx context.Context, d *Download) error {
	m.mu.Lock()
	retries, waitSec, timeout := m.S.Retries, m.S.RetryWaitSec, time.Duration(m.S.TimeoutSec)*time.Second
	maxConn := m.S.MaxConn
	m.mu.Unlock()
	if d.MaxConn > 0 {
		maxConn = d.MaxConn
	}
	if maxConn > 32 {
		maxConn = 32
	}
	if waitSec < 1 {
		waitSec = 1
	}
	client := m.httpClient()

	open := func(from int64) (*http.Response, error) {
		req, err := m.newRequest(ctx, d, d.URL, from)
		if err != nil {
			return nil, err
		}
		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		if resp.StatusCode >= 400 {
			resp.Body.Close()
			return nil, statusErr{resp.StatusCode}
		}
		return resp, nil
	}
	openRetry := func(from int64) (resp *http.Response, err error) {
		for i := 0; ; i++ {
			resp, err = open(from)
			if err == nil || ctx.Err() != nil {
				return
			}
			var se statusErr
			if errors.As(err, &se) && se.code != 429 && se.code < 500 && se.code != 408 {
				return
			}
			if i >= retries {
				return
			}
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(time.Duration(waitSec) * time.Second):
			}
		}
	}

	// ----- reprise ou première connexion -----
	var resp *http.Response
	var first *Segment
	resume := false
	d.mu.Lock()
	if d.Probed && d.Resumable && d.Size > 0 && len(d.Segments) > 0 {
		if st, err := os.Stat(m.partPath(d)); err == nil && st.Size() > 0 {
			resume = true
			for _, s := range d.Segments {
				if !s.done() {
					first = s
					break
				}
			}
		}
	}
	d.mu.Unlock()

	if resume && first != nil {
		r, err := openRetry(first.pos())
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return friendlyErr(err)
		}
		start, total := parseContentRange(r.Header.Get("Content-Range"))
		etag := r.Header.Get("ETag")
		same := r.StatusCode == 206 && total == d.Size && start == first.pos() && (d.ETag == "" || etag == "" || etag == d.ETag)
		if same {
			resp = r
		} else {
			r.Body.Close()
			resume = false // le fichier a changé sur le serveur : on recommence
		}
	}
	if !resume {
		first = nil
		os.Remove(m.partPath(d))
		d.mu.Lock()
		d.Segments = nil
		d.mu.Unlock()
		d.dlCount.Store(0)
		r, err := openRetry(0)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return friendlyErr(err)
		}
		resp = r
		size := resp.ContentLength
		resumable := false
		if resp.StatusCode == 206 {
			resumable = true
			if _, t := parseContentRange(resp.Header.Get("Content-Range")); t >= 0 {
				size = t
			}
		} else if strings.Contains(strings.ToLower(resp.Header.Get("Accept-Ranges")), "bytes") && size > 0 {
			resumable = true
		}
		if size <= 0 {
			resumable = false
		}
		m.reserveName(d, pickName(resp, d.URL))
		m.mu.Lock()
		d.Size, d.Resumable, d.Probed = size, resumable, true
		d.FinalURL = resp.Request.URL.String()
		d.ETag, d.LastMod, d.MimeType = resp.Header.Get("ETag"), resp.Header.Get("Last-Modified"), resp.Header.Get("Content-Type")
		end := size - 1
		if size <= 0 {
			end = math.MaxInt64 - 1
		}
		first = &Segment{Start: 0, End: end, Pos: 0}
		d.mu.Lock()
		d.Segments = []*Segment{first}
		d.mu.Unlock()
		m.changed(d)
		m.mu.Unlock()
	}
	if resume && first == nil {
		return m.finishFile(d) // tout était déjà téléchargé
	}

	f, err := os.OpenFile(m.partPath(d), os.O_RDWR|os.O_CREATE, 0o644)
	if err != nil {
		resp.Body.Close()
		return fmt.Errorf("impossible de créer le fichier : %v", err)
	}
	closed := false
	defer func() {
		if !closed {
			f.Close()
		}
	}()
	if !d.Resumable {
		maxConn = 1
	}

	// ----- travailleurs -----
	type result struct {
		seg     *Segment
		err     error
		noRange bool
	}
	results := make(chan result, 64)
	var wg sync.WaitGroup
	var connLimit = int32(maxConn)

	work := func(seg *Segment, r *http.Response) {
		defer wg.Done()
		fails := 0
		buf := make([]byte, 64*1024)
		var werr error
		noRange := false
		for !seg.done() && ctx.Err() == nil {
			if r == nil {
				rr, err := open(seg.pos())
				if err == nil && d.Resumable && seg.pos() > 0 {
					st, _ := parseContentRange(rr.Header.Get("Content-Range"))
					if rr.StatusCode != 206 || st != seg.pos() {
						rr.Body.Close()
						noRange = true
						werr = errors.New("le serveur refuse les connexions multiples")
						break
					}
				}
				if err != nil {
					var se statusErr
					if errors.As(err, &se) && (se.code == 403 || se.code == 429 || se.code == 503 || se.code == 416) && seg.pos() == seg.Start && seg.Start > 0 {
						noRange = true
						werr = err
						break
					}
					fails++
					werr = err
					if fails > retries || (errors.As(err, &se) && se.code < 500 && se.code != 429 && se.code != 408) {
						break
					}
					select {
					case <-ctx.Done():
					case <-time.After(time.Duration(waitSec) * time.Second):
					}
					continue
				}
				r = rr
			}
			// copie avec chien de garde (connexion figée)
			rctx, rcancel := context.WithCancel(ctx)
			body := r.Body
			stall := time.AfterFunc(timeout, func() { rcancel(); body.Close() })
			progressed := false
			for !seg.done() {
				lim := d.limiter
				c := len(buf)
				if lim != nil {
					c = lim.chunk(c)
				}
				c = m.global.chunk(c)
				n, rerr := body.Read(buf[:c])
				stall.Reset(timeout)
				if n > 0 {
					pos := seg.pos()
					w := int64(n)
					if rem := seg.end() - pos + 1; w > rem {
						w = rem
					}
					if w > 0 {
						if _, e := f.WriteAt(buf[:w], pos); e != nil {
							werr = fmt.Errorf("écriture impossible (disque plein ?) : %v", e)
							fails = retries + 1
							break
						}
					}
					d.mu.Lock()
					adv := seg.End - seg.Pos + 1
					if adv > w {
						adv = w
					}
					if adv > 0 {
						atomic.AddInt64(&seg.Pos, adv)
						d.dlCount.Add(adv)
					}
					d.mu.Unlock()
					progressed = true
					if lim != nil {
						lim.Wait(rctx, n)
					}
					m.global.Wait(rctx, n)
				}
				if rerr != nil {
					if rerr == io.EOF {
						if d.Size <= 0 { // taille inconnue : fin du flux = fin du fichier
							d.mu.Lock()
							atomic.StoreInt64(&seg.End, seg.Pos-1)
							d.mu.Unlock()
						} else if !seg.done() {
							werr = errors.New("connexion interrompue")
						}
					} else {
						werr = rerr
					}
					break
				}
				if rctx.Err() != nil {
					break
				}
			}
			stall.Stop()
			rcancel()
			body.Close()
			r = nil
			if fails > retries {
				break
			}
			if seg.done() {
				werr = nil
				break
			}
			if progressed {
				fails = 0
			} else {
				fails++
				if fails > retries {
					break
				}
				select {
				case <-ctx.Done():
				case <-time.After(time.Duration(waitSec) * time.Second):
				}
			}
		}
		if r != nil {
			r.Body.Close()
		}
		if seg.done() {
			werr = nil
		}
		atomic.StoreInt32(&seg.active, 0)
		results <- result{seg, werr, noRange}
	}

	launch := func(seg *Segment, r *http.Response) {
		atomic.StoreInt32(&seg.active, 1)
		wg.Add(1)
		go work(seg, r)
	}
	launch(first, resp)

	// ----- coordinateur : relance, découpe dynamique -----
	tick := time.NewTicker(30 * time.Millisecond)
	defer tick.Stop()
	var lastErr error
	hardFails := 0
	for {
		select {
		case <-ctx.Done():
			wg.Wait()
			d.mu.Lock()
			if !d.Resumable {
				d.Segments = nil
			}
			d.mu.Unlock()
			if !d.Resumable {
				f.Close()
				closed = true
				os.Remove(m.partPath(d))
				d.dlCount.Store(0)
			}
			return nil
		case res := <-results:
			if res.noRange {
				// connexion supplémentaire refusée : on rend la plage au segment voisin et on réduit
				d.mu.Lock()
				merged := false
				if res.seg.Pos == res.seg.Start {
					for i, s := range d.Segments {
						if s.End+1 == res.seg.Start && s.isActive() && i+1 < len(d.Segments) && d.Segments[i+1] == res.seg {
							atomic.StoreInt64(&s.End, res.seg.End)
							d.Segments = append(d.Segments[:i+1], d.Segments[i+2:]...)
							merged = true
							break
						}
					}
				}
				act := int32(0)
				for _, s := range d.Segments {
					if s.isActive() {
						act++
					}
				}
				d.mu.Unlock()
				if act < 1 {
					act = 1
				}
				atomic.StoreInt32(&connLimit, act)
				if !merged {
					lastErr = res.err
				}
			} else if res.err != nil {
				lastErr = res.err
				hardFails++
			}
		case <-tick.C:
		}

		d.mu.Lock()
		active, allDone := 0, true
		var idle, biggest *Segment
		for _, s := range d.Segments {
			if s.isActive() {
				active++
				if biggest == nil || s.remain() > biggest.remain() {
					biggest = s
				}
			}
			if !s.done() {
				allDone = false
				if !s.isActive() && idle == nil {
					idle = s
				}
			}
		}
		limit := int(atomic.LoadInt32(&connLimit))
		var toStart *Segment
		if !allDone && active < limit && d.Resumable {
			if idle != nil {
				toStart = idle
			} else if biggest != nil && biggest.remain() >= 2*minSplit {
				mid := biggest.Pos + biggest.remain()/2
				ns := &Segment{Start: mid, End: biggest.End, Pos: mid}
				atomic.StoreInt64(&biggest.End, mid-1)
				for i, s := range d.Segments {
					if s == biggest {
						d.Segments = append(d.Segments[:i+1], append([]*Segment{ns}, d.Segments[i+1:]...)...)
						break
					}
				}
				toStart = ns
			}
		}
		d.mu.Unlock()

		if allDone {
			break
		}
		if active == 0 && toStart == nil {
			// plus personne ne travaille et rien à relancer
			wg.Wait()
			if lastErr == nil {
				lastErr = errors.New("connexion interrompue")
			}
			return friendlyErr(lastErr)
		}
		if active == 0 && hardFails > 3 {
			wg.Wait()
			return friendlyErr(lastErr)
		}
		if toStart != nil {
			launch(toStart, nil)
		}
	}
	wg.Wait()
	f.Close()
	closed = true
	if d.Size <= 0 {
		m.mu.Lock()
		d.Size = d.dlCount.Load()
		m.mu.Unlock()
	}
	return m.finishFile(d)
}

// finishFile renomme le fichier partiel en fichier final.
func (m *Manager) finishFile(d *Download) error {
	final := filepath.Join(d.Dir, d.FileName)
	m.mu.Lock()
	over := m.S.OnDuplicate == "overwrite"
	m.mu.Unlock()
	if _, err := os.Stat(final); err == nil && !over {
		final = uniquePath(final, nil)
		m.mu.Lock()
		d.FileName = filepath.Base(final)
		m.mu.Unlock()
	}
	if err := os.Rename(m.partPath(d), final); err != nil {
		if e2 := copyThenRemove(m.partPath(d), final); e2 != nil {
			return fmt.Errorf("impossible de finaliser le fichier : %v", err)
		}
	}
	d.mu.Lock()
	d.Segments = nil
	d.mu.Unlock()
	return nil
}

func copyThenRemove(from, to string) error {
	in, err := os.Open(from)
	if err != nil {
		return err
	}
	out, err := os.Create(to)
	if err != nil {
		in.Close()
		return err
	}
	_, err = io.Copy(out, in)
	in.Close()
	if e := out.Close(); err == nil {
		err = e
	}
	if err != nil {
		os.Remove(to)
		return err
	}
	return os.Remove(from)
}

// verifyChecksum calcule l'empreinte si elle est demandée.
func (m *Manager) verifyChecksum(d *Download) error {
	m.mu.Lock()
	algo, exp := d.Checksum.Algo, d.Checksum.Expected
	path := filepath.Join(d.Dir, d.FileName)
	m.mu.Unlock()
	if algo == "" {
		return nil
	}
	sum, err := fileHash(path, algo)
	if err != nil {
		return nil
	}
	m.mu.Lock()
	d.Checksum.Actual = sum
	if exp != "" {
		ok := sum == exp
		d.Checksum.OK = &ok
	}
	m.mu.Unlock()
	if exp != "" && sum != exp {
		return fmt.Errorf("empreinte %s incorrecte : fichier corrompu ou modifié", strings.ToUpper(algo))
	}
	return nil
}

func fileHash(path, algo string) (string, error) {
	var h hash.Hash
	switch algo {
	case "md5":
		h = md5.New()
	case "sha1":
		h = sha1.New()
	case "sha256":
		h = sha256.New()
	default:
		return "", errors.New("algorithme inconnu")
	}
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// Hash calcule l'empreinte d'un téléchargement terminé (à la demande).
func (m *Manager) Hash(id, algo string) (string, error) {
	d := m.Get(id)
	if d == nil || d.Status != StCompleted {
		return "", errors.New("téléchargement non terminé")
	}
	sum, err := fileHash(filepath.Join(d.Dir, d.FileName), strings.ToLower(algo))
	if err != nil {
		return "", err
	}
	m.mu.Lock()
	if r := m.dls[id]; r != nil {
		r.Checksum.Algo, r.Checksum.Actual = strings.ToLower(algo), sum
		if r.Checksum.Expected != "" {
			ok := r.Checksum.Expected == sum
			r.Checksum.OK = &ok
		}
		m.changed(r)
	}
	m.mu.Unlock()
	return sum, nil
}

// runPostCommand lance la commande d'analyse (antivirus) sur un fichier terminé (ordinateur uniquement).
func runPostCommand(cmdline, file string) {
	if runtime.GOOS == "android" {
		return
	}
	parts := splitArgs(cmdline)
	if len(parts) == 0 {
		return
	}
	used := false
	for i, p := range parts {
		if strings.Contains(p, "%f") {
			parts[i] = strings.ReplaceAll(p, "%f", file)
			used = true
		}
	}
	if !used {
		parts = append(parts, file)
	}
	c := exec.Command(parts[0], parts[1:]...)
	hideWindow(c)
	c.Start()
	go c.Wait()
}

func splitArgs(s string) []string {
	var out []string
	var cur strings.Builder
	q := false
	for _, r := range s {
		switch {
		case r == '"':
			q = !q
		case r == ' ' && !q:
			if cur.Len() > 0 {
				out = append(out, cur.String())
				cur.Reset()
			}
		default:
			cur.WriteRune(r)
		}
	}
	if cur.Len() > 0 {
		out = append(out, cur.String())
	}
	return out
}
