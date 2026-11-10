package core

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math/rand"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func newTestManager(t *testing.T) *Manager {
	dir := t.TempDir()
	m, err := NewManager(filepath.Join(dir, "data"), filepath.Join(dir, "dl"), "linux")
	if err != nil {
		t.Fatal(err)
	}
	m.S.RetryWaitSec = 1
	t.Cleanup(m.Shutdown)
	return m
}

func waitStatus(t *testing.T, m *Manager, id string, want string, max time.Duration) *Download {
	t.Helper()
	end := time.Now().Add(max)
	for time.Now().Before(end) {
		d := m.Get(id)
		if d.Status == want {
			return d
		}
		if d.Status == StError && want != StError {
			t.Fatalf("erreur inattendue : %s", d.Error)
		}
		time.Sleep(30 * time.Millisecond)
	}
	d := m.Get(id)
	t.Fatalf("état %q attendu, obtenu %q (%s)", want, d.Status, d.Error)
	return nil
}

type srvOpts struct {
	noRange   bool
	delay     time.Duration // par bloc de 16 Ko
	failEvery int64         // coupe la connexion toutes les N requêtes
	maxConns  int32         // au-delà : 503
}

func fileServer(data []byte, o *srvOpts, maxSeen *int32, reqs *int64) *httptest.Server {
	var cur int32
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := atomic.AddInt64(reqs, 1)
		c := atomic.AddInt32(&cur, 1)
		defer atomic.AddInt32(&cur, -1)
		for {
			old := atomic.LoadInt32(maxSeen)
			if c <= old || atomic.CompareAndSwapInt32(maxSeen, old, c) {
				break
			}
		}
		if o.maxConns > 0 && c > o.maxConns {
			w.WriteHeader(503)
			return
		}
		start := int64(0)
		w.Header().Set("ETag", `"abc"`)
		w.Header().Set("Content-Disposition", `attachment; filename="fichier test.bin"`)
		if rg := r.Header.Get("Range"); rg != "" && !o.noRange {
			s := strings.TrimSuffix(strings.TrimPrefix(rg, "bytes="), "-")
			start, _ = strconv.ParseInt(strings.SplitN(s, "-", 2)[0], 10, 64)
			w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, len(data)-1, len(data)))
			w.Header().Set("Content-Length", strconv.Itoa(len(data)-int(start)))
			w.WriteHeader(206)
		} else {
			w.Header().Set("Content-Length", strconv.Itoa(len(data)))
		}
		sent := 0
		for p := start; p < int64(len(data)); p += 16384 {
			e := p + 16384
			if e > int64(len(data)) {
				e = int64(len(data))
			}
			if _, err := w.Write(data[p:e]); err != nil {
				return
			}
			w.(http.Flusher).Flush()
			sent += int(e - p)
			if o.failEvery > 0 && n%o.failEvery == 0 && sent > 100000 {
				hj, _ := w.(http.Hijacker)
				c, _, _ := hj.Hijack()
				c.Close()
				return
			}
			if o.delay > 0 {
				time.Sleep(o.delay)
			}
		}
	}))
}

func randData(n int) []byte {
	b := make([]byte, n)
	rand.New(rand.NewSource(42)).Read(b)
	return b
}

func checkFile(t *testing.T, d *Download, data []byte) {
	t.Helper()
	got, err := os.ReadFile(filepath.Join(d.Dir, d.FileName))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, data) {
		t.Fatalf("fichier différent de l'original (%d octets contre %d)", len(got), len(data))
	}
	if _, err := os.Stat(filepath.Join(d.Dir, d.FileName+".tlpart")); err == nil {
		t.Fatal("fichier partiel non supprimé")
	}
}

func TestSegmentedDownload(t *testing.T) {
	data := randData(12 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{delay: 5 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	sum := sha256.Sum256(data)
	d, err := m.Add(AddReq{URL: srv.URL + "/x", Start: true, ChecksumAlg: "sha256", Checksum: hex.EncodeToString(sum[:])})
	if err != nil {
		t.Fatal(err)
	}
	r := waitStatus(t, m, d.ID, StCompleted, 60*time.Second)
	if r.FileName != "fichier test.bin" {
		t.Fatalf("nom = %q", r.FileName)
	}
	if r.Size != int64(len(data)) || r.Downloaded != r.Size {
		t.Fatalf("taille %d / téléchargé %d", r.Size, r.Downloaded)
	}
	if r.Checksum.OK == nil || !*r.Checksum.OK {
		t.Fatal("empreinte non validée")
	}
	checkFile(t, r, data)
	if maxSeen != 8 {
		t.Fatalf("seulement %d connexions simultanées (8 attendues)", maxSeen)
	}
	t.Logf("connexions simultanées max : %d, requêtes : %d", maxSeen, reqs)
}

func TestPauseResumeAndRestartEngine(t *testing.T) {
	data := randData(8 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{delay: 25 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	dir := t.TempDir()
	m, _ := NewManager(filepath.Join(dir, "data"), filepath.Join(dir, "dl"), "linux")
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", Start: true})
	time.Sleep(900 * time.Millisecond)
	m.Pause(d.ID)
	p := m.Get(d.ID)
	if p.Status != StPaused || p.Downloaded == 0 || p.Downloaded >= p.Size {
		t.Fatalf("pause : état %s, %d/%d", p.Status, p.Downloaded, p.Size)
	}
	before := p.Downloaded
	// simulation d'un arrêt complet de l'application puis relance
	m.Shutdown()
	m2, err := NewManager(filepath.Join(dir, "data"), filepath.Join(dir, "dl"), "linux")
	if err != nil {
		t.Fatal(err)
	}
	defer m2.Shutdown()
	q := m2.Get(d.ID)
	if q == nil || q.Downloaded != before || len(q.Segments) == 0 {
		t.Fatalf("état non restauré après relance")
	}
	atomic.StoreInt64(&reqs, 0)
	m2.Start(d.ID)
	r := waitStatus(t, m2, d.ID, StCompleted, 60*time.Second)
	checkFile(t, r, data)
	t.Logf("repris à %d octets sur %d", before, len(data))
}

func TestFlakyServer(t *testing.T) {
	data := randData(6 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{failEvery: 2, delay: 4 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 90*time.Second)
	checkFile(t, r, data)
	t.Logf("requêtes : %d (coupures tolérées)", reqs)
}

func TestNoRangeServer(t *testing.T) {
	data := randData(3 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{noRange: true}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 30*time.Second)
	checkFile(t, r, data)
	if maxSeen != 1 || r.Resumable {
		t.Fatalf("serveur sans reprise : %d connexions, resumable=%v", maxSeen, r.Resumable)
	}
}

func TestConnectionLimitedServer(t *testing.T) {
	data := randData(8 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{maxConns: 2, delay: 2 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 60*time.Second)
	checkFile(t, r, data)
}

func TestSpeedLimit(t *testing.T) {
	data := randData(2 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	t0 := time.Now()
	d, _ := m.Add(AddReq{URL: srv.URL + "/x", Start: true, SpeedLimit: 512 * 1024})
	r := waitStatus(t, m, d.ID, StCompleted, 30*time.Second)
	el := time.Since(t0).Seconds()
	checkFile(t, r, data)
	if el < 3 || el > 7 {
		t.Fatalf("2 Mo à 512 Ko/s en %.1f s (environ 4 s attendues)", el)
	}
	t.Logf("2 Mo limités à 512 Ko/s : %.1f s", el)
}

func TestQueue(t *testing.T) {
	data := randData(1 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{delay: 3 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	m.Queues[0].MaxActive = 2
	var ids []string
	for i := 0; i < 5; i++ {
		d, _ := m.Add(AddReq{URL: fmt.Sprintf("%s/f%d", srv.URL, i), MaxConn: 1})
		ids = append(ids, d.ID)
	}
	if m.Get(ids[0]).Status != StQueued {
		t.Fatal("devrait être en attente")
	}
	if err := m.StartQueue("main"); err != nil {
		t.Fatal(err)
	}
	time.Sleep(150 * time.Millisecond)
	act := 0
	for _, id := range ids {
		if m.Get(id).Status == StDownloading {
			act++
		}
	}
	if act != 2 {
		t.Fatalf("%d actifs, 2 attendus", act)
	}
	for _, id := range ids {
		waitStatus(t, m, id, StCompleted, 60*time.Second)
	}
	time.Sleep(100 * time.Millisecond)
	if m.Queues[0].Running {
		t.Fatal("la file devrait s'arrêter une fois vide")
	}
	names := map[string]bool{}
	for _, id := range ids {
		names[m.Get(id).FileName] = true
	}
	if len(names) != 5 {
		t.Fatalf("noms en double : %v", names)
	}
}

func TestBatchAndNames(t *testing.T) {
	u, err := expandBatch("http://x/img[08-11].jpg", 100)
	if err != nil || len(u) != 4 || u[0] != "http://x/img08.jpg" || u[3] != "http://x/img11.jpg" {
		t.Fatalf("%v %v", u, err)
	}
	u, _ = expandBatch("http://x/[a-c]/[1-2]", 100)
	if len(u) != 6 || u[5] != "http://x/c/2" {
		t.Fatalf("%v", u)
	}
	if _, err := expandBatch("http://x/[1-99999]", 100); err == nil {
		t.Fatal("limite non appliquée")
	}
	if n := nameFromDisposition(`attachment; filename*=UTF-8''%C3%A9t%C3%A9%202024.pdf`); n != "été 2024.pdf" {
		t.Fatalf("%q", n)
	}
	if n := sanitizeName(`a<b>:c?.txt`); n != "a_b__c_.txt" {
		t.Fatalf("%q", n)
	}
}

func pkcs7(b []byte) []byte {
	p := 16 - len(b)%16
	return append(b, bytes.Repeat([]byte{byte(p)}, p)...)
}

// TestHLS : flux HLS réel généré par ffmpeg, chiffré en AES-128, converti en MP4.
func TestHLS(t *testing.T) {
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg absent")
	}
	src := t.TempDir()
	out, err := exec.Command("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=12:size=320x240:rate=25",
		"-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac",
		"-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_segment_filename", filepath.Join(src, "s%03d.ts"), filepath.Join(src, "media.m3u8")).CombinedOutput()
	if err != nil {
		t.Skipf("ffmpeg : %v %s", err, out)
	}
	key := []byte("0123456789abcdef")
	blk, _ := aes.NewCipher(key)
	files, _ := filepath.Glob(filepath.Join(src, "s*.ts"))
	if len(files) < 4 {
		t.Fatalf("segments : %d", len(files))
	}
	for i, f := range files { // chiffrement AES-128-CBC, IV = numéro de séquence
		b, _ := os.ReadFile(f)
		iv := make([]byte, 16)
		iv[15] = byte(i)
		b = pkcs7(b)
		cipher.NewCBCEncrypter(blk, iv).CryptBlocks(b, b)
		os.WriteFile(f, b, 0o644)
	}
	pl, _ := os.ReadFile(filepath.Join(src, "media.m3u8"))
	pl = bytes.Replace(pl, []byte("#EXTINF"), []byte("#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\"\n#EXTINF"), 1)
	os.WriteFile(filepath.Join(src, "media.m3u8"), pl, 0o644)
	os.WriteFile(filepath.Join(src, "key.bin"), key, 0o644)
	os.WriteFile(filepath.Join(src, "master.m3u8"), []byte("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=160x120\nlow.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=320x240\nmedia.m3u8\n"), 0o644)
	srv := httptest.NewServer(http.FileServer(http.Dir(src)))
	defer srv.Close()
	m := newTestManager(t)
	info, err := m.Probe(t.Context(), AddReq{URL: srv.URL + "/master.m3u8"})
	if err != nil || info.Kind != "hls" || len(info.Variants) != 2 || info.Variants[0].Resolution != "320x240" {
		t.Fatalf("analyse : %+v %v", info, err)
	}
	d, _ := m.Add(AddReq{URL: srv.URL + "/master.m3u8", FileName: "ma video", Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 60*time.Second)
	if r.FileName != "ma video.mp4" || r.HLS.Container != "mp4" {
		t.Fatalf("sortie : %s (%s)", r.FileName, r.HLS.Container)
	}
	path := filepath.Join(r.Dir, r.FileName)
	probe, err := exec.Command("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name", "-of", "csv=p=0", path).CombinedOutput()
	if err != nil {
		t.Fatalf("ffprobe : %v %s", err, probe)
	}
	s := string(probe)
	if !strings.Contains(s, "h264") || !strings.Contains(s, "aac") {
		t.Fatalf("pistes manquantes : %s", s)
	}
	var dur float64
	for _, l := range strings.Fields(s) {
		if f, err := strconv.ParseFloat(l, 64); err == nil {
			dur = f
		}
	}
	if dur < 11.5 || dur > 12.6 {
		t.Fatalf("durée %.2f s (12 s attendues)", dur)
	}
	// décodage complet : aucune erreur attendue
	if o, err := exec.Command("ffmpeg", "-v", "error", "-i", path, "-f", "null", "-").CombinedOutput(); err != nil || len(bytes.TrimSpace(o)) > 0 {
		t.Fatalf("MP4 invalide : %v %s", err, o)
	}
	if _, err := os.Stat(path + ".tlparts"); err == nil {
		t.Fatal("dossier temporaire non supprimé")
	}
	t.Logf("HLS chiffré -> MP4 : %s", strings.ReplaceAll(strings.TrimSpace(s), "\n", " | "))
}

func TestDuplicateAndAutoRetry(t *testing.T) {
	data := randData(1 << 20)
	var maxSeen int32
	var reqs int64
	fails := int64(1)
	inner := fileServer(data, &srvOpts{}, &maxSeen, &reqs)
	defer inner.Close()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if atomic.AddInt64(&fails, -1) >= 0 {
			w.WriteHeader(503)
			return
		}
		resp, err := http.Get(inner.URL + r.URL.Path)
		if err != nil {
			w.WriteHeader(502)
			return
		}
		defer resp.Body.Close()
		w.Header().Set("Content-Length", resp.Header.Get("Content-Length"))
		w.WriteHeader(200)
		buf := make([]byte, 32768)
		for {
			n, e := resp.Body.Read(buf)
			w.Write(buf[:n])
			if e != nil {
				break
			}
		}
	}))
	defer srv.Close()
	m := newTestManager(t)
	m.S.Retries = 0
	d, err := m.Add(AddReq{URL: srv.URL + "/a.bin", Start: true})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Add(AddReq{URL: srv.URL + "/a.bin"}); err == nil {
		t.Fatal("doublon accepté")
	}
	if _, err := m.Add(AddReq{URL: srv.URL + "/a.bin", AllowDup: true}); err != nil {
		t.Fatal("doublon forcé refusé :", err)
	}
	waitStatus(t, m, d.ID, StError, 10*time.Second)
	m.mu.Lock()
	m.checkAutoRetry(time.Now()) // trop tôt : rien
	m.mu.Unlock()
	if m.Get(d.ID).Status != StError {
		t.Fatal("relancé trop tôt")
	}
	m.mu.Lock()
	m.checkAutoRetry(time.Now().Add(6 * time.Minute))
	m.mu.Unlock()
	r := waitStatus(t, m, d.ID, StCompleted, 20*time.Second)
	if r.AutoRetries != 0 {
		t.Fatal("compteur non remis à zéro")
	}
}

func TestRefreshByRecapture(t *testing.T) {
	data := randData(4 << 20)
	var maxSeen int32
	var reqs int64
	srv := fileServer(data, &srvOpts{delay: 10 * time.Millisecond}, &maxSeen, &reqs)
	defer srv.Close()
	m := newTestManager(t)
	d, _ := m.Add(AddReq{URL: srv.URL + "/vieux-lien?jeton=expire", Start: true})
	time.Sleep(400 * time.Millisecond)
	m.Pause(d.ID)
	before := m.Get(d.ID).Downloaded
	m.WaitRefresh(d.ID, true)
	if err := m.AddSimple(t.Context(), srv.URL+"/nouveau-lien?jeton=frais", "", "a=b", ""); err != nil {
		t.Fatal(err)
	}
	r := waitStatus(t, m, d.ID, StCompleted, 30*time.Second)
	if r.URL != srv.URL+"/nouveau-lien?jeton=frais" || r.Cookies != "a=b" {
		t.Fatalf("adresse non remplacée : %s", r.URL)
	}
	checkFile(t, r, data)
	if len(m.List()) != 1 {
		t.Fatal("un nouveau téléchargement a été créé au lieu d'actualiser")
	}
	t.Logf("repris à %d octets avec la nouvelle adresse", before)
}
