package core

import (
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"

	mp4 "github.com/yapingcat/gomedia/go-mp4"
)

// ---------- DASH (.mpd) ----------

type mpdTimelineS struct {
	T *int64 `xml:"t,attr"`
	D int64  `xml:"d,attr"`
	R int64  `xml:"r,attr"`
}

type mpdTemplate struct {
	Init      string `xml:"initialization,attr"`
	Media     string `xml:"media,attr"`
	Start     *int64 `xml:"startNumber,attr"`
	Timescale int64  `xml:"timescale,attr"`
	Duration  int64  `xml:"duration,attr"`
	Timeline  *struct {
		S []mpdTimelineS `xml:"S"`
	} `xml:"SegmentTimeline"`
}

type mpdURLRange struct {
	Src   string `xml:"sourceURL,attr"`
	Range string `xml:"range,attr"`
}

type mpdList struct {
	Init *mpdURLRange `xml:"Initialization"`
	Segs []struct {
		Media string `xml:"media,attr"`
		Range string `xml:"mediaRange,attr"`
	} `xml:"SegmentURL"`
}

type mpdProtection struct {
	Scheme string `xml:"schemeIdUri,attr"`
}

type mpdRep struct {
	ID         string          `xml:"id,attr"`
	MimeType   string          `xml:"mimeType,attr"`
	Codecs     string          `xml:"codecs,attr"`
	Bandwidth  int64           `xml:"bandwidth,attr"`
	Width      int             `xml:"width,attr"`
	Height     int             `xml:"height,attr"`
	BaseURL    []string        `xml:"BaseURL"`
	Template   *mpdTemplate    `xml:"SegmentTemplate"`
	List       *mpdList        `xml:"SegmentList"`
	Base       *struct{}       `xml:"SegmentBase"`
	Protection []mpdProtection `xml:"ContentProtection"`
}

type mpdSet struct {
	MimeType    string          `xml:"mimeType,attr"`
	ContentType string          `xml:"contentType,attr"`
	Codecs      string          `xml:"codecs,attr"`
	Lang        string          `xml:"lang,attr"`
	BaseURL     []string        `xml:"BaseURL"`
	Template    *mpdTemplate    `xml:"SegmentTemplate"`
	List        *mpdList        `xml:"SegmentList"`
	Protection  []mpdProtection `xml:"ContentProtection"`
	Reps        []mpdRep        `xml:"Representation"`
}

type mpdPeriod struct {
	Duration string   `xml:"duration,attr"`
	BaseURL  []string `xml:"BaseURL"`
	Sets     []mpdSet `xml:"AdaptationSet"`
}

type mpdDoc struct {
	Type     string      `xml:"type,attr"`
	Duration string      `xml:"mediaPresentationDuration,attr"`
	BaseURL  []string    `xml:"BaseURL"`
	Periods  []mpdPeriod `xml:"Period"`
}

func isMPD(b []byte) bool {
	n := len(b)
	if n > 2048 {
		n = 2048
	}
	return strings.Contains(string(b[:n]), "<MPD")
}

func looksMPD(u string) bool {
	l := strings.ToLower(strings.SplitN(strings.SplitN(u, "?", 2)[0], "#", 2)[0])
	return strings.HasSuffix(l, ".mpd")
}

// looksStream : adresse d'un flux vidéo segmenté (HLS ou DASH).
func looksStream(u string) bool { return looksHLS(u) || looksMPD(u) }

var isoDurRe = regexp.MustCompile(`^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$`)

// parseISODur : "PT1H2M3.5S" -> secondes.
func parseISODur(s string) float64 {
	m := isoDurRe.FindStringSubmatch(strings.TrimSpace(s))
	if m == nil {
		return 0
	}
	f := func(x string) float64 { v, _ := strconv.ParseFloat(x, 64); return v }
	return f(m[1])*86400 + f(m[2])*3600 + f(m[3])*60 + f(m[4])
}

var tplRe = regexp.MustCompile(`\$(RepresentationID|Number|Time|Bandwidth)(?:%0(\d+)d)?\$`)

func fillTpl(t, rep string, bw, num, tm int64) string {
	t = tplRe.ReplaceAllStringFunc(t, func(s string) string {
		m := tplRe.FindStringSubmatch(s)
		var v int64
		switch m[1] {
		case "RepresentationID":
			return rep
		case "Number":
			v = num
		case "Time":
			v = tm
		case "Bandwidth":
			v = bw
		}
		if m[2] != "" {
			w, _ := strconv.Atoi(m[2])
			return fmt.Sprintf("%0*d", w, v)
		}
		return strconv.FormatInt(v, 10)
	})
	return strings.ReplaceAll(t, "$$", "$")
}

func parseRange(r string) (st, ln int64, ok bool) {
	p := strings.SplitN(strings.TrimSpace(r), "-", 2)
	if len(p) != 2 {
		return 0, 0, false
	}
	a, e1 := strconv.ParseInt(p[0], 10, 64)
	b, e2 := strconv.ParseInt(p[1], 10, 64)
	if e1 != nil || e2 != nil || b < a {
		return 0, 0, false
	}
	return a, b - a + 1, true
}

func mergeTpl(set, rep *mpdTemplate) *mpdTemplate {
	if set == nil && rep == nil {
		return nil
	}
	out := &mpdTemplate{}
	for _, t := range []*mpdTemplate{set, rep} {
		if t == nil {
			continue
		}
		if t.Init != "" {
			out.Init = t.Init
		}
		if t.Media != "" {
			out.Media = t.Media
		}
		if t.Start != nil {
			out.Start = t.Start
		}
		if t.Timescale > 0 {
			out.Timescale = t.Timescale
		}
		if t.Duration > 0 {
			out.Duration = t.Duration
		}
		if t.Timeline != nil {
			out.Timeline = t.Timeline
		}
	}
	return out
}

func joinBase(base string, chain ...[]string) string {
	for _, c := range chain {
		if len(c) > 0 && strings.TrimSpace(c[0]) != "" {
			base = resolveURL(base, strings.TrimSpace(c[0]))
		}
	}
	return base
}

type mpdPick struct {
	set *mpdSet
	rep *mpdRep
	id  string
}

func (p mpdPick) kind() string {
	mt := strings.ToLower(p.rep.MimeType + " " + p.set.MimeType + " " + p.set.ContentType)
	switch {
	case strings.Contains(mt, "video"):
		return "video"
	case strings.Contains(mt, "audio"):
		return "audio"
	}
	c := strings.ToLower(p.rep.Codecs + p.set.Codecs)
	if strings.HasPrefix(c, "mp4a") || strings.HasPrefix(c, "opus") || strings.HasPrefix(c, "ac-3") || strings.HasPrefix(c, "ec-3") {
		return "audio"
	}
	if p.rep.Width > 0 || strings.HasPrefix(c, "avc") || strings.HasPrefix(c, "hev") || strings.HasPrefix(c, "hvc") || strings.HasPrefix(c, "vp") || strings.HasPrefix(c, "av01") {
		return "video"
	}
	return "other"
}

func (p mpdPick) container() string {
	if strings.Contains(strings.ToLower(p.rep.MimeType+p.set.MimeType), "webm") {
		return "webm"
	}
	return "mp4"
}

// parseMPD : sans sélection, renvoie les qualités ; avec "r=ID", la liste des segments de cette représentation.
func parseMPD(body []byte, final, mpdURL, frag string) (*hlsPlaylist, error) {
	var doc mpdDoc
	if err := xml.Unmarshal(body, &doc); err != nil {
		return nil, fmt.Errorf("manifeste DASH illisible : %v", err)
	}
	if len(doc.Periods) == 0 {
		return nil, errors.New("manifeste DASH vide")
	}
	pl := &hlsPlaylist{Live: doc.Type == "dynamic", Container: "mp4"}
	// période la plus longue (les autres sont souvent des publicités)
	per := &doc.Periods[0]
	for i := range doc.Periods {
		if parseISODur(doc.Periods[i].Duration) > parseISODur(per.Duration) {
			per = &doc.Periods[i]
		}
	}
	total := parseISODur(per.Duration)
	if total == 0 {
		total = parseISODur(doc.Duration)
	}
	var picks []mpdPick
	for si := range per.Sets {
		s := &per.Sets[si]
		for ri := range s.Reps {
			r := &s.Reps[ri]
			id := r.ID
			if id == "" {
				id = fmt.Sprintf("_%d_%d", si, ri)
			}
			picks = append(picks, mpdPick{s, r, id})
		}
	}
	if frag == "" {
		var videos, audios []mpdPick
		for _, p := range picks {
			if len(p.set.Protection)+len(p.rep.Protection) > 0 {
				pl.DRM = true
			}
			switch p.kind() {
			case "video":
				videos = append(videos, p)
			case "audio":
				audios = append(audios, p)
			}
		}
		sort.SliceStable(videos, func(i, j int) bool { return videos[i].rep.Bandwidth > videos[j].rep.Bandwidth })
		sort.SliceStable(audios, func(i, j int) bool { return audios[i].rep.Bandwidth > audios[j].rep.Bandwidth })
		bestAudio := func(cont string) string {
			for _, a := range audios {
				if a.container() == cont {
					return mpdURL + "#r=" + a.id
				}
			}
			if len(audios) > 0 {
				return mpdURL + "#r=" + audios[0].id
			}
			return ""
		}
		for _, v := range videos {
			lbl := ""
			if v.rep.Height > 0 {
				lbl = fmt.Sprintf("%dp", v.rep.Height)
			}
			if v.rep.Bandwidth > 0 {
				if lbl != "" {
					lbl += " · "
				}
				lbl += fmt.Sprintf("%.1f Mb/s", float64(v.rep.Bandwidth)/1e6)
			}
			if v.container() == "webm" {
				lbl += " (WebM)"
			}
			res := ""
			if v.rep.Width > 0 {
				res = fmt.Sprintf("%dx%d", v.rep.Width, v.rep.Height)
			}
			pl.Variants = append(pl.Variants, HLSVariant{URL: mpdURL + "#r=" + v.id, AudioURL: bestAudio(v.container()), Bandwidth: v.rep.Bandwidth, Resolution: res, Label: strings.TrimSpace(lbl)})
		}
		if len(videos) == 0 { // son seul (musique, podcast)
			for _, a := range audios {
				pl.Variants = append(pl.Variants, HLSVariant{URL: mpdURL + "#r=" + a.id, Bandwidth: a.rep.Bandwidth, Label: fmt.Sprintf("Audio · %d kb/s", a.rep.Bandwidth/1000)})
			}
		}
		if len(pl.Variants) == 0 {
			return nil, errors.New("aucune piste vidéo ou audio dans ce manifeste")
		}
		return pl, nil
	}

	want := strings.TrimPrefix(frag, "r=")
	var p *mpdPick
	for i := range picks {
		if picks[i].id == want {
			p = &picks[i]
		}
	}
	if p == nil {
		return nil, errors.New("qualité introuvable dans le manifeste")
	}
	if len(p.set.Protection)+len(p.rep.Protection) > 0 {
		pl.DRM = true
	}
	pl.Container = p.container()
	base := joinBase(final, doc.BaseURL, per.BaseURL, p.set.BaseURL, p.rep.BaseURL)
	rid, bw := p.rep.ID, p.rep.Bandwidth
	seg := func(u string) hlsSeg { return hlsSeg{URL: u, RangeLn: -1, Seq: int64(len(pl.Segs))} }

	if t := mergeTpl(p.set.Template, p.rep.Template); t != nil && t.Media != "" {
		ts := t.Timescale
		if ts <= 0 {
			ts = 1
		}
		num := int64(1)
		if t.Start != nil {
			num = *t.Start
		}
		if t.Init != "" {
			pl.MapURL, pl.MapLn = resolveURL(base, fillTpl(t.Init, rid, bw, 0, 0)), -1
		}
		if t.Timeline != nil {
			var cur int64
			end := int64(total * float64(ts))
			for i, s := range t.Timeline.S {
				if s.T != nil {
					cur = *s.T
				}
				rep := s.R
				if rep < 0 { // répéter jusqu'au prochain S ou à la fin
					limit := end
					if i+1 < len(t.Timeline.S) && t.Timeline.S[i+1].T != nil {
						limit = *t.Timeline.S[i+1].T
					}
					if s.D > 0 && limit > cur {
						rep = int64(math.Ceil(float64(limit-cur)/float64(s.D))) - 1
					} else {
						rep = 0
					}
				}
				for k := int64(0); k <= rep; k++ {
					pl.Segs = append(pl.Segs, seg(resolveURL(base, fillTpl(t.Media, rid, bw, num, cur))))
					num++
					cur += s.D
					if len(pl.Segs) > 200000 {
						return nil, errors.New("manifeste DASH trop long")
					}
				}
			}
		} else {
			if t.Duration <= 0 || total <= 0 {
				return nil, errors.New("durée du flux DASH inconnue")
			}
			n := int64(math.Ceil(total * float64(ts) / float64(t.Duration)))
			if n > 200000 {
				return nil, errors.New("manifeste DASH trop long")
			}
			for i := int64(0); i < n; i++ {
				pl.Segs = append(pl.Segs, seg(resolveURL(base, fillTpl(t.Media, rid, bw, num+i, i*t.Duration))))
			}
		}
	} else if l := p.rep.List; l != nil || p.set.List != nil {
		if l == nil {
			l = p.set.List
		}
		if l.Init != nil {
			pl.MapURL, pl.MapLn = base, -1
			if l.Init.Src != "" {
				pl.MapURL = resolveURL(base, l.Init.Src)
			}
			if st, ln, ok := parseRange(l.Init.Range); ok {
				pl.MapSt, pl.MapLn = st, ln
			}
		}
		for _, s := range l.Segs {
			u := base
			if s.Media != "" {
				u = resolveURL(base, s.Media)
			}
			sg := seg(u)
			if st, ln, ok := parseRange(s.Range); ok {
				sg.RangeSt, sg.RangeLn = st, ln
			}
			pl.Segs = append(pl.Segs, sg)
		}
	} else {
		// SegmentBase ou simple BaseURL : la piste est un fichier complet
		pl.Segs = []hlsSeg{seg(base)}
	}
	if len(pl.Segs) == 0 {
		return nil, errors.New("aucun segment dans cette piste DASH")
	}
	return pl, nil
}

// ---------- fusion vidéo + audio (MP4) ----------

type mp4src struct {
	f    *os.File
	dem  *mp4.MovDemuxer
	next *mp4.AVPacket
	done bool
}

func (s *mp4src) peek() *mp4.AVPacket {
	if s.next == nil && !s.done {
		p, err := s.dem.ReadPacket()
		if err != nil {
			s.done = true
			return nil
		}
		s.next = p
	}
	return s.next
}

// mergeMP4 réunit une piste vidéo et une piste audio (MP4 ou MP4 fragmenté) en un seul MP4, sans réencodage.
func mergeMP4(ctx context.Context, paths []string, out string) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("fusion impossible : %v", r)
		}
	}()
	var srcs []*mp4src
	defer func() {
		for _, s := range srcs {
			s.f.Close()
		}
	}()
	for _, p := range paths {
		f, err := os.Open(p)
		if err != nil {
			return err
		}
		s := &mp4src{f: f, dem: mp4.CreateMp4Demuxer(f)}
		srcs = append(srcs, s)
		tracks, err := s.dem.ReadHead()
		if err != nil && err != io.EOF {
			return err
		}
		if len(tracks) == 0 {
			return errors.New("piste illisible")
		}
		for _, t := range tracks {
			switch t.Cid {
			case mp4.MP4_CODEC_H264, mp4.MP4_CODEC_H265, mp4.MP4_CODEC_AAC, mp4.MP4_CODEC_MP3:
			default:
				return fmt.Errorf("codec non pris en charge pour la fusion (%v)", t.Cid)
			}
		}
	}
	f, err := os.Create(out)
	if err != nil {
		return err
	}
	defer f.Close()
	mux, err := mp4.CreateMp4Muxer(f)
	if err != nil {
		return err
	}
	ids := map[[2]int]uint32{}
	var base uint64
	haveBase := false
	for _, s := range srcs {
		if p := s.peek(); p != nil && (!haveBase || p.Dts < base) {
			base, haveBase = p.Dts, true
		}
	}
	frames := 0
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		var pick *mp4src
		var pi int
		for i, s := range srcs {
			p := s.peek()
			if p == nil {
				continue
			}
			if pick == nil || p.Dts < pick.next.Dts {
				pick, pi = s, i
			}
		}
		if pick == nil {
			break
		}
		p := pick.next
		pick.next = nil
		key := [2]int{pi, p.TrackId}
		id, ok := ids[key]
		if !ok {
			switch p.Cid {
			case mp4.MP4_CODEC_H264, mp4.MP4_CODEC_H265:
				id = mux.AddVideoTrack(p.Cid)
			default:
				id = mux.AddAudioTrack(p.Cid)
			}
			ids[key] = id
		}
		dts, pts := p.Dts, p.Pts
		if dts < base {
			dts = base
		}
		if pts < dts {
			pts = dts
		}
		if err := mux.Write(id, p.Data, pts-base, dts-base); err != nil {
			return err
		}
		frames++
	}
	if frames == 0 {
		return errors.New("aucune image à fusionner")
	}
	return mux.WriteTrailer()
}
