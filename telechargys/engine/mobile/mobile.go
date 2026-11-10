// Package mobile : façade du moteur pour l'application Android (gomobile bind).
package mobile

import (
	"context"
	"encoding/json"
	"errors"
	"io/fs"
	"strconv"
	"sync"
	"time"

	"telechargys/engine/core"
	"telechargys/engine/ui"
)

// Callback : évènements remontés à l'application Android.
type Callback interface {
	OnEvent(kind string, data string)
}

var (
	mu  sync.Mutex
	mgr *core.Manager
	srv *core.Server
)

// Start lance le moteur et renvoie "port|jeton".
func Start(dataDir, downloadDir string, cb Callback) (string, error) {
	mu.Lock()
	defer mu.Unlock()
	if mgr != nil {
		return strconv.Itoa(srv.Port) + "|" + mgr.Token, nil
	}
	m, err := core.NewManager(dataDir, downloadDir, "android")
	if err != nil {
		return "", err
	}
	if cb != nil {
		m.OnEvent = func(ev core.Event) {
			switch ev.Type {
			case "notify", "queueDone", "settings", "capture":
				b, _ := json.Marshal(ev.Data)
				cb.OnEvent(ev.Type, string(b))
			}
		}
	}
	web, _ := fs.Sub(ui.FS, "web")
	s, err := core.Serve(m, web)
	if err != nil {
		m.Shutdown()
		return "", err
	}
	mgr, srv = m, s
	return strconv.Itoa(s.Port) + "|" + m.Token, nil
}

func get() (*core.Manager, error) {
	mu.Lock()
	defer mu.Unlock()
	if mgr == nil {
		return nil, errors.New("moteur arrêté")
	}
	return mgr, nil
}

// Summary : {"active":1,"queued":0,"speed":123,"percent":42} pour la notification.
func Summary() string {
	m, err := get()
	if err != nil {
		return "{}"
	}
	b, _ := json.Marshal(m.Summary())
	return string(b)
}

// Settings : réglages en JSON.
func Settings() string {
	m, err := get()
	if err != nil {
		return "{}"
	}
	b, _ := json.Marshal(m.State().Settings)
	return string(b)
}

// AddURL : lien reçu par partage, par le navigateur intégré ou par « Ouvrir avec ».
func AddURL(url, referer, cookies, userAgent string) error {
	m, err := get()
	if err != nil {
		return err
	}
	return m.AddSimple(context.Background(), url, referer, cookies, userAgent)
}

// AddNamed : ajout direct d'un média détecté (nom proposé, démarrage immédiat).
func AddNamed(url, fileName, referer, cookies, userAgent string) error {
	m, err := get()
	if err != nil {
		return err
	}
	_, err = m.Add(core.AddReq{URL: url, FileName: fileName, Referer: referer, Cookies: cookies, UserAgent: userAgent, Start: true})
	return err
}

func PauseAll() {
	if m, err := get(); err == nil {
		m.PauseAll()
	}
}

func StartAll() {
	if m, err := get(); err == nil {
		m.StartAll()
	}
}

// SetBlocked : true quand le réseau ne convient pas (Wi-Fi uniquement, hors ligne).
func SetBlocked(b bool) {
	if m, err := get(); err == nil {
		m.SetBlocked(b)
	}
}

// Flush enregistre l'état sur le disque.
func Flush() {
	if m, err := get(); err == nil {
		m.Flush()
	}
}

// SetTimeZone : fuseau horaire du téléphone (Go ne le lit pas tout seul sur Android) ; sert au planificateur.
func SetTimeZone(name string) {
	if loc, err := time.LoadLocation(name); err == nil {
		time.Local = loc
	}
}
