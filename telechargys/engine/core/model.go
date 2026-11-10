// Package core : moteur de téléchargement de Telechargys (commun Windows / Android).
package core

import (
	"sync"
	"sync/atomic"
	"time"
)

const Version = "1.0.0"

// États d'un téléchargement.
const (
	StQueued      = "queued"      // en attente dans sa file
	StDownloading = "downloading" // en cours
	StPaused      = "paused"      // en pause (reprise possible si le serveur le permet)
	StCompleted   = "completed"   // terminé
	StError       = "error"       // en erreur
	StMerging     = "merging"     // assemblage / conversion finale
)

// Segment : plage d'octets [Start, End] d'un fichier ; Pos = prochain octet à écrire.
type Segment struct {
	Start int64 `json:"start"`
	End   int64 `json:"end"`
	Pos   int64 `json:"pos"`

	active int32 // 1 si une connexion travaille dessus (non persisté)
}

func (s *Segment) pos() int64     { return atomic.LoadInt64(&s.Pos) }
func (s *Segment) end() int64     { return atomic.LoadInt64(&s.End) }
func (s *Segment) remain() int64  { return s.end() - s.pos() + 1 }
func (s *Segment) done() bool     { return s.pos() > s.end() }
func (s *Segment) isActive() bool { return atomic.LoadInt32(&s.active) == 1 }

// HLSState : état d'un téléchargement de flux HLS (m3u8).
type HLSState struct {
	MediaURL  string `json:"mediaUrl"`            // playlist média choisie
	AudioURL  string `json:"audioUrl,omitempty"`  // playlist audio séparée éventuelle
	Quality   string `json:"quality,omitempty"`   // libellé de la qualité
	Total     int    `json:"total"`               // nombre total de segments
	Done      int    `json:"done"`                // segments terminés
	DoneBits  []byte `json:"doneBits,omitempty"`  // bitmap des segments terminés
	Container string `json:"container,omitempty"` // ts ou mp4
}

// Checksum : contrôle d'intégrité.
type Checksum struct {
	Algo     string `json:"algo,omitempty"` // md5, sha1, sha256
	Expected string `json:"expected,omitempty"`
	Actual   string `json:"actual,omitempty"`
	OK       *bool  `json:"ok,omitempty"`
}

// Download : un téléchargement et tous ses réglages.
type Download struct {
	ID          string            `json:"id"`
	URL         string            `json:"url"`
	FinalURL    string            `json:"finalUrl,omitempty"`
	Kind        string            `json:"kind"` // http, hls, ftp
	FileName    string            `json:"fileName"`
	Dir         string            `json:"dir"`
	Category    string            `json:"category"`
	Queue       string            `json:"queue"`
	Status      string            `json:"status"`
	Size        int64             `json:"size"` // -1 si inconnue
	Downloaded  int64             `json:"downloaded"`
	Speed       int64             `json:"speed"`
	Resumable   bool              `json:"resumable"`
	Probed      bool              `json:"probed"`
	Segments    []*Segment        `json:"segments,omitempty"`
	MaxConn     int               `json:"maxConn"`    // 0 = réglage global
	SpeedLimit  int64             `json:"speedLimit"` // octets/s, 0 = illimité
	Headers     map[string]string `json:"headers,omitempty"`
	Referer     string            `json:"referer,omitempty"`
	UserAgent   string            `json:"userAgent,omitempty"`
	Cookies     string            `json:"cookies,omitempty"`
	Username    string            `json:"username,omitempty"`
	Password    string            `json:"password,omitempty"`
	Checksum    Checksum          `json:"checksum"`
	Description string            `json:"description,omitempty"`
	Error       string            `json:"error,omitempty"`
	ETag        string            `json:"etag,omitempty"`
	LastMod     string            `json:"lastMod,omitempty"`
	MimeType    string            `json:"mimeType,omitempty"`
	AddedAt     int64             `json:"addedAt"`
	CompletedAt int64             `json:"completedAt,omitempty"`
	ElapsedMs   int64             `json:"elapsedMs"`
	Conns       int               `json:"conns"` // connexions actives
	HLS         *HLSState         `json:"hls,omitempty"`
	Order       int64             `json:"order"`
	NameLocked  bool              `json:"nameLocked,omitempty"`
	CatAuto     bool              `json:"catAuto,omitempty"`

	// exécution (non persisté)
	cancel    func()
	doneCh    chan struct{}
	dlCount   atomic.Int64 // octets reçus
	lastDl    int64
	startedAt time.Time
	limiter   *Limiter
	mu        sync.Mutex // protège Segments pendant l'exécution
}

// Category : catégorie de fichiers et son dossier.
type Category struct {
	ID   string   `json:"id"`
	Name string   `json:"name"`
	Dir  string   `json:"dir"` // sous-dossier (relatif au dossier de base) ou chemin absolu
	Exts []string `json:"exts"`
}

// Schedule : planification d'une file.
type Schedule struct {
	Enabled   bool   `json:"enabled"`
	Start     string `json:"start"`          // HH:MM
	Stop      string `json:"stop,omitempty"` // HH:MM, vide = pas d'arrêt automatique
	Days      []int  `json:"days"`           // 0 = dimanche ... 6 = samedi ; vide = tous les jours
	lastStart string
	lastStop  string
}

// Queue : file d'attente.
type Queue struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	MaxActive  int      `json:"maxActive"`
	Running    bool     `json:"running"`
	Schedule   Schedule `json:"schedule"`
	PostAction string   `json:"postAction"` // "", exit, shutdown, sleep, hibernate
}

// SiteLogin : identifiants enregistrés pour un site.
type SiteLogin struct {
	Host     string `json:"host"`
	Username string `json:"username"`
	Password string `json:"password"`
}

// Settings : réglages généraux.
type Settings struct {
	DownloadDir     string      `json:"downloadDir"`
	MaxConn         int         `json:"maxConn"`    // connexions par fichier (1 à 32)
	SpeedLimit      int64       `json:"speedLimit"` // limite globale en octets/s
	SpeedLimitOn    bool        `json:"speedLimitOn"`
	Retries         int         `json:"retries"`
	RetryWaitSec    int         `json:"retryWaitSec"`
	TimeoutSec      int         `json:"timeoutSec"`
	UserAgent       string      `json:"userAgent"`
	Proxy           string      `json:"proxy"` // http://hote:port ou socks5://hote:port
	AutoResume      bool        `json:"autoResume"`
	ShowAddDialog   bool        `json:"showAddDialog"`
	ClipboardWatch  bool        `json:"clipboardWatch"`
	CaptureExts     []string    `json:"captureExts"`
	CaptureMinKB    int         `json:"captureMinKB"`
	NotifyDone      bool        `json:"notifyDone"`
	SoundDone       bool        `json:"soundDone"`
	Theme           string      `json:"theme"` // auto, light, dark
	OnDuplicate     string      `json:"onDuplicate"`
	AntivirusCmd    string      `json:"antivirusCmd"` // commande lancée sur chaque fichier terminé (ordinateur)
	HLSToMP4        bool        `json:"hlsToMp4"`
	HLSConn         int         `json:"hlsConn"`
	WifiOnly        bool        `json:"wifiOnly"` // Android
	StartWithSystem bool        `json:"startWithSystem"`
	MinimizeToTray  bool        `json:"minimizeToTray"`
	Logins          []SiteLogin `json:"logins"`
}

const defaultUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

func defaultSettings(dir string) Settings {
	return Settings{
		DownloadDir: dir, MaxConn: 8, Retries: 10, RetryWaitSec: 3, TimeoutSec: 30,
		UserAgent: defaultUA, AutoResume: false, ShowAddDialog: true, ClipboardWatch: true,
		CaptureExts: []string{"zip", "rar", "7z", "gz", "bz2", "xz", "tar", "iso", "img", "exe", "msi", "apk", "dmg", "deb", "rpm",
			"mp3", "m4a", "flac", "wav", "ogg", "opus", "aac", "mp4", "mkv", "avi", "mov", "webm", "wmv", "flv", "m4v", "mpg", "mpeg", "ts", "m3u8",
			"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "epub", "bin", "torrent"},
		CaptureMinKB: 0, NotifyDone: true, SoundDone: true, Theme: "auto", OnDuplicate: "rename",
		HLSToMP4: true, HLSConn: 6, MinimizeToTray: true,
	}
}

func defaultCategories() []Category {
	return []Category{
		{ID: "video", Name: "Vidéos", Dir: "Vidéos", Exts: []string{"mp4", "mkv", "avi", "mov", "webm", "wmv", "flv", "m4v", "mpg", "mpeg", "3gp", "ts", "m3u8"}},
		{ID: "music", Name: "Musique", Dir: "Musique", Exts: []string{"mp3", "m4a", "flac", "wav", "ogg", "opus", "aac", "wma", "aiff"}},
		{ID: "archive", Name: "Archives", Dir: "Archives", Exts: []string{"zip", "rar", "7z", "gz", "bz2", "xz", "tar", "tgz", "iso", "img", "cab"}},
		{ID: "program", Name: "Programmes", Dir: "Programmes", Exts: []string{"exe", "msi", "apk", "dmg", "deb", "rpm", "appimage", "bat", "jar", "xapk"}},
		{ID: "document", Name: "Documents", Dir: "Documents", Exts: []string{"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "txt", "epub", "csv", "rtf"}},
		{ID: "image", Name: "Images", Dir: "Images", Exts: []string{"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "tif", "tiff", "heic"}},
		{ID: "other", Name: "Autres", Dir: "", Exts: nil},
	}
}

func defaultQueues() []*Queue {
	return []*Queue{{ID: "main", Name: "File principale", MaxActive: 3}}
}
