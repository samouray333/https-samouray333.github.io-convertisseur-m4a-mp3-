//go:build windows

package main

import (
	"encoding/base64"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unicode/utf16"
	"unsafe"

	"github.com/atotto/clipboard"
	"github.com/jchv/go-webview2"
	"github.com/sqweek/dialog"
	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"

	"telechargys/engine/core"
)

var (
	user32           = windows.NewLazySystemDLL("user32.dll")
	shell32          = windows.NewLazySystemDLL("shell32.dll")
	pMessageBoxW     = user32.NewProc("MessageBoxW")
	pShowWindow      = user32.NewProc("ShowWindow")
	pSetForeground   = user32.NewProc("SetForegroundWindow")
	pIsIconic        = user32.NewProc("IsIconic")
	pSetWindowLongW  = user32.NewProc("SetWindowLongPtrW")
	pCallWindowProcW = user32.NewProc("CallWindowProcW")
	pShellExecuteW   = shell32.NewProc("ShellExecuteW")
)

const (
	mbIconError   = 0x10
	mbIconWarning = 0x30
	mbYesNo       = 0x04
	idYes         = 6
	swHide        = 0
	swShow        = 5
	swRestore     = 9
	wmClose       = 0x0010
	createNoWin   = 0x08000000
)

func utf16p(s string) uintptr {
	p, _ := windows.UTF16PtrFromString(s)
	return uintptr(unsafe.Pointer(p))
}

func messageBox(title, text string, flags uintptr) int {
	r, _, _ := pMessageBoxW.Call(0, utf16p(text), utf16p(title), flags|0x00010000 /* MB_SETFOREGROUND */)
	return int(r)
}

func showWindow(hwnd uintptr, cmd uintptr) { pShowWindow.Call(hwnd, cmd) }

func bringToFront(hwnd uintptr) {
	if r, _, _ := pIsIconic.Call(hwnd); r != 0 {
		pShowWindow.Call(hwnd, swRestore)
	} else {
		pShowWindow.Call(hwnd, swShow)
	}
	pSetForeground.Call(hwnd)
}

func shellOpen(target string) bool {
	r, _, _ := pShellExecuteW.Call(0, utf16p("open"), utf16p(target), 0, 0, swShow)
	return r > 32
}

func run(name string, args ...string) {
	c := exec.Command(name, args...)
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWin}
	c.Start()
}

// ---------- croix de la fenêtre principale : masquer dans la zone de notification ----------

var (
	mainApp  *App
	origProc uintptr
)

func mainProc(hwnd, msg, wp, lp uintptr) uintptr {
	if msg == wmClose && mainApp != nil && mainApp.closeRequested() {
		return 0
	}
	r, _, _ := pCallWindowProcW.Call(origProc, hwnd, msg, wp, lp)
	return r
}

func subclassMain(a *App) {
	mainApp = a
	gwlpWndProc := -4
	origProc, _, _ = pSetWindowLongW.Call(a.hwnd, uintptr(gwlpWndProc), windows.NewCallback(mainProc))
}

// ---------- fonctions offertes à l'interface (window.tyShell) ----------

func (a *App) bindShell(w webview2.WebView, view string) {
	w.Bind("tyOpenFile", func(p string) {
		if _, err := os.Stat(p); err != nil {
			messageBox("Telechargys", "Fichier introuvable (déplacé ou supprimé) :\n"+p, mbIconWarning)
			return
		}
		if !shellOpen(p) {
			messageBox("Telechargys", "Aucune application pour ouvrir ce fichier :\n"+p, mbIconWarning)
		}
	})
	w.Bind("tyShowInFolder", func(p string) {
		if _, err := os.Stat(p); err != nil {
			shellOpen(filepath.Dir(p))
			return
		}
		c := exec.Command("explorer.exe")
		c.SysProcAttr = &syscall.SysProcAttr{CmdLine: `explorer.exe /select,"` + p + `"`}
		c.Start()
	})
	w.Bind("tyChooseFolder", func(cur string) string {
		b := dialog.Directory().Title("Choisir un dossier")
		if cur != "" {
			b = b.SetStartDir(cur)
		}
		p, err := b.Browse()
		if err != nil {
			return ""
		}
		return p
	})
	w.Bind("tyReadClipboard", func() string { return readClipboard() })
	w.Bind("tyCopy", func(t string) {
		clipboard.WriteAll(t)
		a.mu.Lock()
		a.lastClip = strings.TrimSpace(t)
		a.mu.Unlock()
	})
	w.Bind("tyApplySettings", func(s core.Settings) { a.applySettings(s) })
	w.Bind("tyCancelPost", func() { a.cancelPost() })
	w.Bind("tyOpenExtension", func() {
		exe, _ := os.Executable()
		dir := filepath.Join(filepath.Dir(exe), "extension")
		if _, err := os.Stat(dir); err != nil {
			messageBox("Telechargys", "Le dossier de l'extension est introuvable à côté du programme.", mbIconWarning)
			return
		}
		shellOpen(dir)
	})
	w.Bind("tyInstallUpdate", func(p string) string { return a.installUpdate(p) })
	w.Bind("tyCloseWindow", func() { w.Destroy() })
	w.Bind("tyResize", func(big bool) {
		if big {
			w.SetSize(520, 500, webview2.HintNone)
		} else {
			w.SetSize(520, 360, webview2.HintNone)
		}
	})
	w.Init(`window.tyShell = {
  native: true,
  openFile: p => tyOpenFile(p), showInFolder: p => tyShowInFolder(p), chooseFolder: c => tyChooseFolder(c || ''),
  readClipboard: () => tyReadClipboard(), copy: t => tyCopy(String(t)), applySettings: s => tyApplySettings(s),
  cancelPost: () => tyCancelPost(), openExtension: () => tyOpenExtension(), installUpdate: p => tyInstallUpdate(p),
  closeWindow: () => tyCloseWindow(), resizeProgress: b => tyResize(!!b)
};`)
}

func readClipboard() string {
	t, err := clipboard.ReadAll()
	if err != nil {
		return ""
	}
	return t
}

// installUpdate lance l'installeur téléchargé en mode silencieux ; il relance Telechargys une fois installé.
func (a *App) installUpdate(path string) string {
	if a.portable {
		return "Version portable : télécharge la nouvelle version portable et remplace l'ancienne."
	}
	if !strings.HasSuffix(strings.ToLower(path), ".exe") {
		return "fichier de mise à jour inattendu"
	}
	c := exec.Command(path, "/S", "/RELANCER")
	if err := c.Start(); err != nil {
		return "impossible de lancer l'installeur : " + err.Error()
	}
	a.m.Flush()
	go a.quit()
	return ""
}

// ---------- démarrage avec Windows ----------

func setStartup(on bool) {
	k, err := registry.OpenKey(registry.CURRENT_USER, `Software\Microsoft\Windows\CurrentVersion\Run`, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		return
	}
	defer k.Close()
	if on {
		exe, _ := os.Executable()
		k.SetStringValue("Telechargys", `"`+exe+`" --hidden`)
	} else {
		k.DeleteValue("Telechargys")
	}
}

// ---------- notifications Windows ----------

// registerAUMID : identité de l'appli pour que les notifications affichent « Telechargys » et son icône.
func registerAUMID(dataDir string) {
	icon := filepath.Join(dataDir, "icone.png")
	if _, err := os.Stat(icon); err != nil {
		os.WriteFile(icon, appPNG, 0o644)
	}
	k, _, err := registry.CreateKey(registry.CURRENT_USER, `Software\Classes\AppUserModelId\`+aumid, registry.SET_VALUE)
	if err != nil {
		return
	}
	defer k.Close()
	k.SetStringValue("DisplayName", "Telechargys")
	k.SetStringValue("IconUri", icon)
}

func xmlEsc(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&apos;").Replace(s)
}

func toast(title, body string) {
	xml := `<toast><visual><binding template="ToastGeneric"><text>` + xmlEsc(title) + `</text><text>` + xmlEsc(body) + `</text></binding></visual></toast>`
	script := `[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('` + strings.ReplaceAll(xml, "'", "''") + `')
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('` + aumid + `').Show([Windows.UI.Notifications.ToastNotification]::new($x))`
	u := utf16.Encode([]rune(script))
	b := make([]byte, len(u)*2)
	for i, v := range u {
		b[2*i], b[2*i+1] = byte(v), byte(v>>8)
	}
	run("powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", base64.StdEncoding.EncodeToString(b))
}
