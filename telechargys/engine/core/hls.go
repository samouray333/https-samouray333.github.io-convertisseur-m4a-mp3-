package core

import (
	"bufio"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	mp4 "github.com/yapingcat/gomedia/go-mp4"
	mpeg2 "github.com/yapingcat/gomedia/go-mpeg2"
)

// HLSVariant : une qualité proposée par une playlist maître.
type HLSVariant struct {
	URL        string `json:"url"`
	AudioURL   string `json:"audioUrl,omitempty"`
	Bandwidth  int64  `json:"bandwidth"`
	Resolution string `json:"resolution,omitempty"`
	Label      string `json:"label"`
}

type hlsSeg struct {
	URL     string
	KeyURL  string
	IV      []byte
	Seq     int64
	RangeLn int64 // -1 = fichier entier
	RangeSt int64
}

type hlsPlaylist struct {
	Variants []HLSVariant
	Segs     []hlsSeg
	MapURL   string
	MapLn    int64
	MapSt    int64
	Live      bool
	DRM       bool
	Container string // ts, mp4 ou webm
}

func attrs(line string) map[string]string {
	out := map[string]string{}
	i := strings.Index(line, ":")
	if i < 0 {
		return out
	}
	s := line[i+1:]
	for len(s) > 0 {
		eq := strings.Index(s, "=")
		if eq < 0 {
			break
		}
		k := strings.TrimSpace(s[:eq])
		s = s[eq+1:]
		var v string
		if strings.HasPrefix(s, `"`) {
			end := strings.Index(s[1:], `"`)
			if end < 0 {
				v, s = s[1:], ""
			} else {
				v, s = s[1:1+end], s[end+2:]
			}
			s = strings.TrimPrefix(s, ",")
		} else {
			end := strings.Index(s, ",")
			if end < 0 {
				v, s = s, ""
			} else {
				v, s = s[:end], s[end+1:]
			}
		}
		out[strings.ToUpper(k)] = v
	}
	return out
}

func resolveURL(base, ref string) string {
	b, err := url.Parse(base)
	if err != nil {
		return ref
	}
	r, err := url.Parse(strings.TrimSpace(ref))
	if err != nil {
		return ref
	}
	return b.ResolveReference(r).String()
}

func parseByteRange(v string, prevEnd int64) (ln, st int64) {
	p := strings.SplitN(v, "@", 2)
	ln, _ = strconv.ParseInt(p[0], 10, 64)
	st = prevEnd
	if len(p) == 2 {
		st, _ = strconv.ParseInt(p[1], 10, 64)
	}
	return
}

func parseM3U8(body, base string) (*hlsPlaylist, error) {
	if !strings.Contains(body, "#EXTM3U") {
		return nil, errors.New("ce lien n'est pas une playlist HLS valide")
	}
	pl := &hlsPlaylist{Live: true}
	sc := bufio.NewScanner(strings.NewReader(body))
	sc.Buffer(make([]byte, 1<<20), 8<<20)
	audio := map[string]string{}
	var pendingVar *HLSVariant
	var pendingGroup string
	var keyURL string
	var keyIV []byte
	var seq int64
	var brLn, brEnd int64 = -1, 0
	groups := map[int]string{}
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		switch {
		case strings.HasPrefix(line, "#EXT-X-STREAM-INF"):
			a := attrs(line)
			v := HLSVariant{Resolution: a["RESOLUTION"]}
			v.Bandwidth, _ = strconv.ParseInt(a["BANDWIDTH"], 10, 64)
			pendingVar = &v
			pendingGroup = a["AUDIO"]
		case strings.HasPrefix(line, "#EXT-X-MEDIA:"):
			a := attrs(line)
			if a["TYPE"] == "AUDIO" && a["URI"] != "" {
				if _, ok := audio[a["GROUP-ID"]]; !ok || a["DEFAULT"] == "YES" {
					audio[a["GROUP-ID"]] = resolveURL(base, a["URI"])
				}
			}
		case strings.HasPrefix(line, "#EXT-X-MEDIA-SEQUENCE"):
			seq, _ = strconv.ParseInt(strings.TrimSpace(line[strings.Index(line, ":")+1:]), 10, 64)
		case strings.HasPrefix(line, "#EXT-X-KEY"):
			a := attrs(line)
			switch a["METHOD"] {
			case "NONE", "":
				keyURL, keyIV = "", nil
			case "AES-128":
				if strings.HasPrefix(a["URI"], "skd:") || (a["KEYFORMAT"] != "" && a["KEYFORMAT"] != "identity") {
					pl.DRM = true
				}
				keyURL = resolveURL(base, a["URI"])
				keyIV = nil
				if iv := strings.TrimPrefix(strings.TrimPrefix(a["IV"], "0x"), "0X"); iv != "" {
					if b, err := hex.DecodeString(iv); err == nil && len(b) == 16 {
						keyIV = b
					}
				}
			default:
				pl.DRM = true
			}
		case strings.HasPrefix(line, "#EXT-X-MAP"):
			a := attrs(line)
			pl.MapURL = resolveURL(base, a["URI"])
			pl.MapLn = -1
			if br := a["BYTERANGE"]; br != "" {
				pl.MapLn, pl.MapSt = parseByteRange(br, 0)
			}
		case strings.HasPrefix(line, "#EXT-X-BYTERANGE"):
			var st int64
			brLn, st = parseByteRange(strings.TrimSpace(line[strings.Index(line, ":")+1:]), brEnd)
			brEnd = st
		case strings.HasPrefix(line, "#EXT-X-ENDLIST"):
			pl.Live = false
		case strings.HasPrefix(line, "#EXT-X-PLAYLIST-TYPE"):
			if strings.Contains(line, "VOD") {
				pl.Live = false
			}
		case strings.HasPrefix(line, "#"):
		default:
			if pendingVar != nil {
				pendingVar.URL = resolveURL(base, line)
				groups[len(pl.Variants)] = pendingGroup
				pl.Variants = append(pl.Variants, *pendingVar)
				pendingVar = nil
				continue
			}
			s := hlsSeg{URL: resolveURL(base, line), KeyURL: keyURL, IV: keyIV, Seq: seq, RangeLn: -1}
			if brLn >= 0 {
				s.RangeLn, s.RangeSt = brLn, brEnd
				brEnd += brLn
				brLn = -1
			}
			seq++
			pl.Segs = append(pl.Segs, s)
		}
	}
	for i := range pl.Variants {
		v := &pl.Variants[i]
		v.AudioURL = audio[groups[i]]
		lbl := ""
		if p := strings.SplitN(v.Resolution, "x", 2); len(p) == 2 {
			lbl = p[1] + "p"
		}
		if v.Bandwidth > 0 {
			if lbl != "" {
				lbl += " · "
			}
			lbl += fmt.Sprintf("%.1f Mb/s", float64(v.Bandwidth)/1e6)
		}
		if lbl == "" {
			lbl = fmt.Sprintf("Qualité %d", i+1)
		}
		v.Label = lbl
	}
	sort.SliceStable(pl.Variants, func(i, j int) bool { return pl.Variants[i].Bandwidth > pl.Variants[j].Bandwidth })
	pl.Container = "ts"
	if pl.MapURL != "" {
		pl.Container = "mp4"
	}
	return pl, nil
}

func (m *Manager) fetchSmall(ctx context.Context, d *Download, u string, from, ln int64) ([]byte, string, error) {
	req, err := m.newRequest(ctx, d, u, -1)
	if err != nil {
		return nil, "", err
	}
	if ln >= 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", from, from+ln-1))
	}
	resp, err := m.httpClient().Do(req)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, "", statusErr{resp.StatusCode}
	}
	b, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	return b, resp.Request.URL.String(), err
}

func (m *Manager) loadPlaylist(ctx context.Context, d *Download, u string) (*hlsPlaylist, error) {
	src, frag, _ := strings.Cut(u, "#")
	b, final, err := m.fetchSmall(ctx, d, src, 0, -1)
	if err != nil {
		return nil, friendlyErr(err)
	}
	return parseStream(b, final, src, frag)
}

// parseStream reconnaît une playlist HLS ou un manifeste DASH.
func parseStream(b []byte, final, src, frag string) (*hlsPlaylist, error) {
	if isMPD(b) {
		return parseMPD(b, final, src, frag)
	}
	return parseM3U8(string(b), final)
}

type hlsTrack struct {
	pl   *hlsPlaylist
	dir  string
	off  int // décalage dans le bitmap
	keys sync.Map
}

// runHLS télécharge un flux HLS : segments en parallèle, déchiffrement AES-128, assemblage.
func (m *Manager) runHLS(ctx context.Context, d *Download) error {
	m.mu.Lock()
	conns, retries, waitSec, toMP4 := m.S.HLSConn, m.S.Retries, m.S.RetryWaitSec, m.S.HLSToMP4
	timeout := time.Duration(m.S.TimeoutSec) * time.Second
	if d.HLS == nil {
		d.HLS = &HLSState{}
	}
	mediaURL, audioURL := d.HLS.MediaURL, d.HLS.AudioURL
	m.mu.Unlock()
	if d.MaxConn > 0 {
		conns = d.MaxConn
	}
	if conns > 16 {
		conns = 16
	}
	if mediaURL == "" {
		mediaURL = d.URL
	}
	pl, err := m.loadPlaylist(ctx, d, mediaURL)
	if err != nil {
		if ctx.Err() != nil {
			return nil
		}
		return err
	}
	if len(pl.Variants) > 0 { // playlist maître : meilleure qualité par défaut
		v := pl.Variants[0]
		mediaURL, audioURL = v.URL, v.AudioURL
		m.mu.Lock()
		d.HLS.MediaURL, d.HLS.AudioURL, d.HLS.Quality = v.URL, v.AudioURL, v.Label
		m.mu.Unlock()
		if pl, err = m.loadPlaylist(ctx, d, mediaURL); err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
	}
	if pl.DRM {
		return errors.New("flux protégé par DRM : non pris en charge")
	}
	if len(pl.Segs) == 0 {
		return errors.New("playlist vide")
	}
	if pl.Live {
		return errors.New("flux en direct : seules les vidéos complètes sont prises en charge")
	}
	base := m.partPath(d) + "s"
	tracks := []*hlsTrack{{pl: pl, dir: filepath.Join(base, "v")}}
	if audioURL != "" {
		apl, err := m.loadPlaylist(ctx, d, audioURL)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		if apl.DRM {
			return errors.New("flux protégé par DRM : non pris en charge")
		}
		tracks = append(tracks, &hlsTrack{pl: apl, dir: filepath.Join(base, "a"), off: len(pl.Segs)})
	}
	total := 0
	for _, t := range tracks {
		total += len(t.pl.Segs)
		if err := os.MkdirAll(t.dir, 0o755); err != nil {
			return err
		}
	}
	if !d.Probed {
		m.reserveName(d, "")
	}
	m.mu.Lock()
	d.Probed, d.Resumable = true, true
	d.mu.Lock()
	if d.HLS.Total != total || len(d.HLS.DoneBits) != (total+7)/8 {
		d.HLS.Total, d.HLS.Done, d.HLS.DoneBits = total, 0, make([]byte, (total+7)/8)
		d.dlCount.Store(0)
	}
	d.mu.Unlock()
	m.changed(d)
	m.mu.Unlock()

	isDone := func(i int) bool { return d.HLS.DoneBits[i/8]&(1<<(i%8)) != 0 }
	type job struct {
		t *hlsTrack
		i int
	}
	jobs := make(chan job, total)
	d.mu.Lock()
	for _, t := range tracks {
		for i := range t.pl.Segs {
			if !isDone(t.off + i) {
				jobs <- job{t, i}
			} else if _, err := os.Stat(segPath(t, i)); err != nil {
				d.HLS.DoneBits[(t.off+i)/8] &^= 1 << ((t.off + i) % 8)
				d.HLS.Done--
				jobs <- job{t, i}
			}
		}
	}
	d.mu.Unlock()
	close(jobs)

	wctx, wcancel := context.WithCancel(ctx)
	defer wcancel()
	var wg sync.WaitGroup
	var errMu sync.Mutex
	var firstErr error
	for w := 0; w < conns; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			m.mu.Lock()
			d.Conns++
			m.mu.Unlock()
			defer func() { m.mu.Lock(); d.Conns--; m.mu.Unlock() }()
			for j := range jobs {
				if wctx.Err() != nil {
					return
				}
				var err error
				for try := 0; try <= retries; try++ {
					err = m.hlsSegment(wctx, d, j.t, j.i, timeout)
					if err == nil || wctx.Err() != nil {
						break
					}
					var se statusErr
					if errors.As(err, &se) && se.code < 500 && se.code != 429 && se.code != 408 {
						break
					}
					select {
					case <-wctx.Done():
					case <-time.After(time.Duration(waitSec) * time.Second):
					}
				}
				if wctx.Err() != nil {
					return
				}
				if err != nil {
					errMu.Lock()
					if firstErr == nil {
						firstErr = fmt.Errorf("segment %d : %v", j.i+1, friendlyErr(err))
					}
					errMu.Unlock()
					wcancel()
					return
				}
				d.mu.Lock()
				k := j.t.off + j.i
				d.HLS.DoneBits[k/8] |= 1 << (k % 8)
				d.HLS.Done++
				d.mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if ctx.Err() != nil {
		return nil
	}
	if firstErr != nil {
		return firstErr
	}

	// ----- assemblage -----
	m.mu.Lock()
	d.Status = StMerging
	m.changed(d)
	m.mu.Unlock()
	nameBase := strings.TrimSuffix(d.FileName, filepath.Ext(d.FileName))
	setName := func(ext string) string {
		m.mu.Lock()
		defer m.mu.Unlock()
		d.FileName = filepath.Base(uniquePath(filepath.Join(d.Dir, nameBase+ext), nil))
		return filepath.Join(d.Dir, d.FileName)
	}
	var outErr error
	if pl.Container != "ts" {
		// MP4 fragmenté / WebM : en-tête + fragments = fichier lisible tel quel
		ext := "." + pl.Container
		var parts []string
		for ti, t := range tracks {
			var init []byte
			if t.pl.MapURL != "" {
				b, _, err := m.fetchSmall(ctx, d, t.pl.MapURL, t.pl.MapSt, t.pl.MapLn)
				if err != nil {
					if ctx.Err() != nil {
						return nil
					}
					return friendlyErr(err)
				}
				init = b
			}
			tmp := filepath.Join(base, fmt.Sprintf("piste%d.%s", ti, t.pl.Container))
			if outErr = concatSegs(ctx, t, tmp, init); outErr != nil {
				break
			}
			parts = append(parts, tmp)
		}
		if outErr == nil && len(parts) == 1 {
			outErr = moveFile(parts[0], setName(ext))
		} else if outErr == nil {
			merged := false
			if pl.Container == "mp4" && tracks[1].pl.Container == "mp4" {
				out := setName(".mp4")
				if err := mergeMP4(ctx, parts, out); err == nil {
					merged = true
				} else {
					os.Remove(out)
				}
			}
			if !merged && ctx.Err() == nil {
				// codecs non fusionnables (VP9, Opus...) : vidéo et son côte à côte
				if outErr = moveFile(parts[0], setName(ext)); outErr == nil {
					aext := ".audio.m4a"
					if tracks[1].pl.Container == "webm" {
						aext = ".audio.webm"
					}
					outErr = moveFile(parts[1], uniquePath(filepath.Join(d.Dir, nameBase+aext), nil))
				}
			}
		}
		m.mu.Lock()
		d.HLS.Container = pl.Container
		m.mu.Unlock()
	} else {
		done := false
		if toMP4 {
			out := setName(".mp4")
			if err := remuxTS(ctx, tracks, out); err == nil {
				done = true
				m.mu.Lock()
				d.HLS.Container = "mp4"
				m.mu.Unlock()
			} else {
				os.Remove(out)
			}
		}
		if !done && ctx.Err() == nil {
			out := setName(".ts")
			outErr = concatSegs(ctx, tracks[0], out, nil)
			if outErr == nil && len(tracks) > 1 {
				outErr = concatSegs(ctx, tracks[1], uniquePath(filepath.Join(d.Dir, nameBase+".audio.ts"), nil), nil)
			}
			m.mu.Lock()
			d.HLS.Container = "ts"
			m.mu.Unlock()
		}
	}
	if ctx.Err() != nil {
		return nil
	}
	if outErr != nil {
		return fmt.Errorf("assemblage impossible : %v", outErr)
	}
	if st, err := os.Stat(filepath.Join(d.Dir, d.FileName)); err == nil {
		d.dlCount.Store(st.Size())
	}
	os.RemoveAll(base)
	return nil
}

func segPath(t *hlsTrack, i int) string { return filepath.Join(t.dir, fmt.Sprintf("%06d.seg", i)) }

func (m *Manager) hlsSegment(ctx context.Context, d *Download, t *hlsTrack, i int, timeout time.Duration) error {
	s := t.pl.Segs[i]
	rctx, cancel := context.WithCancel(ctx)
	defer cancel()
	req, err := m.newRequest(rctx, d, s.URL, -1)
	if err != nil {
		return err
	}
	if s.RangeLn >= 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", s.RangeSt, s.RangeSt+s.RangeLn-1))
	}
	resp, err := m.httpClient().Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return statusErr{resp.StatusCode}
	}
	tmp := segPath(t, i) + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	var w io.Writer = f
	var dec *cbcWriter
	if s.KeyURL != "" {
		var key []byte
		if k, ok := t.keys.Load(s.KeyURL); ok {
			key = k.([]byte)
		} else {
			kb, _, err := m.fetchSmall(ctx, d, s.KeyURL, 0, -1)
			if err != nil || len(kb) != 16 {
				f.Close()
				os.Remove(tmp)
				if err == nil {
					err = errors.New("clé de déchiffrement invalide")
				}
				return err
			}
			key = kb
			t.keys.Store(s.KeyURL, kb)
		}
		iv := s.IV
		if iv == nil {
			iv = make([]byte, 16)
			binary.BigEndian.PutUint64(iv[8:], uint64(s.Seq))
		}
		blk, _ := aes.NewCipher(key)
		dec = &cbcWriter{w: f, mode: cipher.NewCBCDecrypter(blk, iv)}
		w = dec
	}
	stall := time.AfterFunc(timeout, cancel)
	defer stall.Stop()
	buf := make([]byte, 64*1024)
	var got int64
	for {
		n, rerr := resp.Body.Read(buf[:m.global.chunk(d.limiter.chunk(len(buf)))])
		stall.Reset(timeout)
		if n > 0 {
			if _, e := w.Write(buf[:n]); e != nil {
				f.Close()
				os.Remove(tmp)
				return e
			}
			got += int64(n)
			d.dlCount.Add(int64(n))
			d.limiter.Wait(rctx, n)
			m.global.Wait(rctx, n)
		}
		if rerr == io.EOF {
			break
		}
		if rerr != nil {
			f.Close()
			os.Remove(tmp)
			d.dlCount.Add(-got)
			return rerr
		}
	}
	if dec != nil {
		if err := dec.finish(); err != nil {
			f.Close()
			os.Remove(tmp)
			d.dlCount.Add(-got)
			return err
		}
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, segPath(t, i))
}

// cbcWriter déchiffre un flux AES-128-CBC à la volée et retire le bourrage PKCS7 à la fin.
type cbcWriter struct {
	w    io.Writer
	mode cipher.BlockMode
	buf  []byte
	last []byte
}

func (c *cbcWriter) Write(p []byte) (int, error) {
	c.buf = append(c.buf, p...)
	n := len(c.buf) / 16 * 16
	if n == 0 {
		return len(p), nil
	}
	out := make([]byte, n)
	c.mode.CryptBlocks(out, c.buf[:n])
	c.buf = append(c.buf[:0], c.buf[n:]...)
	if c.last != nil {
		if _, err := c.w.Write(c.last); err != nil {
			return 0, err
		}
	}
	if _, err := c.w.Write(out[:n-16]); err != nil {
		return 0, err
	}
	c.last = append(c.last[:0], out[n-16:]...)
	return len(p), nil
}

func (c *cbcWriter) finish() error {
	if len(c.buf) != 0 || c.last == nil {
		return errors.New("segment chiffré tronqué")
	}
	pad := int(c.last[15])
	if pad < 1 || pad > 16 {
		return errors.New("déchiffrement incorrect (mauvaise clé ?)")
	}
	_, err := c.w.Write(c.last[:16-pad])
	return err
}

func concatSegs(ctx context.Context, t *hlsTrack, out string, head []byte) error {
	f, err := os.Create(out)
	if err != nil {
		return err
	}
	defer f.Close()
	if head != nil {
		if _, err := f.Write(head); err != nil {
			return err
		}
	}
	for i := range t.pl.Segs {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		in, err := os.Open(segPath(t, i))
		if err != nil {
			return err
		}
		_, err = io.Copy(f, in)
		in.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

// remuxTS convertit des segments MPEG-TS (H.264/H.265 + AAC/MP3) en un vrai fichier MP4, sans réencodage.
func remuxTS(ctx context.Context, tracks []*hlsTrack, out string) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("conversion MP4 impossible : %v", r)
		}
	}()
	f, err := os.Create(out)
	if err != nil {
		return err
	}
	defer f.Close()
	mux, err := mp4.CreateMp4Muxer(f)
	if err != nil {
		return err
	}
	ids := map[mpeg2.TS_STREAM_TYPE]uint32{}
	var base uint64
	haveBase := false
	frames := 0
	var werr error
	var aacBase, aacN, aacLast uint64
	aacInit := false
	onFrame := func(cid mpeg2.TS_STREAM_TYPE, frame []byte, pts uint64, dts uint64) {
		if werr != nil {
			return
		}
		id, ok := ids[cid]
		if !ok {
			switch cid {
			case mpeg2.TS_STREAM_H264:
				id = mux.AddVideoTrack(mp4.MP4_CODEC_H264)
			case mpeg2.TS_STREAM_H265:
				id = mux.AddVideoTrack(mp4.MP4_CODEC_H265)
			case mpeg2.TS_STREAM_AAC:
				id = mux.AddAudioTrack(mp4.MP4_CODEC_AAC)
			case mpeg2.TS_STREAM_AUDIO_MPEG1, mpeg2.TS_STREAM_AUDIO_MPEG2:
				id = mux.AddAudioTrack(mp4.MP4_CODEC_MP3)
			default:
				werr = fmt.Errorf("codec non géré (%d)", cid)
				return
			}
			ids[cid] = id
		}
		if !haveBase {
			base, haveBase = dts, true
			if pts < base {
				base = pts
			}
		}
		if dts < base {
			dts = base
		}
		if pts < dts {
			pts = dts
		}
		if cid == mpeg2.TS_STREAM_AAC {
			// un paquet PES contient souvent plusieurs trames ADTS : on les sépare et on les horodate une à une
			for len(frame) >= 7 && frame[0] == 0xFF && frame[1]&0xF0 == 0xF0 {
				ln := int(frame[3]&0x03)<<11 | int(frame[4])<<3 | int(frame[5])>>5
				if ln < 7 || ln > len(frame) {
					break
				}
				sr := adtsRates[(frame[2]>>2)&0x0F]
				if sr == 0 {
					sr = 44100
				}
				ts := aacBase + aacN*1024*1000/uint64(sr)
				if !aacInit || dts-base > ts+150 || ts > dts-base+150 { // (re)synchronisation
					aacBase, aacN, aacInit = dts-base, 0, true
					ts = aacBase
					if ts <= aacLast && aacLast > 0 {
						ts = aacLast + 1
						aacBase = ts
					}
				}
				aacN++
				aacLast = ts
				if e := mux.Write(id, frame[:ln], ts, ts); e != nil {
					werr = e
					return
				}
				frame = frame[ln:]
				frames++
			}
			return
		}
		if e := mux.Write(id, frame, pts-base, dts-base); e != nil {
			werr = e
		}
		frames++
	}
	// un démultiplexeur par piste, alimenté segment par segment pour entrelacer vidéo et audio
	dem := make([]*mpeg2.TSDemuxer, len(tracks))
	for i := range tracks {
		dem[i] = mpeg2.NewTSDemuxer()
		dem[i].OnFrame = onFrame
	}
	n := 0
	for _, t := range tracks {
		if len(t.pl.Segs) > n {
			n = len(t.pl.Segs)
		}
	}
	for i := 0; i < n; i++ {
		for ti, t := range tracks {
			if i >= len(t.pl.Segs) {
				continue
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			in, e := os.Open(segPath(t, i))
			if e != nil {
				return e
			}
			e = dem[ti].Input(bufio.NewReaderSize(in, 256*1024))
			in.Close()
			if e != nil && e != io.EOF && !errors.Is(e, io.ErrUnexpectedEOF) {
				return e
			}
			if werr != nil {
				return werr
			}
		}
	}
	if frames == 0 {
		return errors.New("aucune image décodable")
	}
	return mux.WriteTrailer()
}

var adtsRates = [16]int{96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350}
