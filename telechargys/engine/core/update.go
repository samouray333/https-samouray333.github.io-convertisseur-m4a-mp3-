package core

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Mises à jour : Releases GitHub du dépôt (privé) de Telechargys, lues avec un jeton en lecture seule.

// UpdateRepo : dépôt qui publie les versions (propriétaire/nom).
var UpdateRepo = "samouray333/https-samouray333.github.io-convertisseur-m4a-mp3-"

// BuiltinToken : jeton intégré à la compilation (-ldflags "-X telechargys/engine/core.BuiltinToken=..."),
// jamais écrit dans le code source. Le jeton des Réglages est prioritaire.
var BuiltinToken = ""

// UpdateInfo : résultat d'une recherche de mise à jour.
type UpdateInfo struct {
	Current   string `json:"current"`
	Latest    string `json:"latest"`
	Available bool   `json:"available"`
	Notes     string `json:"notes"`
	Name      string `json:"name"`
	Size      int64  `json:"size"`
	assetURL  string
	sumsURL   string
}

func (m *Manager) updateToken() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	if t := strings.TrimSpace(m.S.UpdateToken); t != "" {
		return t
	}
	return BuiltinToken
}

func (m *Manager) ghRequest(ctx context.Context, u, accept string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", accept)
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	req.Header.Set("User-Agent", "Telechargys/"+Version)
	if t := m.updateToken(); t != "" {
		req.Header.Set("Authorization", "Bearer "+t)
	}
	// Go retire l'en-tête Authorization quand GitHub redirige vers son stockage (autre domaine) : le jeton ne fuit pas.
	return m.httpClient().Do(req)
}

// newerVersion : a > b ("1.10.0" > "1.9.2").
func newerVersion(a, b string) bool {
	pa, pb := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < len(pa) || i < len(pb); i++ {
		var x, y int
		if i < len(pa) {
			x, _ = strconv.Atoi(strings.TrimFunc(pa[i], func(r rune) bool { return r < '0' || r > '9' }))
		}
		if i < len(pb) {
			y, _ = strconv.Atoi(strings.TrimFunc(pb[i], func(r rune) bool { return r < '0' || r > '9' }))
		}
		if x != y {
			return x > y
		}
	}
	return false
}

// CheckUpdate interroge la dernière version publiée.
func (m *Manager) CheckUpdate(ctx context.Context) (*UpdateInfo, error) {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	resp, err := m.ghRequest(ctx, "https://api.github.com/repos/"+UpdateRepo+"/releases/latest", "application/vnd.github+json")
	if err != nil {
		return nil, friendlyErr(err)
	}
	defer resp.Body.Close()
	switch {
	case resp.StatusCode == 401:
		return nil, errors.New("jeton de mise à jour refusé (expiré ou mal copié)")
	case resp.StatusCode == 404 && m.updateToken() == "":
		return nil, errors.New("dépôt privé : renseigne le jeton d'accès dans Réglages > Mises à jour")
	case resp.StatusCode == 404:
		return nil, errors.New("aucune version publiée, ou le jeton n'a pas accès au dépôt")
	case resp.StatusCode >= 400:
		return nil, fmt.Errorf("GitHub a répondu %d", resp.StatusCode)
	}
	var rel struct {
		Tag    string `json:"tag_name"`
		Body   string `json:"body"`
		Assets []struct {
			Name string `json:"name"`
			Size int64  `json:"size"`
			URL  string `json:"url"`
		} `json:"assets"`
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 4<<20)).Decode(&rel); err != nil {
		return nil, errors.New("réponse de GitHub illisible")
	}
	info := &UpdateInfo{Current: Version, Latest: strings.TrimPrefix(strings.TrimPrefix(rel.Tag, "v"), "V"), Notes: rel.Body}
	for _, a := range rel.Assets {
		n := strings.ToLower(a.Name)
		switch {
		case n == "sha256sums.txt":
			info.sumsURL = a.URL
		case m.Platform == "android" && strings.HasSuffix(n, ".apk"),
			m.Platform == "windows" && strings.HasSuffix(n, "-installation.exe") && !strings.Contains(n, "classique"):
			info.Name, info.Size, info.assetURL = a.Name, a.Size, a.URL
		}
	}
	info.Available = info.assetURL != "" && newerVersion(info.Latest, Version)
	m.mu.Lock()
	m.upd = info
	m.mu.Unlock()
	return info, nil
}

// DownloadUpdate télécharge la nouvelle version, vérifie son empreinte SHA-256 et signale « update » (ready / error).
func (m *Manager) DownloadUpdate() error {
	m.mu.Lock()
	info := m.upd
	busy := m.updBusy
	if info != nil && info.Available && !busy {
		m.updBusy = true
	}
	m.mu.Unlock()
	if info == nil || !info.Available {
		return errors.New("aucune mise à jour disponible (relance la recherche)")
	}
	if busy {
		return nil
	}
	if info.sumsURL == "" {
		m.mu.Lock()
		m.updBusy = false
		m.mu.Unlock()
		return errors.New("la version publiée n'a pas de fichier SHA256SUMS.txt : téléchargement refusé par sécurité")
	}
	go func() {
		path, err := m.fetchUpdate(info)
		m.mu.Lock()
		m.updBusy = false
		if err != nil {
			m.emit("update", map[string]any{"state": "error", "error": err.Error()})
		} else {
			m.emit("update", map[string]any{"state": "ready", "path": path, "version": info.Latest})
		}
		m.mu.Unlock()
	}()
	return nil
}

func (m *Manager) fetchUpdate(info *UpdateInfo) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	// empreintes attendues
	resp, err := m.ghRequest(ctx, info.sumsURL, "application/octet-stream")
	if err != nil {
		return "", friendlyErr(err)
	}
	want := ""
	sc := bufio.NewScanner(io.LimitReader(resp.Body, 1<<20))
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) >= 2 && strings.EqualFold(strings.TrimPrefix(f[len(f)-1], "*"), info.Name) {
			want = strings.ToLower(f[0])
		}
	}
	resp.Body.Close()
	if len(want) != 64 {
		return "", errors.New("empreinte de " + info.Name + " absente de SHA256SUMS.txt")
	}
	dir := filepath.Join(m.dataDir, "update")
	os.RemoveAll(dir)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", err
	}
	resp, err = m.ghRequest(ctx, info.assetURL, "application/octet-stream")
	if err != nil {
		return "", friendlyErr(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("téléchargement refusé par GitHub (%d)", resp.StatusCode)
	}
	path := filepath.Join(dir, sanitizeName(info.Name))
	f, err := os.Create(path)
	if err != nil {
		return "", err
	}
	h := sha256.New()
	total := resp.ContentLength
	if total <= 0 {
		total = info.Size
	}
	var done int64
	last := time.Now()
	buf := make([]byte, 128*1024)
	for {
		n, rerr := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := f.Write(buf[:n]); werr != nil {
				f.Close()
				return "", werr
			}
			h.Write(buf[:n])
			done += int64(n)
			if time.Since(last) > 300*time.Millisecond {
				last = time.Now()
				m.mu.Lock()
				m.emit("update", map[string]any{"state": "downloading", "done": done, "total": total})
				m.mu.Unlock()
			}
		}
		if rerr == io.EOF {
			break
		}
		if rerr != nil {
			f.Close()
			return "", friendlyErr(rerr)
		}
	}
	if err := f.Close(); err != nil {
		return "", err
	}
	if got := hex.EncodeToString(h.Sum(nil)); got != want {
		os.Remove(path)
		return "", errors.New("empreinte SHA-256 incorrecte : fichier corrompu, mise à jour annulée")
	}
	return path, nil
}

// autoCheckUpdate : recherche discrète (au démarrage puis une fois par jour).
func (m *Manager) autoCheckUpdate() {
	m.mu.Lock()
	on := m.S.AutoUpdate
	m.mu.Unlock()
	if !on || m.updateToken() == "" && !strings.Contains(UpdateRepo, "/") {
		return
	}
	info, err := m.CheckUpdate(context.Background())
	if err != nil || !info.Available {
		return
	}
	m.mu.Lock()
	if m.updNotified != info.Latest {
		m.updNotified = info.Latest
		m.emit("updateAvailable", info)
	}
	m.mu.Unlock()
}
