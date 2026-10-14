"""Page Intervenants : les personnages des dialogues (et le professeur), leur langue, leur sexe et leur voix.

Sans voix choisie, un intervenant reçoit automatiquement une voix native de sa langue, différente de celle des
autres personnages (femmes et hommes en alternance)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...core import languages
from ...core.models import HOST_ROLES, Host

PAN_CHOICES = [(None, "Stéréo : auto"), (-1.0, "À gauche"), (-0.5, "Un peu à gauche"), (0.0, "Au centre"),
               (0.5, "Un peu à droite"), (1.0, "À droite")]
from .. import icons, theme
from ..widgets import Avatar, Card, IconButton, button, card_title, label
from .base import Page
from .voices import COLORS


def host_color(name: str) -> str:
    return COLORS[sum(map(ord, name or "?")) % len(COLORS)]


def sync_cast(project) -> None:
    """Recopie les voix des intervenants dans la distribution (utilisée par les autres pages)."""
    for h in project.hosts:
        if h.name.strip():
            project.cast[h.name.strip()] = h.voice_id


def rename_in_scripts(project, old: str, new: str) -> int:
    """Remplace « @Ancien: » par « @Nouveau: » dans toutes les leçons ; renvoie le nombre de répliques."""
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
        self.pan = QComboBox()
        self.pan.setToolTip("Place de la voix dans le son stéréo, comme autour d'une table de studio")
        for value, text in PAN_CHOICES:
            self.pan.addItem(text, value)
        current = next((i for i, (v, _t) in enumerate(PAN_CHOICES)
                        if (v is None and host.pan is None) or (v is not None and host.pan is not None
                                                                 and abs(v - host.pan) < 0.01)), 0)
        self.pan.setCurrentIndex(current)
        self.pan.currentIndexChanged.connect(self._changed)
        top.addWidget(self.pan)
        col.addLayout(top)
        mid = QHBoxLayout()
        self.lang = QComboBox()
        self.lang.setToolTip("Langue que parle cet intervenant (voix native automatique)")
        self.lang.addItem("Langue apprise de la leçon", "")
        for lg in languages.sorted_languages():
            self.lang.addItem(lg.name, lg.code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(host.language)))
        self.lang.currentIndexChanged.connect(self._changed)
        mid.addWidget(self.lang, 1)
        self.gender = QComboBox()
        for key, text in (("", "Femme ou homme"), ("F", "Femme"), ("M", "Homme")):
            self.gender.addItem(text, key)
        self.gender.setCurrentIndex(max(0, self.gender.findData(host.gender)))
        self.gender.currentIndexChanged.connect(self._changed)
        mid.addWidget(self.gender)
        col.addLayout(mid)
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
        tag = IconButton("edit", "Insérer « @Nom: » dans la leçon ouverte", 34, 15)
        tag.clicked.connect(self._insert_tag)
        lay.addWidget(tag)
        rm = IconButton("trash", "Retirer", 34, 15, color=theme.CURRENT.danger)
        rm.clicked.connect(lambda: self.page.remove(self.host))
        lay.addWidget(rm)
        self.fill_voices()

    def fill_voices(self) -> None:
        self.voice.blockSignals(True)
        self.voice.clear()
        self.voice.addItem(icons.icon("globe", theme.CURRENT.accent2, 16), "Voix native automatique", "")
        for v in self.page.ctx.library.all():
            self.voice.addItem(icons.icon("mic" if v.is_clone else "user", v.color, 16), v.name, v.id)
        self.voice.setCurrentIndex(max(0, self.voice.findData(self.host.voice_id)))
        self.voice.blockSignals(False)

    def set_count(self, n: int) -> None:
        v = self.page.ctx.library.get(self.host.voice_id)
        txt = f"{n} réplique(s) dans les leçons" if n else "Aucune réplique pour l'instant"
        if v is None:
            auto = self.page.auto_voice(self.host)
            txt += f" · voix native automatique : {auto.name}" if auto else ""
        self.info.setText(txt)

    def _changed(self, *_a) -> None:
        self.host.role = self.role.currentData() or "host"
        self.host.voice_id = self.voice.currentData() or ""
        self.host.bio = self.bio.text().strip()
        self.host.pan = self.pan.currentData()
        self.host.language = self.lang.currentData() or ""
        self.host.gender = self.gender.currentData() or ""
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
        v = self.page.ctx.library.get(self.host.voice_id) or self.page.auto_voice(self.host)
        if v is None:
            self.page.ctx.toast("Aucune voix pour cet intervenant.", "warning")
            return
        code = self.host.language or self.page.ctx.project.metadata.target_language
        hello = languages.sample_sentence(code)
        self.page.ctx.preview_voice(v, f"{hello} {self.host.name}." if hello else None, language=code)

    def _insert_tag(self) -> None:
        page = self.page.ctx.window.pages.get("manuscript")
        if page is None or page._current is None:
            self.page.ctx.toast("Ouvrez d'abord une leçon.", "warning")
            return
        self.page.ctx.navigate("manuscript")
        page._tag_role(self.host.name)


class HostsPage(Page):
    name = "hosts"

    def __init__(self, ctx):
        super().__init__(ctx, "Intervenants",
                         "Les personnages des dialogues et leurs voix. Dans le script, chaque réplique commence par "
                         "leur nom : « @Maria: [es] ¡Hola! ». Sans voix choisie, chacun reçoit une voix native de sa "
                         "langue.", scroll=True)
        self._loading = False
        add_host = button("Ajouter un personnage", "plus", "primary")
        add_host.clicked.connect(lambda: self.add("guest"))
        add_guest = button("Ajouter un professeur", "user")
        add_guest.clicked.connect(lambda: self.add("host"))
        clone = button("Cloner une voix", "mic", tooltip="Créez une voix à partir d'un enregistrement (la vôtre, "
                       "celle d'un professeur…)")
        clone.clicked.connect(lambda: self.ctx.navigate("voices"))
        for b in (clone, add_guest, add_host):
            self.header.add_action(b)

        main = Card()
        main.add(card_title("Voix d'explication", "Lit les consignes, les traductions et tout le texte sans balise "
                            "de langue ni « @Nom: » (« @Prof: » aussi).", "user"))
        mr = QHBoxLayout()
        self.narrator = QComboBox()
        self.narrator.setMinimumWidth(300)
        self.narrator.currentIndexChanged.connect(self._narrator_changed)
        mr.addWidget(self.narrator)
        mr.addStretch(1)
        main.add(mr)
        self.body.addWidget(main)

        people = Card()
        people.add(card_title("Qui parle ?", "Indiquez la langue et le sexe de chaque personnage : une voix native "
                              "différente lui est attribuée. Vous pouvez aussi choisir une voix précise, une voix "
                              "clonée — ou votre vraie voix (Leçons → Studio → Enregistrer au micro).", "users"))
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
            self.rows_box.addWidget(label("Aucun intervenant pour l'instant. Les personnages des dialogues créés par "
                                          "l'assistant IA s'ajoutent ici automatiquement.", "Hint"))
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
            self.unknown.setText("Noms utilisés dans les leçons mais absents de cette liste : "
                                 + ", ".join(unknown) + ". Ils parlent la langue apprise avec une voix native "
                                 "automatique ; ajoutez-les pour choisir leur langue, leur sexe ou leur voix.")

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

    def auto_voice(self, host: Host):
        """Voix native que recevra cet intervenant s'il n'a pas de voix choisie."""
        from ...core import renderer

        pr = self.ctx.project
        from ...core import course

        explain = course.explain_code(pr)
        if host.role == "host" and (not host.language or getattr(languages.get(host.language), "code", "") == explain):
            return self.ctx.library.get(pr.narrator_voice_id)  # le professeur parle avec la voix d'explication
        res = renderer.VoiceResolver(pr, self.ctx.library)
        spec = host.language or pr.metadata.target_locale or pr.metadata.target_language
        lang = languages.get(spec)
        if lang is None:
            return None
        same = [h for h in pr.hosts if (languages.get(h.language or pr.metadata.target_language) is lang)
                and h.gender == host.gender and not h.voice_id]
        idx = next((i for i, h in enumerate(same) if h.id == host.id), 0)
        return res.native(spec, None, idx, host.gender)

    def add(self, role: str = "guest") -> None:
        pr = self.ctx.project
        base = "Professeur" if role == "host" else "Personnage"
        n = 1
        name = base
        while pr.host_by_name(name) is not None:
            n += 1
            name = f"{base} {n}"
        gender = "F" if sum(1 for h in pr.hosts if h.role != "host") % 2 == 0 else "M"
        pr.hosts.append(Host(name, role, "", language="" if role != "host" else pr.metadata.language or "fr",
                             gender=gender))
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
        self.ctx.toast(f"« {host.name} » retiré. Ses répliques gardent une voix native automatique.", "info")
