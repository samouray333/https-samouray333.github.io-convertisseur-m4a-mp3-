"""Page Animateurs : les personnes qui parlent dans le podcast (animateurs, invités, voix off) et leurs voix."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...core.models import HOST_ROLES, Host
from .. import icons, theme
from ..widgets import Avatar, Card, IconButton, button, card_title, label
from .base import Page
from .voices import COLORS


def host_color(name: str) -> str:
    return COLORS[sum(map(ord, name or "?")) % len(COLORS)]


def sync_cast(project) -> None:
    """Recopie les voix des animateurs dans la distribution (utilisée par les autres pages)."""
    for h in project.hosts:
        if h.name.strip():
            project.cast[h.name.strip()] = h.voice_id


def rename_in_scripts(project, old: str, new: str) -> int:
    """Remplace « @Ancien: » par « @Nouveau: » dans tous les épisodes ; renvoie le nombre de répliques."""
    rx = re.compile(r"(?m)^@" + re.escape(old.strip()) + r"\s*:", re.IGNORECASE)
    count = 0
    for ch in project.chapters:
        ch.text, n = rx.subn(f"@{new.strip()}:", ch.text)
        count += n
    return count


def lines_per_host(project) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in project.chapters:
        for m in re.finditer(r"(?m)^@([^:\n]{1,40}):", ch.text):
            key = m.group(1).strip().lower()
            counts[key] = counts.get(key, 0) + 1
    return counts


class HostRow(QFrame):
    def __init__(self, page: "HostsPage", host: Host):
        super().__init__()
        self.page = page
        self.host = host
        self.setObjectName("CardFlat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.avatar = Avatar(host.name, host_color(host.name), 40)
        lay.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(6)
        top = QHBoxLayout()
        self.name = QLineEdit(host.name)
        self.name.setPlaceholderText("Prénom ou pseudonyme")
        self.name.setMinimumWidth(180)
        self.name.setStyleSheet("font-weight: 700;")
        self.name.editingFinished.connect(self._renamed)
        top.addWidget(self.name, 1)
        self.role = QComboBox()
        for key, text in HOST_ROLES.items():
            self.role.addItem(text, key)
        self.role.setCurrentIndex(max(0, self.role.findData(host.role)))
        self.role.currentIndexChanged.connect(self._changed)
        top.addWidget(self.role)
        self.voice = QComboBox()
        self.voice.setMinimumWidth(260)
        self.voice.currentIndexChanged.connect(self._changed)
        top.addWidget(self.voice)
        col.addLayout(top)
        self.bio = QLineEdit(host.bio)
        self.bio.setPlaceholderText("Présentation (facultatif) : métier, personnalité, ton… — aide l'assistant IA")
        self.bio.textEdited.connect(self._changed)
        col.addWidget(self.bio)
        self.info = label("", "Faint")
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        play = IconButton("play", "Écouter cette voix", 34, 15, color=theme.CURRENT.accent)
        play.clicked.connect(self._preview)
        lay.addWidget(play)
        tag = IconButton("edit", "Insérer « @Nom: » dans l'épisode ouvert", 34, 15)
        tag.clicked.connect(self._insert_tag)
        lay.addWidget(tag)
        rm = IconButton("trash", "Retirer", 34, 15, color=theme.CURRENT.danger)
        rm.clicked.connect(lambda: self.page.remove(self.host))
        lay.addWidget(rm)
        self.fill_voices()

    def fill_voices(self) -> None:
        self.voice.blockSignals(True)
        self.voice.clear()
        self.voice.addItem(icons.icon("user", theme.CURRENT.muted, 16), "Choisir une voix…", "")
        for v in self.page.ctx.library.all():
            self.voice.addItem(icons.icon("mic" if v.is_clone else "user", v.color, 16), v.name, v.id)
        self.voice.setCurrentIndex(max(0, self.voice.findData(self.host.voice_id)))
        self.voice.blockSignals(False)

    def set_count(self, n: int) -> None:
        v = self.page.ctx.library.get(self.host.voice_id)
        txt = f"{n} réplique(s) dans les épisodes" if n else "Aucune réplique pour l'instant"
        if v is None:
            txt += " · sans voix : la voix principale sera utilisée"
        self.info.setText(txt)

    def _changed(self, *_a) -> None:
        self.host.role = self.role.currentData() or "host"
        self.host.voice_id = self.voice.currentData() or ""
        self.host.bio = self.bio.text().strip()
        self.page.changed()

    def _renamed(self) -> None:
        new = " ".join(self.name.text().replace(":", " ").split())[:40]
        old = self.host.name
        if not new:
            self.name.setText(old)
            return
        if new == old:
            return
        if self.page.ctx.project.host_by_name(new) is not None:
            self.page.ctx.toast(f"« {new} » existe déjà.", "warning")
            self.name.setText(old)
            return
        n = rename_in_scripts(self.page.ctx.project, old, new) if old else 0
        self.page.ctx.project.cast.pop(old, None)
        self.host.name = new
        self.name.setText(new)
        self.avatar.set(new, host_color(new))
        self.page.changed()
        if n:
            self.page.ctx.toast(f"{n} réplique(s) « @{old}: » renommée(s) en « @{new}: ».", "success")
            self.page.ctx.project_changed.emit()

    def _preview(self) -> None:
        v = self.page.ctx.library.get(self.host.voice_id)
        if v is None:
            self.page.ctx.toast("Choisissez d'abord une voix.", "warning")
            return
        role = HOST_ROLES.get(self.host.role, "").lower()
        self.page.ctx.preview_voice(v, f"Bonjour, je suis {self.host.name}, {role} de ce podcast. "
                                       "Merci de nous écouter, et bonne écoute !")

    def _insert_tag(self) -> None:
        page = self.page.ctx.window.pages.get("manuscript")
        if page is None or page._current is None:
            self.page.ctx.toast("Ouvrez d'abord un épisode.", "warning")
            return
        self.page.ctx.navigate("manuscript")
        page._tag_role(self.host.name)


class HostsPage(Page):
    name = "hosts"

    def __init__(self, ctx):
        super().__init__(ctx, "Animateurs et invités",
                         "Les personnes qui parlent dans votre podcast et leurs voix. Dans le script, chaque "
                         "réplique commence par leur nom : « @Alex: Bonjour ! ».", scroll=True)
        self._loading = False
        add_host = button("Ajouter un animateur", "plus", "primary")
        add_host.clicked.connect(lambda: self.add("host"))
        add_guest = button("Ajouter un invité", "user")
        add_guest.clicked.connect(lambda: self.add("guest"))
        clone = button("Cloner une voix", "mic", tooltip="Créez la voix d'un animateur à partir d'un enregistrement")
        clone.clicked.connect(lambda: self.ctx.navigate("voices"))
        for b in (clone, add_guest, add_host):
            self.header.add_action(b)

        main = Card()
        main.add(card_title("Voix principale", "Lit le texte qui n'est attribué à personne (paragraphes sans "
                            "« @Nom: ») et annonce le titre des épisodes.", "user"))
        mr = QHBoxLayout()
        self.narrator = QComboBox()
        self.narrator.setMinimumWidth(300)
        self.narrator.currentIndexChanged.connect(self._narrator_changed)
        mr.addWidget(self.narrator)
        mr.addStretch(1)
        main.add(mr)
        self.body.addWidget(main)

        people = Card()
        people.add(card_title("Qui parle ?", "Donnez une voix différente à chacun pour que l'auditeur les "
                              "reconnaisse. Voix Microsoft (en ligne), Kokoro (hors ligne) ou voix clonée.", "users"))
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        holder = QWidget()
        holder.setLayout(self.rows_box)
        people.add(holder)
        self.unknown = label("", "Hint", wrap=True)
        people.add(self.unknown)
        self.body.addWidget(people)
        self.body.addStretch(1)
        self.rows: list[HostRow] = []
        ctx.voices_changed.connect(self._refresh_voices)

    # -- synchronisation ---------------------------------------------------------------
    def on_project_changed(self) -> None:
        self.reload()

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        pr = self.ctx.project
        self._loading = True
        self.narrator.blockSignals(True)
        self.narrator.clear()
        for v in self.ctx.library.all():
            self.narrator.addItem(icons.icon("mic" if v.is_clone else "user", v.color, 16), v.name, v.id)
        self.narrator.setCurrentIndex(max(0, self.narrator.findData(pr.narrator_voice_id)))
        self.narrator.blockSignals(False)
        self._loading = False
        while self.rows_box.count():
            w = self.rows_box.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.rows = []
        if not pr.hosts:
            self.rows_box.addWidget(label("Aucun animateur pour l'instant : ajoutez-en un.", "Hint"))
        for h in pr.hosts:
            row = HostRow(self, h)
            self.rows.append(row)
            self.rows_box.addWidget(row)
        self._update_counts()

    def _refresh_voices(self) -> None:
        for r in self.rows:
            r.fill_voices()

    def _update_counts(self) -> None:
        pr = self.ctx.project
        counts = lines_per_host(pr)
        for r in self.rows:
            r.set_count(counts.get(r.host.name.strip().lower(), 0))
        known = {h.name.strip().lower() for h in pr.hosts}
        unknown = sorted({m for m in counts if m not in known})
        self.unknown.setVisible(bool(unknown))
        if unknown:
            self.unknown.setText("Noms utilisés dans les scripts mais absents de cette liste : "
                                 + ", ".join(unknown) + ". Ajoutez-les pour leur donner une voix.")

    # -- actions -----------------------------------------------------------------------
    def changed(self) -> None:
        if self._loading:
            return
        sync_cast(self.ctx.project)
        self.ctx.mark_dirty()
        self._update_counts()

    def _narrator_changed(self, _i: int) -> None:
        if self._loading:
            return
        vid = self.narrator.currentData()
        if vid:
            self.ctx.project.narrator_voice_id = vid
            self.ctx.mark_dirty()

    def add(self, role: str = "host") -> None:
        pr = self.ctx.project
        base = "Invité" if role == "guest" else "Animateur"
        n = 1
        name = base
        while pr.host_by_name(name) is not None:
            n += 1
            name = f"{base} {n}"
        taken = {h.voice_id for h in pr.hosts}
        free = next((v for v in self.ctx.library.all() if v.id not in taken and v.language == "fr"), None)
        pr.hosts.append(Host(name, role, free.id if free else ""))
        self.changed()
        self.reload()
        if self.rows:
            self.rows[-1].name.setFocus()
            self.rows[-1].name.selectAll()

    def remove(self, host: Host) -> None:
        pr = self.ctx.project
        pr.hosts = [h for h in pr.hosts if h.id != host.id]
        pr.cast.pop(host.name, None)
        self.changed()
        self.reload()
        self.ctx.toast(f"« {host.name} » retiré. Ses répliques seront lues par la voix principale.", "info")
