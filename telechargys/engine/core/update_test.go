package core

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestNewerVersion(t *testing.T) {
	for _, c := range []struct {
		a, b string
		w    bool
	}{{"1.10.0", "1.9.2", true}, {"1.3.0", "1.3.0", false}, {"1.2.9", "1.3.0", false}, {"2", "1.9.9", true}, {"1.3.1-beta", "1.3.0", true}} {
		if newerVersion(c.a, c.b) != c.w {
			t.Errorf("%s > %s : %v attendu", c.a, c.b, c.w)
		}
	}
}

// faux GitHub : release, empreintes, fichier ; vérifie le jeton et la vérification SHA-256
func TestUpdateFlow(t *testing.T) {
	payload := []byte(strings.Repeat("installeur ", 50000))
	sum := sha256.Sum256(payload)
	sums := hex.EncodeToString(sum[:]) + "  Telechargys-9.9.9-Installation.exe\n"
	var srv *httptest.Server
	srv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer jeton-test" {
			w.WriteHeader(404)
			return
		}
		switch r.URL.Path {
		case "/repos/o/r/releases/latest":
			fmt.Fprintf(w, `{"tag_name":"v9.9.9","body":"Nouveautés","assets":[{"name":"Telechargys-9.9.9-Installation.exe","size":%d,"url":"%s/a/1"},{"name":"Telechargys-9.9.9.apk","size":5,"url":"%s/a/2"},{"name":"SHA256SUMS.txt","size":10,"url":"%s/a/3"}]}`, len(payload), srv.URL, srv.URL, srv.URL)
		case "/a/1":
			w.Write(payload)
		case "/a/3":
			w.Write([]byte(sums))
		}
	}))
	defer srv.Close()
	m := newTestManager(t)
	m.Platform = "windows"
	old := UpdateRepo
	UpdateRepo = "o/r"
	defer func() { UpdateRepo = old }()
	// l'API GitHub est remplacée par le faux serveur
	m.client.Transport = rewriteTransport{to: srv.URL, base: m.client.Transport}
	if _, err := m.CheckUpdate(t.Context()); err == nil || !strings.Contains(err.Error(), "jeton") {
		t.Fatalf("sans jeton : %v", err)
	}
	m.S.UpdateToken = "jeton-test"
	info, err := m.CheckUpdate(t.Context())
	if err != nil || !info.Available || info.Name != "Telechargys-9.9.9-Installation.exe" {
		t.Fatalf("%+v %v", info, err)
	}
	ch := m.Subscribe()
	if err := m.DownloadUpdate(); err != nil {
		t.Fatal(err)
	}
	deadline := time.After(20 * time.Second)
	for {
		select {
		case ev := <-ch:
			if ev.Type != "update" {
				continue
			}
			d := ev.Data.(map[string]any)
			if d["state"] == "error" {
				t.Fatal(d["error"])
			}
			if d["state"] == "ready" {
				b, _ := os.ReadFile(d["path"].(string))
				if string(b) != string(payload) {
					t.Fatal("fichier différent")
				}
				return
			}
		case <-deadline:
			t.Fatal("délai dépassé")
		}
	}
}

type rewriteTransport struct {
	to   string
	base http.RoundTripper
}

func (r rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.URL.Host == "api.github.com" {
		u := *req.URL
		u.Scheme, u.Host = "http", strings.TrimPrefix(r.to, "http://")
		req = req.Clone(req.Context())
		req.URL = &u
	}
	return r.base.RoundTrip(req)
}
