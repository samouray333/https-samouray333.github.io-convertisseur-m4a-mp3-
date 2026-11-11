package core

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"mime"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

func newID() string {
	b := make([]byte, 8)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func newToken() string {
	b := make([]byte, 24)
	rand.Read(b)
	return hex.EncodeToString(b)
}

// Limiter : limiteur de débit (seau à jetons avec dette), réglable à chaud.
type Limiter struct {
	mu     sync.Mutex
	rate   int64
	tokens float64
	last   time.Time
}

func NewLimiter(rate int64) *Limiter { return &Limiter{rate: rate, last: time.Now()} }

func (l *Limiter) SetRate(r int64) {
	l.mu.Lock()
	l.rate = r
	l.tokens = 0
	l.last = time.Now()
	l.mu.Unlock()
}

func (l *Limiter) Rate() int64 {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.rate
}

// Wait consomme n octets et dort le temps nécessaire pour respecter le débit.
func (l *Limiter) Wait(ctx context.Context, n int) {
	l.mu.Lock()
	if l.rate <= 0 {
		l.mu.Unlock()
		return
	}
	now := time.Now()
	l.tokens += now.Sub(l.last).Seconds() * float64(l.rate)
	if max := float64(l.rate) / 4; l.tokens > max {
		l.tokens = max
	}
	l.last = now
	l.tokens -= float64(n)
	var sleep time.Duration
	if l.tokens < 0 {
		sleep = time.Duration(-l.tokens / float64(l.rate) * float64(time.Second))
	}
	l.mu.Unlock()
	if sleep > 0 {
		if sleep > 2*time.Second {
			sleep = 2 * time.Second
		}
		select {
		case <-ctx.Done():
		case <-time.After(sleep):
		}
	}
}

// chunk : taille de lecture adaptée au débit limite (pour un débit régulier).
func (l *Limiter) chunk(def int) int {
	r := l.Rate()
	if r <= 0 {
		return def
	}
	c := int(r / 8)
	if c < 1024 {
		c = 1024
	}
	if c > def {
		c = def
	}
	return c
}

var badChars = regexp.MustCompile(`[<>:"/\\|?*\x00-\x1f]`)

// sanitizeName nettoie un nom de fichier pour Windows et Android.
func sanitizeName(n string) string {
	n = badChars.ReplaceAllString(n, "_")
	n = strings.TrimRight(strings.TrimSpace(n), ". ")
	if len(n) > 180 {
		ext := filepath.Ext(n)
		if len(ext) > 12 {
			ext = ""
		}
		n = n[:180-len(ext)] + ext
	}
	up := strings.ToUpper(strings.TrimSuffix(n, filepath.Ext(n)))
	switch up {
	case "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "LPT1", "LPT2", "LPT3":
		n = "_" + n
	}
	if n == "" {
		n = "telechargement"
	}
	return n
}

// nameFromURL déduit un nom de fichier depuis une adresse.
func nameFromURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	base := path.Base(u.Path)
	if base == "." || base == "/" {
		base = ""
	}
	if d, err := url.PathUnescape(base); err == nil {
		base = d
	}
	if base == "" {
		base = u.Hostname()
	}
	return sanitizeName(base)
}

// nameFromDisposition lit le nom dans un en-tête Content-Disposition.
func nameFromDisposition(cd string) string {
	if cd == "" {
		return ""
	}
	if _, params, err := mime.ParseMediaType(cd); err == nil {
		if n := params["filename"]; n != "" {
			if d, err := url.QueryUnescape(strings.ReplaceAll(n, "+", "%2B")); err == nil && strings.Contains(n, "%") {
				n = d
			}
			return sanitizeName(filepath.Base(strings.ReplaceAll(n, "\\", "/")))
		}
	}
	// repli : analyse manuelle
	if i := strings.Index(strings.ToLower(cd), "filename="); i >= 0 {
		n := strings.Trim(strings.SplitN(cd[i+9:], ";", 2)[0], `" `)
		if n != "" {
			return sanitizeName(n)
		}
	}
	return ""
}

func extOf(name string) string {
	return strings.ToLower(strings.TrimPrefix(filepath.Ext(name), "."))
}

var mimeExt = map[string]string{
	"video/mp4": "mp4", "video/webm": "webm", "video/x-matroska": "mkv", "video/quicktime": "mov", "video/mp2t": "ts",
	"audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/flac": "flac", "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac",
	"application/pdf": "pdf", "application/zip": "zip", "application/x-7z-compressed": "7z", "application/x-rar-compressed": "rar", "application/vnd.rar": "rar",
	"application/gzip": "gz", "application/x-tar": "tar", "application/vnd.android.package-archive": "apk", "application/x-msdownload": "exe",
	"application/x-msi": "msi", "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp", "text/html": "html", "text/plain": "txt",
	"application/json": "json", "application/epub+zip": "epub", "application/x-iso9660-image": "iso",
	"application/vnd.apple.mpegurl": "m3u8", "application/x-mpegurl": "m3u8", "application/dash+xml": "mpd",
}

func extFromMime(ct string) string {
	mt, _, _ := mime.ParseMediaType(ct)
	return mimeExt[strings.ToLower(mt)]
}

// uniquePath renvoie un chemin libre : "nom (1).ext", "nom (2).ext"...
func uniquePath(p string, taken func(string) bool) string {
	exists := func(q string) bool {
		if _, err := os.Stat(q); err == nil {
			return true
		}
		return taken != nil && taken(q)
	}
	if !exists(p) {
		return p
	}
	ext := filepath.Ext(p)
	base := strings.TrimSuffix(p, ext)
	for i := 1; i < 10000; i++ {
		q := fmt.Sprintf("%s (%d)%s", base, i, ext)
		if !exists(q) {
			return q
		}
	}
	return base + "-" + newID() + ext
}

func isHTTP(u string) bool {
	l := strings.ToLower(u)
	return strings.HasPrefix(l, "http://") || strings.HasPrefix(l, "https://")
}

func isFTP(u string) bool { return strings.HasPrefix(strings.ToLower(u), "ftp://") }

func looksHLS(u string) bool {
	pu, err := url.Parse(u)
	if err != nil {
		return false
	}
	return strings.HasSuffix(strings.ToLower(pu.Path), ".m3u8")
}

// expandBatch développe un motif : http://site/img[001-120].jpg, [a-f], [1-50:5].
var batchRe = regexp.MustCompile(`\[([0-9]+|[a-zA-Z])-([0-9]+|[a-zA-Z])(?::([0-9]+))?\]`)

func expandBatch(pattern string, limit int) ([]string, error) {
	out := []string{pattern}
	for {
		loc := batchRe.FindStringSubmatchIndex(out[0])
		if loc == nil {
			break
		}
		var next []string
		for _, s := range out {
			m := batchRe.FindStringSubmatch(s)
			idx := batchRe.FindStringIndex(s)
			if m == nil {
				next = append(next, s)
				continue
			}
			step := 1
			if m[3] != "" {
				step, _ = strconv.Atoi(m[3])
				if step < 1 {
					step = 1
				}
			}
			var vals []string
			a, b := m[1], m[2]
			if a[0] >= '0' && a[0] <= '9' && b[0] >= '0' && b[0] <= '9' {
				x, _ := strconv.Atoi(a)
				y, _ := strconv.Atoi(b)
				w := 0
				if strings.HasPrefix(a, "0") && len(a) > 1 {
					w = len(a)
				}
				if x <= y {
					for i := x; i <= y; i += step {
						vals = append(vals, fmt.Sprintf("%0*d", w, i))
					}
				} else {
					for i := x; i >= y; i -= step {
						vals = append(vals, fmt.Sprintf("%0*d", w, i))
					}
				}
			} else if len(a) == 1 && len(b) == 1 {
				x, y := int(a[0]), int(b[0])
				if x <= y {
					for i := x; i <= y; i += step {
						vals = append(vals, string(rune(i)))
					}
				} else {
					for i := x; i >= y; i -= step {
						vals = append(vals, string(rune(i)))
					}
				}
			} else {
				return nil, fmt.Errorf("motif invalide : %s", m[0])
			}
			for _, v := range vals {
				next = append(next, s[:idx[0]]+v+s[idx[1]:])
				if len(next) > limit {
					return nil, fmt.Errorf("le motif génère plus de %d adresses", limit)
				}
			}
		}
		out = next
	}
	return out, nil
}

// humanSize : "1,5 Go".
func humanSize(n int64) string {
	u := []string{"o", "Ko", "Mo", "Go", "To"}
	v := float64(n)
	i := 0
	for v >= 1024 && i < 4 {
		v /= 1024
		i++
	}
	if i == 0 {
		return fmt.Sprintf("%d o", n)
	}
	return strings.Replace(fmt.Sprintf("%.1f %s", v, u[i]), ".", ",", 1)
}
