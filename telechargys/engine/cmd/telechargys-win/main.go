//go:build windows

// Telechargys pour Windows : un seul exécutable léger (moteur + interface WebView2 + zone de notification).
package main

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"fyne.io/systray"
	"github.com/jchv/go-webview2"
	"github.com/jchv/go-webview2/webviewloader"
	"golang.org/x/sys/windows"

	"telechargys/engine/core"
	"telechargys/engine/ui"
)

//go:embed assets/tray.ico
var trayIcon []byte

//go:embed assets/icon.png
var appPNG []byte

const aumid = "QMTech.Telechargys"

// App : état de l'application de bureau.
type App struct {
	m        *core.Manager
	srv      *core.Server
	base     string
	dataDir  string
	wvData   string
	portable bool
	main     webview2.WebView
	hwnd     uintptr

	mu         sync.Mutex
	settings   core.Settings
	quitting   bool
	prog       map[string]webview2.WebView
	lastStatus map[string]string
	postCancel chan struct{}
	clipStop   chan struct{}
	lastClip   string
}

func main() {
	runtime.LockOSThread() // l'interface Windows vit sur ce fil

	exe, _ := os.Executable()
	exeDir := filepath.Dir(exe)
	hidden := false
	var urls []string
	for _, a := range os.Args[1:] {
		switch {
		case a == "--hidden":
			hidden = true
		case strings.HasPrefix(strings.ToLower(a), "http://"), strings.HasPrefix(strings.ToLower(a), "https://"), strings.HasPrefix(strings.ToLower(a), "ftp://"):
			urls = append(urls, a)
		}
	}

	// mode portable : un fichier « portable.txt » à côté de l'exécutable garde tout dans le dossier
	app := &App{prog: map[string]webview2.WebView{}, lastStatus: map[string]string{}}
	dlDir := ""
	if _, err := os.Stat(filepath.Join(exeDir, "portable.txt")); err == nil {
		app.portable = true
		app.dataDir = filepath.Join(exeDir, "donnees")
		app.wvData = filepath.Join(exeDir, "donnees", "webview2")
		dlDir = filepath.Join(exeDir, "Téléchargements")
	} else {
		cfg, _ := os.UserConfigDir() // %APPDATA% : mêmes données que la version précédente
		app.dataDir = filepath.Join(cfg, "Telechargys", "moteur")
		cache, _ := os.UserCacheDir() // %LOCALAPPDATA%
		app.wvData = filepath.Join(cache, "Telechargys", "WebView2")
		if p, err := windows.KnownFolderPath(windows.FOLDERID_Downloads, 0); err == nil {
			dlDir = filepath.Join(p, "Telechargys")
		} else {
			home, _ := os.UserHomeDir()
			dlDir = filepath.Join(home, "Downloads", "Telechargys")
		}
	}

	// une seule instance : la seconde transmet ses liens à la première et s'arrête
	name, _ := windows.UTF16PtrFromString("Local\\QMTech.Telechargys." + shortHash(app.dataDir))
	mutex, err := windows.CreateMutex(nil, false, name)
	if err == windows.ERROR_ALREADY_EXISTS {
		forward(app.dataDir, urls)
		return
	}
	defer windows.CloseHandle(mutex)

	m, err := core.NewManager(app.dataDir, dlDir, "windows")
	if err != nil {
		messageBox("Telechargys", "Impossible de démarrer :\n"+err.Error(), mbIconError)
		return
	}
	web, _ := fs.Sub(ui.FS, "web")
	srv, err := core.Serve(m, web)
	if err != nil {
		messageBox("Telechargys", "Impossible de démarrer le serveur local :\n"+err.Error(), mbIconError)
		return
	}
	app.m, app.srv = m, srv
	app.base = fmt.Sprintf("http://127.0.0.1:%d", srv.Port)
	writeInstance(app.dataDir, srv.Port, m.Token)
	registerAUMID(app.dataDir)

	// WebView2 (composant Microsoft présent sur Windows 11 et sur la plupart des Windows 10)
	if v, err := webviewloader.GetInstalledVersion(); err != nil || v == "" {
		if messageBox("Telechargys", "Telechargys a besoin du composant Microsoft Edge WebView2, absent de cet ordinateur.\n\nOuvrir la page de téléchargement de Microsoft (gratuit, 2 minutes) ?", mbYesNo|mbIconWarning) == idYes {
			shellOpen("https://developer.microsoft.com/fr-fr/microsoft-edge/webview2/#download-section")
		}
		m.Shutdown()
		srv.Close()
		return
	}

	st := m.State()
	app.settings = st.Settings
	for _, d := range st.Downloads {
		app.lastStatus[d.ID] = d.Status
	}
	m.OnEvent = app.onEvent

	app.main = webview2.NewWithOptions(webview2.WebViewOptions{
		AutoFocus: true,
		DataPath:  app.wvData,
		WindowOptions: webview2.WindowOptions{
			Title: "Telechargys", Width: 1200, Height: 760, IconId: 1, Center: true,
		},
	})
	if app.main == nil {
		messageBox("Telechargys", "Impossible d'ouvrir la fenêtre (WebView2).", mbIconError)
		m.Shutdown()
		srv.Close()
		return
	}
	app.hwnd = uintptr(app.main.Window())
	if hidden {
		showWindow(app.hwnd, swHide)
	}
	app.main.SetSize(420, 480, webview2.HintMin)
	app.bindShell(app.main, "")
	subclassMain(app)
	app.main.Navigate(app.base + "/?token=" + m.Token)

	systray.Register(app.trayReady, nil) // même fil : la boucle de messages de la fenêtre sert aussi l'icône
	app.applySettings(app.settings)
	go app.pollTray()
	go func() {
		time.Sleep(1500 * time.Millisecond) // laisser l'interface se charger avant d'afficher les liens reçus
		for _, u := range urls {
			m.AddSimple(context.Background(), u, "", "", "")
		}
	}()

	app.main.Run() // jusqu'à « Quitter »

	app.mu.Lock()
	if app.clipStop != nil {
		close(app.clipStop)
	}
	for _, w := range app.prog {
		w.Destroy()
	}
	app.mu.Unlock()
	systray.Quit()
	m.Shutdown()
	srv.Close()
	os.Remove(filepath.Join(app.dataDir, "instance.json"))
}

// ---------- seconde instance ----------

type instance struct {
	Port  int    `json:"port"`
	Token string `json:"token"`
}

func writeInstance(dir string, port int, token string) {
	b, _ := json.Marshal(instance{port, token})
	os.WriteFile(filepath.Join(dir, "instance.json"), b, 0o600)
}

func forward(dir string, urls []string) {
	b, err := os.ReadFile(filepath.Join(dir, "instance.json"))
	if err != nil {
		return
	}
	var in instance
	if json.Unmarshal(b, &in) != nil {
		return
	}
	post := func(path string, body any) {
		data, _ := json.Marshal(body)
		req, _ := http.NewRequest("POST", fmt.Sprintf("http://127.0.0.1:%d/api/%s", in.Port, path), bytes.NewReader(data))
		req.Header.Set("X-Token", in.Token)
		c := &http.Client{Timeout: 5 * time.Second}
		if resp, err := c.Do(req); err == nil {
			resp.Body.Close()
		}
	}
	post("show", map[string]any{})
	for _, u := range urls {
		post("capture", map[string]any{"url": u})
	}
}

func shortHash(s string) string {
	var h uint32 = 2166136261
	for _, c := range strings.ToLower(s) {
		h = (h ^ uint32(c)) * 16777619
	}
	return fmt.Sprintf("%08x", h)
}

// ---------- évènements du moteur ----------

func (a *App) onEvent(ev core.Event) {
	switch ev.Type {
	case "show", "capture", "captureBatch", "pair", "refreshed", "updateAvailable":
		a.showMain()
	case "settings":
		if s, ok := ev.Data.(core.Settings); ok {
			a.applySettings(s)
		}
	case "download":
		if d, ok := ev.Data.(*core.Download); ok {
			a.onDownload(d)
		}
	case "removed":
		id, _ := ev.Data.(string)
		a.mu.Lock()
		if w := a.prog[id]; w != nil {
			w.Destroy()
		}
		delete(a.lastStatus, id)
		a.mu.Unlock()
	case "notify":
		d, _ := ev.Data.(map[string]any)
		a.mu.Lock()
		s := a.settings
		a.mu.Unlock()
		if d == nil || !s.NotifyDone || (d["kind"] == "done" && s.ShowDoneWin) {
			return
		}
		title, _ := d["title"].(string)
		body, _ := d["body"].(string)
		go toast(title, body)
	case "queueDone":
		d, _ := ev.Data.(map[string]any)
		if d != nil {
			act, _ := d["postAction"].(string)
			a.postAction(act)
		}
	}
}

func (a *App) onDownload(d *core.Download) {
	a.mu.Lock()
	prev, known := a.lastStatus[d.ID]
	a.lastStatus[d.ID] = d.Status
	pw := a.prog[d.ID]
	s := a.settings
	nProg := len(a.prog)
	a.mu.Unlock()
	if d.Status == core.StDownloading && known && prev != core.StDownloading && prev != core.StMerging && !d.ViaQueue && s.ShowProgressWin && pw == nil && nProg < 6 {
		a.openMini(d.ID, "progress")
	}
	if d.Status == core.StCompleted && known && prev != core.StCompleted {
		if pw != nil {
			pw.Destroy()
		}
		if s.ShowDoneWin && !d.ViaQueue {
			a.openMini(d.ID, "done")
		}
	}
}

// openMini ouvre une fenêtre de progression ou de fin, chacune sur son propre fil Windows.
func (a *App) openMini(id, view string) {
	go func() {
		runtime.LockOSThread()
		h := uint(500)
		if view == "done" {
			h = 340
		}
		w := webview2.NewWithOptions(webview2.WebViewOptions{
			DataPath: a.wvData,
			WindowOptions: webview2.WindowOptions{
				Title: "Telechargys", Width: 520, Height: h, IconId: 1, Center: true,
			},
		})
		if w == nil {
			return
		}
		if view == "done" {
			w.SetSize(520, 340, webview2.HintFixed)
		}
		a.bindShell(w, view)
		w.Navigate(fmt.Sprintf("%s/progress.html?view=%s&id=%s&token=%s", a.base, view, id, a.m.Token))
		a.mu.Lock()
		if view == "progress" {
			a.prog[id] = w
		}
		a.mu.Unlock()
		w.Run()
		a.mu.Lock()
		if a.prog[id] == w {
			delete(a.prog, id)
		}
		a.mu.Unlock()
	}()
}

// ---------- réglages ----------

func (a *App) applySettings(s core.Settings) {
	a.mu.Lock()
	a.settings = s
	if a.clipStop != nil {
		close(a.clipStop)
		a.clipStop = nil
	}
	if s.ClipboardWatch {
		a.clipStop = make(chan struct{})
		go a.watchClipboard(a.clipStop)
	}
	portable := a.portable
	a.mu.Unlock()
	if !portable {
		setStartup(s.StartWithSystem)
	}
}

func (a *App) watchClipboard(stop chan struct{}) {
	t := time.NewTicker(1200 * time.Millisecond)
	defer t.Stop()
	a.mu.Lock()
	a.lastClip = readClipboard()
	a.mu.Unlock()
	for {
		select {
		case <-stop:
			return
		case <-t.C:
		}
		txt := strings.TrimSpace(readClipboard())
		a.mu.Lock()
		same := txt == a.lastClip
		a.lastClip = txt
		exts := a.settings.CaptureExts
		a.mu.Unlock()
		if same || len(txt) > 2000 || strings.ContainsAny(txt, " \n\t") {
			continue
		}
		l := strings.ToLower(txt)
		if !strings.HasPrefix(l, "http://") && !strings.HasPrefix(l, "https://") && !strings.HasPrefix(l, "ftp://") {
			continue
		}
		e := strings.ToLower(strings.TrimPrefix(filepath.Ext(strings.SplitN(strings.SplitN(txt, "?", 2)[0], "#", 2)[0]), "."))
		for _, x := range exts {
			if x == e {
				a.m.AddSimple(context.Background(), txt, "", "", "")
				break
			}
		}
	}
}

// ---------- fin de file : quitter, veille, extinction ----------

func (a *App) postAction(act string) {
	if act == "" {
		return
	}
	if act == "exit" {
		a.quit()
		return
	}
	labels := map[string]string{"shutdown": "éteindre l'ordinateur", "sleep": "mettre l'ordinateur en veille", "hibernate": "mettre l'ordinateur en veille prolongée"}
	lbl, ok := labels[act]
	if !ok {
		return
	}
	cancel := make(chan struct{})
	a.mu.Lock()
	if a.postCancel != nil {
		close(a.postCancel)
	}
	a.postCancel = cancel
	a.mu.Unlock()
	a.showMain()
	a.main.Dispatch(func() {
		a.main.Eval(fmt.Sprintf("window.tyCountdown && tyCountdown(%q, 30)", "La file est terminée : Telechargys va "+lbl))
	})
	go func() {
		select {
		case <-cancel:
			return
		case <-time.After(30 * time.Second):
		}
		a.m.Flush()
		switch act {
		case "shutdown":
			run("shutdown", "/s", "/t", "5")
		case "hibernate":
			run("shutdown", "/h")
		case "sleep":
			run("rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0")
		}
	}()
}

func (a *App) cancelPost() {
	a.mu.Lock()
	if a.postCancel != nil {
		close(a.postCancel)
		a.postCancel = nil
	}
	a.mu.Unlock()
}

// ---------- zone de notification ----------

func (a *App) trayReady() {
	systray.SetIcon(trayIcon)
	systray.SetTooltip("Telechargys")
	open := systray.AddMenuItem("Ouvrir Telechargys", "")
	add := systray.AddMenuItem("Nouveau téléchargement…", "")
	systray.AddSeparator()
	startAll := systray.AddMenuItem("Tout démarrer", "")
	pauseAll := systray.AddMenuItem("Tout arrêter", "")
	systray.AddSeparator()
	folder := systray.AddMenuItem("Ouvrir le dossier des téléchargements", "")
	systray.AddSeparator()
	quit := systray.AddMenuItem("Quitter", "")
	systray.SetOnTapped(a.showMain)
	go func() {
		for {
			select {
			case <-open.ClickedCh:
				a.showMain()
			case <-add.ClickedCh:
				a.showMain()
				a.main.Dispatch(func() { a.main.Eval("window.openAdd && openAdd()") })
			case <-startAll.ClickedCh:
				go a.m.StartAll()
			case <-pauseAll.ClickedCh:
				go a.m.PauseAll()
			case <-folder.ClickedCh:
				a.mu.Lock()
				dir := a.settings.DownloadDir
				a.mu.Unlock()
				os.MkdirAll(dir, 0o755)
				shellOpen(dir)
			case <-quit.ClickedCh:
				a.quit()
				return
			}
		}
	}()
}

func (a *App) pollTray() {
	for {
		time.Sleep(1500 * time.Millisecond)
		a.mu.Lock()
		q := a.quitting
		a.mu.Unlock()
		if q {
			return
		}
		s := a.m.Summary()
		if s.Active > 0 {
			tip := fmt.Sprintf("Telechargys : %d en cours, %s", s.Active, fmtSpeed(s.Speed))
			if s.Percent >= 0 {
				tip += fmt.Sprintf(" (%d %%)", s.Percent)
			}
			systray.SetTooltip(tip)
		} else {
			systray.SetTooltip("Telechargys")
		}
	}
}

func fmtSpeed(n int64) string {
	v := float64(n)
	u := []string{"o", "Ko", "Mo", "Go"}
	i := 0
	for v >= 1024 && i < 3 {
		v /= 1024
		i++
	}
	if i == 0 {
		return fmt.Sprintf("%d o/s", n)
	}
	return strings.Replace(fmt.Sprintf("%.1f %s/s", v, u[i]), ".", ",", 1)
}

// ---------- fenêtre principale ----------

func (a *App) showMain() {
	if a.main == nil {
		return
	}
	a.main.Dispatch(func() { bringToFront(a.hwnd) })
}

func (a *App) quit() {
	a.mu.Lock()
	if a.quitting {
		a.mu.Unlock()
		return
	}
	a.quitting = true
	a.mu.Unlock()
	a.main.Dispatch(func() { a.main.Destroy() })
}

// closeRequested : croix de la fenêtre principale.
func (a *App) closeRequested() bool {
	a.mu.Lock()
	q, tray := a.quitting, a.settings.MinimizeToTray
	a.mu.Unlock()
	if q {
		return false // laisser la fenêtre se fermer
	}
	if tray {
		showWindow(a.hwnd, swHide)
		return true
	}
	a.quit()
	return true
}
