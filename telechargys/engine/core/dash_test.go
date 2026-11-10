package core

import (
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func ffprobe(t *testing.T, path string) (string, float64) {
	out, err := exec.Command("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name", "-of", "csv=p=0", path).CombinedOutput()
	if err != nil {
		t.Fatalf("ffprobe : %v %s", err, out)
	}
	var dur float64
	for _, l := range strings.Fields(string(out)) {
		if f, err := strconv.ParseFloat(l, 64); err == nil {
			dur = f
		}
	}
	return string(out), dur
}

func makeDASH(t *testing.T, single bool) string {
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		t.Skip("ffmpeg absent")
	}
	dir := t.TempDir()
	args := []string{"-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
		"-map", "0:v", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac",
		"-s:v:1", "160x120", "-b:v:0", "600k", "-b:v:1", "200k",
		"-f", "dash", "-seg_duration", "2", "-adaptation_sets", "id=0,streams=v id=1,streams=a"}
	if single {
		args = append(args, "-single_file", "1")
	} else {
		args = append(args, "-use_timeline", "1", "-use_template", "1")
	}
	args = append(args, filepath.Join(dir, "manifest.mpd"))
	if out, err := exec.Command("ffmpeg", args...).CombinedOutput(); err != nil {
		t.Skipf("ffmpeg : %v %s", err, out)
	}
	return dir
}

func runDASH(t *testing.T, single bool) {
	dir := makeDASH(t, single)
	srv := httptest.NewServer(http.FileServer(http.Dir(dir)))
	defer srv.Close()
	m := newTestManager(t)
	info, err := m.Probe(t.Context(), AddReq{URL: srv.URL + "/manifest.mpd"})
	if err != nil || info.Kind != "hls" || len(info.Variants) != 2 || info.Variants[0].Resolution != "320x240" || info.Variants[0].AudioURL == "" {
		t.Fatalf("analyse : %+v %v", info, err)
	}
	v := info.Variants[0]
	d, _ := m.Add(AddReq{URL: srv.URL + "/manifest.mpd", FileName: "film", VariantURL: v.URL, AudioURL: v.AudioURL, Quality: v.Label, Start: true})
	r := waitStatus(t, m, d.ID, StCompleted, 60*time.Second)
	if r.FileName != "film.mp4" {
		t.Fatalf("nom : %s", r.FileName)
	}
	path := filepath.Join(r.Dir, r.FileName)
	s, dur := ffprobe(t, path)
	if !strings.Contains(s, "h264") || !strings.Contains(s, "aac") {
		t.Fatalf("vidéo et son non fusionnés : %s", s)
	}
	if dur < 9.5 || dur > 10.6 {
		t.Fatalf("durée %.2f s (10 attendues)", dur)
	}
	if o, err := exec.Command("ffmpeg", "-v", "error", "-i", path, "-f", "null", "-").CombinedOutput(); err != nil || len(strings.TrimSpace(string(o))) > 0 {
		t.Fatalf("MP4 invalide : %v %s", err, o)
	}
	if fs, _ := filepath.Glob(filepath.Join(r.Dir, "*")); len(fs) != 1 {
		t.Fatalf("fichiers restants : %v", fs)
	}
	t.Logf("DASH -> MP4 fusionné : %s", strings.ReplaceAll(strings.TrimSpace(s), "\n", " | "))
}

func TestDASHTemplate(t *testing.T)   { runDASH(t, false) }
func TestDASHSingleFile(t *testing.T) { runDASH(t, true) }

func TestISODur(t *testing.T) {
	if v := parseISODur("PT1H2M3.5S"); v != 3723.5 {
		t.Fatal(v)
	}
	if v := parseISODur("P1DT0.5S"); v != 86400.5 {
		t.Fatal(v)
	}
	if s := fillTpl("seg-$RepresentationID$-$Number%05d$-$Time$.m4s", "v1", 0, 7, 9000); s != "seg-v1-00007-9000.m4s" {
		t.Fatal(s)
	}
}

var _ = os.Remove
