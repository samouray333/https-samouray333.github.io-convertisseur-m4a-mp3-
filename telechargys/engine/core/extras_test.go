package core

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestStatsAndFileServing(t *testing.T) {
	data := randData(3 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{delay: 60 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	d, _ := m.Add(AddReq{URL: srv.URL + "/film.mp4", Start: true})
	waitStatus(t, m, d.ID, StCompleted, 30*time.Second)
	v := m.StatsView()
	if v.Today.Files != 1 || v.TotalFiles != 1 || len(v.Days) != 30 {
		t.Fatalf("fichiers : %+v", v.Today)
	}
	if v.Today.Bytes != int64(len(data)) || v.TotalBytes != int64(len(data)) {
		t.Fatalf("octets comptés : %d (attendu %d)", v.Today.Bytes, len(data))
	}
	if v.PeakSpeed <= 0 {
		t.Fatal("vitesse record non relevée")
	}
	// aperçu : lecture partielle (comme un lecteur vidéo), jeton obligatoire
	s, err := Serve(m, os.DirFS(t.TempDir()))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	u := fmt.Sprintf("http://127.0.0.1:%d/api/file/%s", s.Port, d.ID)
	if r, _ := http.Get(u); r.StatusCode != 401 {
		t.Fatalf("sans jeton : %d", r.StatusCode)
	}
	req, _ := http.NewRequest("GET", u+"?token="+m.Token, nil)
	req.Header.Set("Range", "bytes=1000-1999")
	r, err := http.DefaultClient.Do(req)
	if err != nil || r.StatusCode != 206 {
		t.Fatalf("lecture partielle : %v %v", err, r.StatusCode)
	}
	b, _ := io.ReadAll(r.Body)
	if !bytes.Equal(b, data[1000:2000]) {
		t.Fatal("extrait différent")
	}
	if free := diskFree(m.S.DownloadDir); free <= 0 {
		t.Fatalf("espace disque : %d", free)
	}
}

func TestLimitWindow(t *testing.T) {
	for _, c := range []struct {
		now, a, b string
		w         bool
	}{{"10:00", "09:00", "18:00", true}, {"08:59", "09:00", "18:00", false}, {"18:00", "09:00", "18:00", false},
		{"23:30", "22:00", "06:00", true}, {"03:00", "22:00", "06:00", true}, {"12:00", "22:00", "06:00", false}, {"12:00", "", "", false}} {
		if inWindow(c.now, c.a, c.b) != c.w {
			t.Errorf("%s dans %s-%s : %v attendu", c.now, c.a, c.b, c.w)
		}
	}
	m := newTestManager(t)
	m.S.LimitSched = LimitSched{Enabled: true, Start: "00:00", Stop: "23:59", Rate: 100000}
	if r := m.effectiveRate(time.Date(2026, 1, 1, 12, 0, 0, 0, time.Local)); r != 100000 {
		t.Fatal(r)
	}
	m.S.SpeedLimitOn, m.S.SpeedLimit = true, 50000 // la limite manuelle plus basse l'emporte
	if r := m.effectiveRate(time.Date(2026, 1, 1, 12, 0, 0, 0, time.Local)); r != 50000 {
		t.Fatal(r)
	}
}

func makeZip(t *testing.T, files map[string]string) []byte {
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for n, c := range files {
		w, err := zw.Create(n)
		if err != nil {
			t.Fatal(err)
		}
		w.Write([]byte(c))
	}
	zw.Close()
	return buf.Bytes()
}

func TestAutoUnzip(t *testing.T) {
	data := makeZip(t, map[string]string{"lisez-moi.txt": "bonjour", "photos/a.jpg": "image A", "photos/été/b.jpg": "image B"})
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	m.S.AutoUnzip = true
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", FileName: "album.zip", Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 20*time.Second)
	dir := filepath.Join(r.Dir, "album")
	end := time.Now().Add(5 * time.Second)
	for time.Now().Before(end) {
		if b, err := os.ReadFile(filepath.Join(dir, "photos", "été", "b.jpg")); err == nil && string(b) == "image B" {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if b, _ := os.ReadFile(filepath.Join(dir, "lisez-moi.txt")); string(b) != "bonjour" {
		t.Fatal("archive non décompressée")
	}
	// archive piégée : un fichier qui tente de sortir du dossier
	evil := filepath.Join(t.TempDir(), "piege.zip")
	os.WriteFile(evil, makeZip(t, map[string]string{"ok.txt": "ok", "../../hors-dossier.txt": "interdit"}), 0o644)
	out := filepath.Join(t.TempDir(), "sortie")
	if _, err := unzipTo(evil, out); err == nil {
		t.Fatal("archive piégée acceptée")
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(filepath.Dir(out)), "hors-dossier.txt")); err == nil {
		t.Fatal("un fichier a été écrit hors du dossier")
	}
}

func TestCheckLinks(t *testing.T) {
	data := randData(123456)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	res := m.CheckLinks(t.Context(), []string{srv.URL + "/a.bin", "http://127.0.0.1:1/mort.zip", srv.URL + "/b.bin"}, AddReq{})
	if !res[0].OK || res[0].Size != 123456 || res[1].OK || res[1].Error == "" || !res[2].OK {
		t.Fatalf("%+v", res)
	}
}

// deux moteurs sur la même machine : le « téléphone » envoie un lien au « PC »
func TestSendToPeer(t *testing.T) {
	data := randData(200000)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{}, &maxSeen, &reqs)
	defer srv.Close()
	pc := newTestManager(t)
	s := pc.S
	s.RemoteOn = true
	pc.SetSettings(s)
	info := pc.RemoteInfo()
	if !info.On || info.Port == 0 || len(info.Code) != 9 {
		t.Fatalf("réception non démarrée : %+v", info)
	}
	phone := newTestManager(t)
	phone.Platform = "android"
	ps := phone.S
	ps.PeerHost, ps.PeerCode = "127.0.0.1:"+strconv.Itoa(info.Port), "AAAA-AAAA"
	phone.SetSettings(ps)
	if _, err := phone.SendToPeer(t.Context(), srv.URL+"/x", ""); err == nil || !strings.Contains(err.Error(), "code") {
		t.Fatalf("mauvais code accepté : %v", err)
	}
	ps.PeerCode = strings.ToLower(strings.ReplaceAll(info.Code, "-", " ")) // saisie approximative tolérée
	phone.SetSettings(ps)
	name, err := phone.SendToPeer(t.Context(), srv.URL+"/x", "")
	if err != nil || name == "" {
		t.Fatalf("envoi : %v", err)
	}
	var got *Download
	for _, d := range pc.List() {
		got = d
	}
	if got == nil {
		t.Fatal("rien reçu sur le PC")
	}
	r := waitStatus(t, pc, got.ID, StCompleted, 20*time.Second)
	checkFile(t, r, data)
	// rejeu de la même demande signée : refusé
	ts := strconv.FormatInt(time.Now().UnixMilli(), 10)
	body, _ := json.Marshal(map[string]string{"url": srv.URL + "/y", "ts": ts, "sig": remoteSig(info.Code, ts, srv.URL+"/y"), "from": "test"})
	post := func() int {
		resp, err := http.Post(fmt.Sprintf("http://127.0.0.1:%d/remote/add", info.Port), "application/json", bytes.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		return resp.StatusCode
	}
	if c := post(); c != 200 {
		t.Fatalf("demande signée : %d", c)
	}
	if c := post(); c != 403 {
		t.Fatalf("rejeu accepté : %d", c)
	}
	// seule l'action « ajouter » existe à distance, et le blocage arrive après trop d'essais
	if resp, _ := http.Get(fmt.Sprintf("http://127.0.0.1:%d/api/state", info.Port)); resp.StatusCode != 404 {
		t.Fatalf("l'API complète est exposée sur le réseau : %d", resp.StatusCode)
	}
	bad, _ := json.Marshal(map[string]string{"url": "http://x/y", "ts": ts, "sig": "00"})
	last := 0
	for i := 0; i < 10; i++ {
		resp, _ := http.Post(fmt.Sprintf("http://127.0.0.1:%d/remote/add", info.Port), "application/json", bytes.NewReader(bad))
		last = resp.StatusCode
		resp.Body.Close()
	}
	if last != 429 {
		t.Fatalf("pas de blocage après 10 mauvais essais : %d", last)
	}
	// désactivation : le port se ferme
	s.RemoteOn = false
	s.RemoteCode = info.Code
	pc.SetSettings(s)
	if _, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/remote/ping", info.Port)); err == nil {
		t.Fatal("la réception écoute encore après désactivation")
	}
}
