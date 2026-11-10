package core

import (
	"context"
	"io"
	"net/url"
	"path"
	"strings"
	"sync"
	"time"

	"golang.org/x/net/html"
)

// GrabItem : un fichier trouvé par l'aspirateur de site.
type GrabItem struct {
	URL  string `json:"url"`
	Name string `json:"name"`
	Ext  string `json:"ext"`
	Type string `json:"type"` // catégorie
	From string `json:"from"`
	Text string `json:"text,omitempty"`
}

// GrabReq : paramètres d'exploration.
type GrabReq struct {
	URL        string   `json:"url"`
	Depth      int      `json:"depth"`      // 0 = cette page uniquement
	SameDomain bool     `json:"sameDomain"` // ne suit que les pages du même site
	MaxPages   int      `json:"maxPages"`
	Exts       []string `json:"exts"` // vide = tous les fichiers reconnus
	Cookies    string   `json:"cookies"`
	Referer    string   `json:"referer"`
}

// GrabJob : exploration en cours.
type GrabJob struct {
	ID     string     `json:"id"`
	Done   bool       `json:"done"`
	Pages  int        `json:"pages"`
	Error  string     `json:"error,omitempty"`
	Items  []GrabItem `json:"items"`
	mu     sync.Mutex
	cancel func()
}

var pageExts = map[string]bool{"": true, "html": true, "htm": true, "php": true, "asp": true, "aspx": true, "jsp": true, "shtml": true, "xhtml": true}

// StartGrab lance l'exploration d'un site (liens, images, médias) en arrière-plan.
func (m *Manager) StartGrab(r GrabReq) (*GrabJob, error) {
	start, err := url.Parse(strings.TrimSpace(r.URL))
	if err != nil || !isHTTP(r.URL) {
		return nil, errBadURL
	}
	if r.MaxPages <= 0 || r.MaxPages > 500 {
		r.MaxPages = 100
	}
	if r.Depth < 0 {
		r.Depth = 0
	}
	if r.Depth > 5 {
		r.Depth = 5
	}
	want := map[string]bool{}
	for _, e := range r.Exts {
		want[strings.ToLower(strings.TrimPrefix(e, "."))] = true
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	job := &GrabJob{ID: newID(), Items: []GrabItem{}, cancel: cancel}
	m.mu.Lock()
	m.grabs[job.ID] = job
	known := map[string]bool{}
	for _, c := range m.Cats {
		for _, e := range c.Exts {
			known[e] = true
		}
	}
	m.mu.Unlock()
	d := &Download{Cookies: r.Cookies, Referer: r.Referer}
	go func() {
		defer cancel()
		type page struct {
			u     string
			depth int
		}
		queue := []page{{start.String(), 0}}
		seenPage := map[string]bool{start.String(): true}
		seenFile := map[string]bool{}
		for len(queue) > 0 && ctx.Err() == nil {
			p := queue[0]
			queue = queue[1:]
			job.mu.Lock()
			if job.Pages >= r.MaxPages {
				job.mu.Unlock()
				break
			}
			job.Pages++
			job.mu.Unlock()
			links, final, err := m.pageLinks(ctx, d, p.u)
			if err != nil {
				if p.depth == 0 {
					job.mu.Lock()
					job.Error = friendlyErr(err).Error()
					job.mu.Unlock()
				}
				continue
			}
			for _, l := range links {
				abs := resolveURL(final, l.href)
				pu, err := url.Parse(abs)
				if err != nil || !isHTTP(abs) {
					continue
				}
				pu.Fragment = ""
				abs = pu.String()
				ext := strings.ToLower(strings.TrimPrefix(path.Ext(pu.Path), "."))
				isFile := known[ext] && !pageExts[ext]
				if isFile {
					if seenFile[abs] || (len(want) > 0 && !want[ext]) {
						continue
					}
					seenFile[abs] = true
					m.mu.Lock()
					cat := m.categoryFor("x." + ext)
					m.mu.Unlock()
					job.mu.Lock()
					job.Items = append(job.Items, GrabItem{URL: abs, Name: nameFromURL(abs), Ext: ext, Type: cat, From: final, Text: l.text})
					job.mu.Unlock()
				} else if l.nav && p.depth < r.Depth && pageExts[ext] && !seenPage[abs] {
					if r.SameDomain && pu.Hostname() != start.Hostname() {
						continue
					}
					seenPage[abs] = true
					queue = append(queue, page{abs, p.depth + 1})
				}
			}
		}
		job.mu.Lock()
		job.Done = true
		job.mu.Unlock()
		time.AfterFunc(30*time.Minute, func() { m.mu.Lock(); delete(m.grabs, job.ID); m.mu.Unlock() })
	}()
	return job, nil
}

type link struct {
	href, text string
	nav        bool
}

func (m *Manager) pageLinks(ctx context.Context, d *Download, u string) ([]link, string, error) {
	req, err := m.newRequest(ctx, d, u, -1)
	if err != nil {
		return nil, "", err
	}
	req.Header.Set("Accept", "text/html,*/*")
	resp, err := m.httpClient().Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, "", statusErr{resp.StatusCode}
	}
	final := resp.Request.URL.String()
	if ct := resp.Header.Get("Content-Type"); ct != "" && !strings.Contains(ct, "html") && !strings.Contains(ct, "xml") {
		return nil, final, nil
	}
	z := html.NewTokenizer(io.LimitReader(resp.Body, 8<<20))
	var out []link
	cur := -1
	for {
		tt := z.Next()
		if tt == html.ErrorToken {
			break
		}
		switch tt {
		case html.StartTagToken, html.SelfClosingTagToken:
			tok := z.Token()
			get := func(k string) string {
				for _, a := range tok.Attr {
					if a.Key == k {
						return a.Val
					}
				}
				return ""
			}
			switch tok.Data {
			case "a", "area":
				if h := get("href"); h != "" && !strings.HasPrefix(h, "javascript:") && !strings.HasPrefix(h, "mailto:") {
					out = append(out, link{href: h, nav: true})
					cur = len(out) - 1
				}
			case "img", "source", "video", "audio", "embed", "track", "iframe":
				for _, k := range []string{"src", "data-src", "poster"} {
					if h := get(k); h != "" && !strings.HasPrefix(h, "data:") {
						out = append(out, link{href: h, text: get("alt")})
					}
				}
				if ss := get("srcset"); ss != "" {
					for _, part := range strings.Split(ss, ",") {
						if f := strings.Fields(part); len(f) > 0 {
							out = append(out, link{href: f[0]})
						}
					}
				}
			case "link":
				if h := get("href"); h != "" {
					out = append(out, link{href: h})
				}
			case "base":
				if h := get("href"); h != "" {
					final = resolveURL(final, h)
				}
			}
		case html.TextToken:
			if cur >= 0 && len(out[cur].text) < 80 {
				out[cur].text = strings.TrimSpace(out[cur].text + " " + strings.TrimSpace(string(z.Text())))
			}
		case html.EndTagToken:
			if n, _ := z.TagName(); string(n) == "a" {
				cur = -1
			}
		}
	}
	return out, final, nil
}

func (m *Manager) GrabStatus(id string, stop bool) *GrabJob {
	m.mu.Lock()
	j := m.grabs[id]
	m.mu.Unlock()
	if j == nil {
		return nil
	}
	if stop {
		j.cancel()
	}
	j.mu.Lock()
	defer j.mu.Unlock()
	return &GrabJob{ID: j.ID, Done: j.Done, Pages: j.Pages, Error: j.Error, Items: append([]GrabItem{}, j.Items...)}
}
