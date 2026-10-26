"""Page d'accueil : dépôt d'une vidéo, projets récents, état des moteurs."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox, QToolButton, QVBoxLayout

from ...config import settings
from ...core import engines
from ...core import project as project_io
from ...core.textproc import format_duration
from .. import icons, theme
from ..widgets import Badge, Card, DropZone, button, card_title, label
from .base import Page

REQUIRED = ["analysis", "whisper", "kokoro", "chatterbox"]  # chaîne complète hors ligne (mode par défaut)


class HeroBanner(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(250)

    def paintEvent(self, e):
        p = theme.CURRENT
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        c1, c2 = QColor(p.accent), QColor(p.accent2)
        grad.setColorAt(0, c1.darker(150) if p.dark else c1.lighter(105))
        grad.setColorAt(0.55, c1 if p.dark else c1.lighter(115))
        grad.setColorAt(1, c2)
        painter.fillPath(path, grad)
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        n = 42
        w = self.width() * 0.42
        x0 = self.width() - w - 30
        for i in range(n):
            h = (math.sin(i * 0.45) * 0.5 + 0.5) * (0.35 + 0.65 * abs(math.sin(i * 0.17 + 1)))
            bh = 18 + h * self.height() * 0.6
            x = x0 + i * (w / n)
            painter.drawRoundedRect(QRectF(x, (self.height() - bh) / 2, w / n * 0.55, bh), 3, 3)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawEllipse(QRectF(self.width() - 220, -120, 360, 360))
        painter.end()


def project_summary(path: Path) -> tuple[str, str, Path | None]:
    """(titre, infos, vignette) d'un projet sans le charger entièrement dans l'interface."""
    title, info = path.stem, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        title = data.get("title") or title
        lines = data.get("lines", [])
        people = data.get("people", [])
        dur = float(data.get("video", {}).get("duration", 0) or 0)
        steps = data.get("steps", {})
        if data.get("settings", {}).get("subtitles_only"):
            state = "sous-titres prêts" if steps.get("translate", {}).get("done") else (
                "en cours" if steps else "à sous-titrer")
        else:
            state = "VF prête" if steps.get("mix", {}).get("done") else ("en cours" if steps else "à doubler")
        info = f"{format_duration(dur)} · {len(lines)} répliques · {len(people)} personne(s) · {state}"
    except Exception:
        pass
    t = path.parent / "travail" / "vignette.jpg"
    return title, info, t if t.exists() else None


class RecentCard(QFrame):
    def __init__(self, path: str, on_open, on_forget, on_delete, on_reveal):
        super().__init__()
        self.setObjectName("CardHover")
        self.setCursor(Qt.PointingHandCursor)
        self._path = path
        self._on_open = on_open
        self.menu = QMenu(self)
        self.menu.addAction(icons.icon("film", theme.CURRENT.text, 16), "Ouvrir", lambda: on_open(path))
        self.menu.addAction(icons.icon("folder", theme.CURRENT.text, 16), "Afficher dans l'explorateur",
                            lambda: on_reveal(path))
        self.menu.addSeparator()
        self.menu.addAction(icons.icon("x", theme.CURRENT.text, 16), "Retirer de la liste", lambda: on_forget(path))
        self.menu.addAction(icons.icon("trash", theme.CURRENT.danger, 16), "Supprimer le projet…",
                            lambda: on_delete(path))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        p = Path(path)
        title, info, thumb = project_summary(p)
        pic = QLabel()
        pic.setFixedSize(128, 72)
        pic.setAlignment(Qt.AlignCenter)
        pic.setStyleSheet(f"background: {theme.CURRENT.surface3}; border-radius: 8px;")
        if thumb is not None:
            pm = QPixmap(str(thumb))
            if not pm.isNull():
                pic.setPixmap(pm.scaled(128, 72, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        else:
            pic.setPixmap(icons.pixmap("film", theme.CURRENT.faint, 28))
        lay.addWidget(pic)
        col = QVBoxLayout()
        col.setSpacing(4)
        top = QHBoxLayout()
        t = label(title, wrap=True)
        t.setStyleSheet("font-weight: 700; font-size: 11pt;")
        top.addWidget(t, 1)
        more = QToolButton()
        more.setIcon(icons.icon("more", theme.CURRENT.text, 18))
        more.setToolTip("Retirer de la liste, supprimer…")
        more.setAutoRaise(True)
        more.setPopupMode(QToolButton.InstantPopup)
        more.setMenu(self.menu)
        top.addWidget(more, 0, Qt.AlignTop)
        col.addLayout(top)
        col.addWidget(label(info, "Hint", wrap=True))
        try:
            col.addWidget(label(time.strftime("Modifié le %d/%m/%Y", time.localtime(p.stat().st_mtime)), "Faint"))
        except OSError:
            pass
        col.addStretch(1)
        lay.addLayout(col, 1)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_open(self._path)

    def contextMenuEvent(self, e):
        self.menu.exec(e.globalPos())


class HomePage(Page):
    name = "home"

    def __init__(self, ctx, window):
        super().__init__(ctx, "", "", scroll=True)
        self.window_ = window
        self.header.hide()

        hero = HeroBanner()
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(36, 30, 30, 30)
        hl.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(10)
        kicker = label("DOUBLAGE VIDÉO EN FRANÇAIS · ANGLAIS, JAPONAIS, ESPAGNOL… · 100 % LOCAL")
        kicker.setStyleSheet("color: rgba(255,255,255,0.82); font-weight: 700; letter-spacing: 2px; font-size: 8.5pt;")
        title = label("Votre vidéo, en version française.")
        title.setStyleSheet("color: white; font-size: 25pt; font-weight: 800;")
        sub = label("Glissez une vidéo (anglais, japonais, espagnol, allemand…) : Doublys isole les voix, reconnaît qui parle, traduit, donne à "
                    "chaque personne une voix française proche de la sienne et la cale sur le temps d'origine.",
                    wrap=True)
        sub.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 11pt;")
        sub.setMinimumWidth(420)
        left.addWidget(kicker)
        left.addWidget(title)
        left.addWidget(sub)
        left.addSpacing(6)
        row = QHBoxLayout()
        b1 = button("Choisir une vidéo", "film")
        b1.setStyleSheet("QPushButton { background: white; color: #1B1416; border: none; padding: 10px 20px; }"
                         "QPushButton:hover { background: #FFF0EC; }")
        b1.setIcon(icons.icon("film", "#1B1416", 18))
        b1.clicked.connect(window.choose_video)
        b2 = button("Ouvrir un projet", "folder", icon_color="#FFFFFF")
        b2.setStyleSheet("QPushButton { background: rgba(255,255,255,0.16); color: white; border: 1px solid "
                         "rgba(255,255,255,0.35); padding: 10px 18px; } QPushButton:hover { background: "
                         "rgba(255,255,255,0.26); }")
        b2.clicked.connect(window.open_project_dialog)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        left.addLayout(row)
        left.addStretch(1)
        hl.addLayout(left, 3)
        drop = DropZone("Glissez une vidéo ici", "MP4, MKV, MOV, AVI, WEBM… (la vidéo reste à sa place). Plusieurs "
                        "vidéos : file d'attente.", "upload", 180)
        drop.setStyleSheet("#DropZone { background: rgba(255,255,255,0.12); border: 2px dashed "
                           "rgba(255,255,255,0.55); border-radius: 18px; }")
        drop.files_dropped.connect(window.open_files)
        drop.clicked.connect(window.choose_video)
        hl.addWidget(drop, 2)
        self.body.addWidget(hero)

        # moteurs
        eng = Card()
        top = QHBoxLayout()
        top.addWidget(card_title("Moteurs IA", "Installés une fois sur cet ordinateur (gratuits, hors ligne). "
                                 "Environ 6 Go et 20 à 40 minutes selon la connexion.", "cpu"), 1)
        self.install_btn = button("Installer tout ce qu'il faut", "download", "primary")
        self.install_btn.clicked.connect(self.install_required)
        top.addWidget(self.install_btn, 0, Qt.AlignTop)
        eng.add(top)
        self.engines_row = QHBoxLayout()
        self.engines_row.setSpacing(12)
        eng.add(self.engines_row)
        self.body.addWidget(eng)

        self.recent_title = QFrame()
        rt = QHBoxLayout(self.recent_title)
        rt.setContentsMargins(0, 0, 0, 0)
        rt.addWidget(label("Projets récents", "SectionTitle"))
        rt.addStretch(1)
        clear = button("Vider la liste", "x", "ghost",
                       tooltip="Retire tous les projets de cette liste (les fichiers ne sont pas supprimés)")
        clear.clicked.connect(self.clear_recent)
        rt.addWidget(clear)
        self.body.addWidget(self.recent_title)
        self.recent_grid = QGridLayout()
        self.recent_grid.setSpacing(14)
        self.body.addLayout(self.recent_grid)

        steps = Card(obj="CardFlat")
        steps.add(card_title("Comment ça marche", "", "sparkles"))
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        for i, (t, d) in enumerate([
            ("Séparer", "La musique et les bruits sont gardés, les voix isolées (Demucs)."),
            ("Comprendre", "Whisper écrit chaque mot ; les répliques et les personnes sont repérées."),
            ("Traduire", "Opus-MT hors ligne, ou DeepSeek qui adapte la longueur au temps disponible."),
            ("Doubler", "Une voix française par personne, clonée sur la sienne, calée sur l'image."),
        ]):
            c = QVBoxLayout()
            num = QLabel(str(i + 1))
            num.setFixedSize(28, 28)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(f"background: {theme.rgba(theme.CURRENT.accent, 0.18)}; color: {theme.CURRENT.accent};"
                              "border-radius: 14px; font-weight: 800;")
            c.addWidget(num)
            tl = label(t)
            tl.setStyleSheet("font-weight: 700;")
            c.addWidget(tl)
            c.addWidget(label(d, "Hint", wrap=True))
            c.addStretch(1)
            g.addLayout(c, 0, i)
            g.setColumnStretch(i, 1)
        steps.add(g)
        self.body.addWidget(steps)
        self.body.addStretch(1)
        self.ctx.engines_changed.connect(self._fill_engines)

    def on_show(self) -> None:
        self._fill_recent()
        self._fill_engines()

    def install_required(self) -> None:
        self.ctx.navigate("engines")
        page = self.window_.pages.get("engines")
        if page is not None:
            page.install_many(REQUIRED)

    def _fill_recent(self) -> None:
        while self.recent_grid.count():
            it = self.recent_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        recents = settings().recent_projects()[:6]
        self.recent_title.setVisible(bool(recents))
        for i, r in enumerate(recents):
            self.recent_grid.addWidget(RecentCard(r, self.window_.open_project, self.forget_recent,
                                                  self.delete_project, self._reveal), i // 2, i % 2)

    def _reveal(self, path: str) -> None:
        from ..main_window import open_path

        open_path(Path(path).parent)

    def forget_recent(self, path: str) -> None:
        settings().remove_recent(path)
        self._fill_recent()
        self.ctx.toast("Projet retiré de la liste (le fichier est conservé).", "info", 2500)

    def clear_recent(self) -> None:
        settings().clear_recent()
        self._fill_recent()

    def delete_project(self, path: str, confirm: bool = True) -> bool:
        p = Path(path)
        current = self.ctx.project.path if self.ctx.project is not None else None
        if current is not None and Path(current).resolve() == p.resolve():
            QMessageBox.information(self, "Projet ouvert", "Ce projet est ouvert : ouvrez-en un autre avant de le "
                                    "supprimer.")
            return False
        if confirm:
            r = QMessageBox.warning(
                self, "Supprimer le projet",
                f"Supprimer définitivement le projet « {p.stem} » ?\n\nSeront supprimés : le fichier du projet et son "
                f"dossier de travail (sons extraits, voix françaises).\nLa vidéo d'origine et les vidéos exportées "
                f"sont conservées.\n\nDossier : {p.parent}",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if r != QMessageBox.Yes:
                return False
        try:
            project_io.delete_project_files(p)
        except OSError as exc:
            QMessageBox.warning(self, "Suppression impossible", str(exc))
            return False
        settings().remove_recent(path)
        self._fill_recent()
        self.ctx.toast(f"Projet « {p.stem} » supprimé.", "success", 3000)
        return True

    def _fill_engines(self) -> None:
        while self.engines_row.count():
            it = self.engines_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        missing = 0
        for eid in REQUIRED:
            eng = engines.get_tool(eid) or engines.get_engine(eid)
            status, _msg = eng.status()
            missing += status != engines.READY
            chip = QFrame()
            chip.setObjectName("CardFlat")
            chip.setCursor(Qt.PointingHandCursor)
            lay = QVBoxLayout(chip)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(6)
            top = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(10, 10)
            color = {engines.READY: theme.CURRENT.success, engines.NOT_INSTALLED: theme.CURRENT.warning}.get(
                status, theme.CURRENT.faint)
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
            top.addWidget(dot)
            n = label(eng.info.name.split(" — ")[0])
            n.setStyleSheet("font-weight: 700;")
            top.addWidget(n, 1)
            lay.addLayout(top)
            lay.addWidget(label(eng.info.tagline, "Hint", wrap=True))
            badge = Badge({engines.READY: "Prêt", engines.NOT_INSTALLED: "À installer"}.get(status, "Indisponible"),
                          {engines.READY: "success", engines.NOT_INSTALLED: "warning"}.get(status, "muted"))
            lay.addWidget(badge, 0, Qt.AlignLeft)
            chip.mouseReleaseEvent = lambda e: self.ctx.navigate("engines")
            self.engines_row.addWidget(chip, 1)
        self.install_btn.setVisible(missing > 0)
