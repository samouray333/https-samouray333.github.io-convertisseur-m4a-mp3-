package core

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"sync/atomic"
	"time"

	"github.com/jlaffaye/ftp"
)

// runFTP : téléchargement FTP (une connexion, reprise prise en charge via REST).
func (m *Manager) runFTP(ctx context.Context, d *Download) error {
	u, err := url.Parse(d.URL)
	if err != nil {
		return errors.New("adresse FTP invalide")
	}
	host := u.Host
	if u.Port() == "" {
		host += ":21"
	}
	m.mu.Lock()
	timeout := time.Duration(m.S.TimeoutSec) * time.Second
	m.mu.Unlock()
	c, err := ftp.Dial(host, ftp.DialWithTimeout(timeout), ftp.DialWithContext(ctx))
	if err != nil {
		if ctx.Err() != nil {
			return nil
		}
		return friendlyErr(err)
	}
	defer c.Quit()
	user, pass := "anonymous", "anonymous@"
	if d.Username != "" {
		user, pass = d.Username, d.Password
	} else if u.User != nil {
		user = u.User.Username()
		pass, _ = u.User.Password()
	}
	if err := c.Login(user, pass); err != nil {
		return fmt.Errorf("connexion FTP refusée : %v", err)
	}
	path, _ := url.PathUnescape(u.Path)
	size, err := c.FileSize(path)
	if err != nil {
		size = -1
	}
	var seg *Segment
	d.mu.Lock()
	if d.Probed && len(d.Segments) == 1 && d.Size == size && size > 0 {
		if st, e := os.Stat(m.partPath(d)); e == nil && st.Size() >= d.Segments[0].Pos {
			seg = d.Segments[0]
		}
	}
	d.mu.Unlock()
	if seg == nil {
		if !d.Probed {
			m.reserveName(d, "")
		}
		os.Remove(m.partPath(d))
		end := size - 1
		if size <= 0 {
			end = 1<<62 - 1
		}
		seg = &Segment{End: end}
		m.mu.Lock()
		d.Size, d.Probed, d.Resumable = size, true, size > 0
		d.mu.Lock()
		d.Segments = []*Segment{seg}
		d.mu.Unlock()
		d.dlCount.Store(0)
		m.changed(d)
		m.mu.Unlock()
	}
	f, err := os.OpenFile(m.partPath(d), os.O_RDWR|os.O_CREATE, 0o644)
	if err != nil {
		return fmt.Errorf("impossible de créer le fichier : %v", err)
	}
	r, err := c.RetrFrom(path, uint64(seg.pos()))
	if err != nil {
		f.Close()
		return fmt.Errorf("FTP : %v", err)
	}
	atomic.StoreInt32(&seg.active, 1)
	defer atomic.StoreInt32(&seg.active, 0)
	stop := context.AfterFunc(ctx, func() { r.Close() })
	defer stop()
	buf := make([]byte, 64*1024)
	var rerr error
	for {
		r.SetDeadline(time.Now().Add(timeout))
		n, e := r.Read(buf[:m.global.chunk(d.limiter.chunk(len(buf)))])
		if n > 0 {
			if _, we := f.WriteAt(buf[:n], seg.pos()); we != nil {
				rerr = fmt.Errorf("écriture impossible (disque plein ?) : %v", we)
				break
			}
			atomic.AddInt64(&seg.Pos, int64(n))
			d.dlCount.Add(int64(n))
			d.limiter.Wait(ctx, n)
			m.global.Wait(ctx, n)
		}
		if e != nil {
			if e != io.EOF {
				rerr = e
			}
			break
		}
	}
	r.Close()
	f.Close()
	if ctx.Err() != nil {
		return nil
	}
	if rerr != nil {
		return friendlyErr(rerr)
	}
	if size > 0 && seg.pos() < size {
		return errors.New("connexion interrompue")
	}
	if size <= 0 {
		m.mu.Lock()
		d.Size = seg.pos()
		m.mu.Unlock()
	}
	return m.finishFile(d)
}
