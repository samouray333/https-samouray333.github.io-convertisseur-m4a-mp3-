"""Page Bibliothèque : toutes les collections d'histoires, leurs couvertures, durées et favoris."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ...config import settings
from ...core import library
from ...core.story import AGES
from .. import icons, theme
from ..widgets import Badge, Card, IconButton, button, label
from .base import Page

FILTERS = [("all", "Toutes les histoires"), ("fav", "Favoris"), ("night", "Histoires du soir"),
           ("ready", "Prêtes à écouter")] + [(f"age:{k}", a.label) for k, a in AGES.items()]


def cover_pixmap(path: str, size: int) -> QPixmap:
    pm = QPixmap(path) if path else QPixmap()
    if pm.isNull():
        pm = icons.pixmap("book", theme.CURRENT.faint, size // 2)
        out = QPixmap(size, size)
        out.fill(Qt.transparent)
        from PySide6.QtGui import QPainter

        p = QPainter(out)
        p.drawPixmap((size - pm.width()) // 2, (size - pm.height()) // 2, pm)
        p.end()
        return out
    return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def matches(entry: library.StoryEntry, flt: str, query: str) -> bool:
    if query and query.lower() not in (entry.title + " " + entry.summary + " " + entry.collection).lower():
        return False
    if flt == "fav":
        return entry.favorite
    if flt == "night":
        return entry.bedtime
    if flt == "ready":
        return bool(entry.audio)
    if flt.startswith("age:"):
        return entry.age == flt[4:]
    return True


class StoryTile(QFrame):
    def __init__(self, page: "LibraryPage", entry: library.StoryEntry):
        super().__init__()
        self.page = page
        self.entry = entry
        self.setObjectName("CardHover")
        self.setFixedWidth(196)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        img = QLabel()
        img.setFixedSize(176, 176)
        img.setPixmap(cover_pixmap(entry.cover, 176))
        img.setStyleSheet(f"background: {theme.CURRENT.surface2}; border-radius: 12px;")
        lay.addWidget(img)
        t = label(entry.title, wrap=True)
        t.setStyleSheet("font-weight: 700;")
        lay.addWidget(t)
        info = " · ".join(x for x in (library.format_minutes(entry.duration, entry.estimated),
                                      AGES[entry.age].label if entry.age in AGES else "") if x)
        lay.addWidget(label(info, "Hint"))
        row = QHBoxLayout()
        row.setSpacing(4)
        self.fav = IconButton("star-filled" if entry.favorite else "star", "Favori", 30, 16,
                              color=theme.CURRENT.accent2 if entry.favorite else theme.CURRENT.muted)
        self.fav.clicked.connect(lambda: page.toggle_favorite(entry))
        row.addWidget(self.fav)
        if entry.bedtime:
            row.addWidget(Badge("☾ soir", "info"))
        row.addStretch(1)
        play = IconButton("play", "Écouter" if entry.audio else "Pas encore produite", 32, 16,
                          color=theme.CURRENT.accent)
        play.setEnabled(bool(entry.audio))
        play.clicked.connect(lambda: page.ctx.play(entry.audio, entry.title))
        row.addWidget(play)
        op = IconButton("edit", "Ouvrir dans l'éditeur", 30, 15)
        op.clicked.connect(lambda: page.open_story(entry))
        row.addWidget(op)
        lay.addLayout(row)
        self.setToolTip(entry.summary or entry.title)


class LibraryPage(Page):
    name = "library"

    def __init__(self, ctx):
        super().__init__(ctx, "Bibliothèque", "Toutes vos collections d'histoires. Une collection est une série avec "
                         "les mêmes personnages ; chaque histoire a sa couverture et sa durée.", scroll=True)
        kids = button("Coin lecture", "star-filled", "primary", tooltip="Mode lecture pour l'enfant")
        kids.clicked.connect(lambda: self.ctx.window.open_kids_mode())
        new = button("Nouvelle collection", "plus")
        new.clicked.connect(lambda: self.ctx.window.new_empty_project())
        samples = button("Histoires d'exemple", "star")
        samples.clicked.connect(lambda: self.ctx.window.open_samples())
        for b in (samples, new, kids):
            self.header.add_action(b)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher une histoire…")
        self.search.textChanged.connect(self.refresh_view)
        self.filter = QComboBox()
        for key, text in FILTERS:
            self.filter.addItem(text, key)
        self.filter.currentIndexChanged.connect(self.refresh_view)
        refresh = IconButton("refresh", "Actualiser", 34, 16)
        refresh.clicked.connect(self.reload)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        bar.addWidget(refresh)
        self.body.addLayout(bar)
        self.box = QVBoxLayout()
        self.box.setSpacing(18)
        holder = QWidget()
        holder.setLayout(self.box)
        self.body.addWidget(holder)
        self.body.addStretch(1)
        self.collections: list[library.Collection] = []

    def on_show(self) -> None:
        self.reload()

    def project_paths(self) -> list[Path]:
        extra = list(settings().recent_projects())
        if self.ctx.project.path is not None:
            extra.insert(0, str(self.ctx.project.path))
        return library.find_projects([settings().projects_dir()], extra)

    def reload(self) -> None:
        self.collections = library.load_collections(self.project_paths(), self.ctx.project)
        self.refresh_view()

    def refresh_view(self, *_a) -> None:
        while self.box.count():
            w = self.box.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        flt, query = self.filter.currentData() or "all", self.search.text().strip()
        shown = 0
        for col in self.collections:
            stories = [s for s in col.stories if matches(s, flt, query)]
            if not stories:
                continue
            shown += len(stories)
            card = Card()
            head = QHBoxLayout()
            img = QLabel()
            img.setPixmap(cover_pixmap(col.cover, 56))
            head.addWidget(img)
            tc = QVBoxLayout()
            tl = label(col.title)
            tl.setStyleSheet("font-weight: 800; font-size: 13pt;")
            tc.addWidget(tl)
            info = f"{len(col.stories)} histoire(s) · {library.format_minutes(col.duration, True)}"
            if col.characters:
                info += " · " + ", ".join(col.characters[:5]) + ("…" if len(col.characters) > 5 else "")
            tc.addWidget(label(info, "Hint", wrap=True))
            head.addLayout(tc, 1)
            op = button("Ouvrir", "folder")
            op.clicked.connect(lambda _=False, p=col.path: self.ctx.window.open_project(str(p)))
            head.addWidget(op)
            card.add(head)
            grid = QGridLayout()
            grid.setSpacing(12)
            for i, s in enumerate(stories):
                grid.addWidget(StoryTile(self, s), i // 5, i % 5)
            grid.setColumnStretch(5, 1)
            card.add(grid)
            self.box.addWidget(card)
        if not shown:
            self.box.addWidget(label("Aucune histoire ne correspond. Créez une histoire, ou ouvrez les histoires "
                                     "d'exemple.", "Hint", wrap=True))

    def _is_current(self, path: Path) -> bool:
        cur = self.ctx.project.path
        return cur is not None and Path(cur).resolve() == Path(path).resolve()

    def toggle_favorite(self, entry: library.StoryEntry) -> None:
        value = not entry.favorite
        if self._is_current(entry.project_path):
            ch = self.ctx.project.chapter_by_id(entry.chapter_id)
            if ch is not None:
                ch.favorite = value
                self.ctx.mark_dirty()
        else:
            try:
                library.set_favorite(entry.project_path, entry.chapter_id, value)
            except Exception as exc:
                self.ctx.toast(f"Favori non enregistré : {exc}", "error")
                return
        self.reload()

    def open_story(self, entry: library.StoryEntry) -> None:
        if not self._is_current(entry.project_path):
            self.ctx.window.open_project(str(entry.project_path))
            if not self._is_current(entry.project_path):
                return
        page = self.ctx.window.pages.get("manuscript")
        self.ctx.navigate("manuscript")
        if page is not None:
            ids = [c.id for c in self.ctx.project.chapters]
            if entry.chapter_id in ids:
                page._reload_list(ids.index(entry.chapter_id))
