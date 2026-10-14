"""Page Personnages : le narrateur et les personnages des histoires (héros, animaux, fées…), leur voix et leur
façon de parler, et le prénom de l'enfant."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...core.models import HOST_ROLES, VOICE_STYLES, Host

PAN_CHOICES = [(None, "Stéréo : auto"), (-1.0, "À gauche"), (-0.5, "Un peu à gauche"), (0.0, "Au centre"),
               (0.5, "Un peu à droite"), (1.0, "À droite")]
from .. import icons, theme
from ..widgets import Avatar, Card, IconButton, button, card_title, label
from .base import Page
from .voices import COLORS


def host_color(name: str) -> str:
    return COLORS[sum(map(ord, name or "?")) % len(COLORS)]


def sync_cast(project) -> None:
    """Recopie les voix des personnages dans la distribution (utilisée par les autres pages)."""
    for h in project.hosts:
        if h.name.strip():
            project.cast[h.name.strip()] = h.voice_id


def rename_in_scripts(project, old: str, new: str) -> int:
    """Remplace « @Ancien: » par « @Nouveau: » dans toutes les histoires ; renvoie le nombre de répliques."""
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
        self.name.setPlaceholderText("Nom du personnage")
        self.name.setMinimumWidth(150)
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
        self.voice.setMinimumWidth(200)
        self.voice.currentIndexChanged.connect(self._changed)
        top.addWidget(self.voice)
        self.style = QComboBox()
        self.style.setToolTip("Façon de parler : voix plus aiguë pour un enfant ou une souris, plus grave pour un "
                              "géant ou un dragon (fonctionne avec toutes les voix, même clonées)")
        for key, (text, _p, _r) in VOICE_STYLES.items():
            self.style.addItem(text, key)
        self.style.setCurrentIndex(max(0, self.style.findData(host.style)))
        self.style.currentIndexChanged.connect(self._changed)
        second = QHBoxLayout()  # façon de parler, place stéréo et description sur la deuxième ligne
        second.addWidget(self.style)
        self.pan = QComboBox()
        self.pan.setToolTip("Place de la voix dans le son stéréo, comme autour d'une table de studio")
        for value, text in PAN_CHOICES:
            self.pan.addItem(text, value)
        current = next((i for i, (v, _t) in enumerate(PAN_CHOICES)
                        if (v is None and host.pan is None) or (v is not None and host.pan is not None
                                                                 and abs(v - host.pan) < 0.01)), 0)
        self.pan.setCurrentIndex(current)
        self.pan.currentIndexChanged.connect(self._changed)
        second.addWidget(self.pan)
        col.addLayout(top)
        self.bio = QLineEdit(host.bio)
        self.bio.setPlaceholderText("Description (facultatif) : qui il est, son caractère… — aide l'assistant IA à "
                                    "garder le personnage d'une histoire à l'autre")
        self.bio.textEdited.connect(self._changed)
        second.addWidget(self.bio, 1)
        col.addLayout(second)
        self.info = label("", "Faint")
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        play = IconButton("play", "Écouter cette voix", 34, 15, color=theme.CURRENT.accent)
        play.clicked.connect(self._preview)
        lay.addWidget(play)
        tag = IconButton("edit", "Insérer « @Nom: » dans l'histoire ouverte", 34, 15)
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
        txt = f"{n} réplique(s) dans les histoires" if n else "Aucune réplique pour l'instant"
        if v is None:
            txt += " · sans voix : la voix du narrateur sera utilisée"
        if "{" in self.host.name:
            child = self.page.ctx.project.metadata.child_name
            txt += f" · « {self.host.name} » devient « {child or 'Lou'} » (prénom de l'enfant)"
        self.info.setText(txt)

    def _changed(self, *_a) -> None:
        self.host.role = self.role.currentData() or "host"
        self.host.voice_id = self.voice.currentData() or ""
        self.host.bio = self.bio.text().strip()
        self.host.pan = self.pan.currentData()
        self.host.style = self.style.currentData() or "normal"
        self.host.pitch = None
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
        from ...core.models import Chapter, Project
        from ...core.textproc import personalize

        name = personalize(self.host.name, self.page.ctx.project.metadata.child_name)
        sample = Project(hosts=[self.host], metadata=self.page.ctx.project.metadata)
        sample.chapters = [Chapter("", f"@{self.host.name}: Bonjour ! Je m'appelle {name}. Tu veux venir avec moi "
                                       "dans une nouvelle histoire ?")]
        self.page.preview_character(v, sample, name)

    def _insert_tag(self) -> None:
        page = self.page.ctx.window.pages.get("manuscript")
        if page is None or page._current is None:
            self.page.ctx.toast("Ouvrez d'abord une histoire.", "warning")
            return
        self.page.ctx.navigate("manuscript")
        page._tag_role(self.host.name)


class HostsPage(Page):
    name = "hosts"

    def __init__(self, ctx):
        super().__init__(ctx, "Personnages",
                         "Le narrateur et les personnages de vos histoires. Dans le texte, chaque réplique commence "
                         "par le nom du personnage : « @Pompon: J'ai peur du noir ! ».", scroll=True)
        self._loading = False
        add_char = button("Ajouter un personnage", "plus", "primary")
        add_char.clicked.connect(lambda: self.add("character"))
        add_animal = button("Ajouter un animal", "star")
        add_animal.clicked.connect(lambda: self.add("animal"))
        for b in (add_animal, add_char):
            self.header.add_action(b)

        main = Card()
        main.add(card_title("Le narrateur", "Il raconte l'histoire (tout ce qui n'est pas une réplique) et annonce "
                            "le titre.", "book"))
        mr = QHBoxLayout()
        self.narrator = QComboBox()
        self.narrator.setMinimumWidth(300)
        self.narrator.currentIndexChanged.connect(self._narrator_changed)
        mr.addWidget(self.narrator)
        listen = button("Écouter", "play")
        listen.clicked.connect(self._preview_narrator)
        mr.addWidget(listen)
        mr.addStretch(1)
        main.add(mr)
        family = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        family.add(label("La voix de papa, maman, papi ou mamie pour raconter : enregistrez une minute de lecture, "
                         "l'application crée la voix (gratuit, sur cet ordinateur). La personne enregistrée doit être "
                         "d'accord : une case de consentement vous le demande.", "Hint", wrap=True))
        fr = QHBoxLayout()
        for who in ("papa", "maman", "papi", "mamie"):
            b = button(f"Voix de {who}", "mic")
            b.clicked.connect(lambda _=False, w=who: self.clone_family(w))
            fr.addWidget(b)
        fr.addStretch(1)
        family.add(fr)
        main.add(family)
        self.body.addWidget(main)

        kid = Card()
        kid.add(card_title("Le héros, c'est votre enfant", "Son prénom remplace « {prénom} » dans les histoires et "
                           "les titres ; l'assistant IA en fait le héros des nouvelles histoires.", "star"))
        kr = QHBoxLayout()
        self.child = QLineEdit()
        self.child.setPlaceholderText("Prénom de l'enfant")
        self.child.setMaximumWidth(280)
        self.child.editingFinished.connect(self._child_changed)
        kr.addWidget(self.child)
        kr.addWidget(label("Sans prénom, « {prénom} » est lu « Lou ».", "Faint"), 1)
        kid.add(kr)
        self.body.addWidget(kid)

        people = Card()
        people.add(card_title("Qui parle ?", "Une voix différente et une façon de parler pour chacun : l'enfant "
                              "reconnaît tout de suite qui parle. Voix Microsoft (en ligne), Kokoro (hors ligne), voix "
                              "clonée — ou votre vraie voix, réplique par réplique (Histoires → Mise en scène → "
                              "Enregistrer au micro).", "users"))
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
        self.child.setText(pr.metadata.child_name)
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
            self.rows_box.addWidget(label("Aucun personnage pour l'instant : ils sont ajoutés quand l'assistant "
                                          "écrit une histoire, ou ajoutez-les vous-même.", "Hint"))
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

    def _child_changed(self) -> None:
        name = " ".join(self.child.text().split())[:40]
        if name != self.ctx.project.metadata.child_name:
            from ...core.library import refresh_name_covers

            self.ctx.project.metadata.child_name = name
            if refresh_name_covers(self.ctx.project):
                from PySide6.QtGui import QPixmapCache

                QPixmapCache.clear()
            self.ctx.mark_dirty()
            self._update_counts()
            for r in self.rows:
                r.set_count(lines_per_host(self.ctx.project).get(r.host.name.strip().lower(), 0))

    def preview_character(self, voice, sample, name: str) -> None:
        """Écoute d'un personnage avec sa façon de parler (hauteur et débit)."""
        from ...core import renderer
        from .. import tasks

        def work():
            plan = renderer.build_chapter_plan(sample, sample.chapters[0], self.ctx.library)
            r = renderer.Renderer(sample, self.ctx.library)
            seg = plan.segments[0]
            return r.synth_segment(seg)

        sample.path = None
        self.ctx.toast(f"Génération de l'aperçu « {name} »…", "info", 2200)
        self._prev_task = tasks.run(work, on_done=lambda path: self.ctx.play(path, f"Aperçu — {name}"),
                                    on_error=lambda m, _t: self.ctx.toast(f"Aperçu impossible : {m}", "error", 6500))

    def _preview_narrator(self) -> None:
        v = self.ctx.library.get(self.ctx.project.narrator_voice_id)
        if v is not None:
            self.ctx.preview_voice(v, "Il était une fois, dans une petite maison au bord de la forêt, un enfant qui "
                                      "adorait les histoires.")

    def clone_family(self, who: str) -> None:
        """Ouvre l'assistant de clonage ; la voix créée devient celle du narrateur."""
        page = self.ctx.window.pages.get("voices")
        if page is None:
            return
        self.ctx.navigate("voices")
        voice = page.open_clone_wizard(default_name=f"Voix de {who}")
        if voice is not None:
            self.ctx.project.narrator_voice_id = voice.id
            self.ctx.mark_dirty()
            self.ctx.toast(f"« {voice.name} » raconte maintenant les histoires de cette collection.", "success", 6000)
            self.ctx.navigate("hosts")

    def add(self, role: str = "character") -> None:
        pr = self.ctx.project
        base = "Animal" if role == "animal" else "Personnage"
        n = 1
        name = base
        while pr.host_by_name(name) is not None:
            n += 1
            name = f"{base} {n}"
        taken = {h.voice_id for h in pr.hosts}
        free = next((v for v in self.ctx.library.all() if v.id not in taken and v.language == "fr"), None)
        pr.hosts.append(Host(name, role, free.id if free else "", style="petit" if role == "animal" else "normal"))
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
        self.ctx.toast(f"« {host.name} » retiré. Ses répliques seront lues par le narrateur.", "info")
