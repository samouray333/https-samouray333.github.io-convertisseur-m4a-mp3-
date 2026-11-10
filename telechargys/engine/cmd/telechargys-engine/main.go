// Moteur Telechargys (ordinateur) : lancé par l'application, il sert l'API locale et l'interface.
package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"

	"telechargys/engine/core"
	"telechargys/engine/ui"
)

func main() {
	home, _ := os.UserHomeDir()
	cfg, _ := os.UserConfigDir()
	data := flag.String("data", filepath.Join(cfg, "Telechargys"), "dossier des données")
	dl := flag.String("downloads", filepath.Join(home, "Downloads", "Telechargys"), "dossier de téléchargement par défaut")
	flag.Parse()
	m, err := core.NewManager(*data, *dl, runtime.GOOS)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	web, _ := fs.Sub(ui.FS, "web")
	s, err := core.Serve(m, web)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{"port": s.Port, "token": m.Token})
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt)
	go func() { // l'application ferme l'entrée standard (ou écrit « quit ») pour arrêter proprement
		sc := bufio.NewScanner(os.Stdin)
		for sc.Scan() {
			if sc.Text() == "quit" {
				break
			}
		}
		sig <- os.Interrupt
	}()
	<-sig
	m.Shutdown()
	s.Close()
}
