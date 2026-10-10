"""Page Voix : bibliothèque, catalogue des voix intégrées, distribution des rôles."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QScrollArea, QSlider, QTabWidget,
                               QVBoxLayout, QWidget)

from ...core import engines
from ...core.models import VoiceProfile
from ...core.textproc import find_characters
from ...core.voices import VOICE_PACK_EXT
from .. import icons, tasks, theme
from ..widgets import (Avatar, Badge, Card, EmptyState, IconButton, ParamSlider, ToggleSwitch, button, card_title,
                       label)
from .base import Page

LANGS = [("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"), ("de", "Allemand"), ("it", "Italien"),
         ("pt", "Portugais"), ("nl", "Néerlandais"), ("pl", "Polonais"), ("ru", "Russe"), ("ar", "Arabe"),
         ("zh", "Chinois"), ("ja", "Japonais"), ("multi", "Multilingue")]
COLORS = ["#7C5CFF", "#FF4FA3", "#4FC3F7", "#69F0AE", "#FFB74D", "#FF7A6B", "#B388FF", "#26C6DA", "#AED581"]


def engine_short(engine_id: str) -> str:
    return {"edge": "Microsoft", "sapi": "Windows", "xtts": "XTTS-v2", "chatterbox": "Chatterbox",
            "kokoro": "Kokoro", "fastclone": "Clonage rapide", "rvc": "RVC"}.get(engine_id, engine_id)


class VoiceCard(QFrame):
    clicked = Signal(str)
    play = Signal(str)
    star = Signal(str)

    def __init__(self, voice: VoiceProfile, narrator: bool):
        super().__init__()
        self.voice_id = voice.id
        self.setObjectName("VoiceCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(Avatar(voice.name, voice.color, 42, "mic" if voice.is_clone else None))
        col = QVBoxLayout()
        col.setSpacing(1)
        n = label(voice.name)
        n.setStyleSheet("font-weight: 700; font-size: 10.5pt;")
        col.addWidget(n)
        col.addWidget(label(f"{engine_short(voice.engine)} · {dict(LANGS).get(voice.language, voice.language)}",
                            "Hint"))
        top.addLayout(col, 1)
        st = IconButton("star-filled" if voice.favorite else "star", "Favori", 28, 15,
                        color=theme.CURRENT.warning if voice.favorite else theme.CURRENT.faint)
        st.clicked.connect(lambda: self.star.emit(self.voice_id))
        top.addWidget(st, 0, Qt.AlignTop)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(6)
        kind = {"clone": ("Clonée", "accent"), "blend": ("Mélange", "info")}.get(voice.kind, ("Intégrée", "muted"))
        row.addWidget(Badge(*kind))
        if narrator:
            row.addWidget(Badge("Narrateur", "success"))
        eng = engines.get_engine(voice.engine)
        if eng is not None and eng.status()[0] != engines.READY:
            row.addWidget(Badge("Moteur à installer" if eng.status()[0] == engines.NOT_INSTALLED else "Indisponible",
                                "warning"))
        row.addStretch(1)
        pb = IconButton("play", "Écouter un aperçu", 32, 14, color=theme.CURRENT.accent)
        pb.clicked.connect(lambda: self.play.emit(self.voice_id))
        row.addWidget(pb)
        lay.addLayout(row)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.voice_id)


class VoiceEditor(Card):
    def __init__(self, page: "VoicesPage"):
        super().__init__(margins=(18, 16, 18, 16), spacing=10)
        self.page = page
        self.ctx = page.ctx
        self.voice: VoiceProfile | None = None
        self._loading = False

        head = QHBoxLayout()
        self.avatar = Avatar("?", theme.CURRENT.accent, 52)
        head.addWidget(self.avatar)
        hc = QVBoxLayout()
        hc.setSpacing(2)
        self.name = QLineEdit()
        self.name.setStyleSheet("font-size: 12.5pt; font-weight: 700;")
        self.name.editingFinished.connect(self._save)
        hc.addWidget(self.name)
        self.sub = label("", "Hint")
        hc.addWidget(self.sub)
        head.addLayout(hc, 1)
        self.add(head)

        self.colors = QHBoxLayout()
        self.colors.setSpacing(6)
        for c in COLORS:
            b = IconButton("record", "", 24, 18, color=c)
            b.clicked.connect(lambda _=False, c=c: self._set_color(c))
            self.colors.addWidget(b)
        self.colors.addStretch(1)
        self.add(self.colors)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.lang = QComboBox()
        for code, name in LANGS:
            self.lang.addItem(name, code)
        self.lang.currentIndexChanged.connect(self._save)
        self.engine = QComboBox()
        self.engine.currentIndexChanged.connect(self._engine_changed)
        form.addWidget(label("Langue", "Muted"), 0, 0)
        form.addWidget(self.lang, 0, 1)
        form.addWidget(label("Moteur", "Muted"), 1, 0)
        form.addWidget(self.engine, 1, 1)
        self.base_lbl = label("Voix de base", "Muted")
        self.base = QComboBox()
        self.base.setToolTip("Voix Microsoft qui lit le texte avant la conversion vers votre timbre")
        self.base.currentIndexChanged.connect(self._base_changed)
        form.addWidget(self.base_lbl, 2, 0)
        form.addWidget(self.base, 2, 1)
        self.add(form)
        self.engine_hint = label("", "Hint", wrap=True)
        self.add(self.engine_hint)

        self.params_box = QVBoxLayout()
        self.params_box.setSpacing(8)
        self.add(label("Réglages de la voix", "SectionTitle"))
        self.add(self.params_box)

        self.refs_title = label("Enregistrements de référence", "SectionTitle")
        self.add(self.refs_title)
        self.refs = QListWidget()
        self.refs.setMaximumHeight(110)
        self.add(self.refs)
        rr = QHBoxLayout()
        self.ref_play = button("Écouter", "play")
        self.ref_play.clicked.connect(self._play_ref)
        self.ref_add = button("Ajouter", "plus", tooltip="Plusieurs extraits améliorent la ressemblance (XTTS)")
        self.ref_add.clicked.connect(self._add_ref)
        self.ref_del = IconButton("trash", "Retirer l'extrait", 34, 16, color=theme.CURRENT.danger)
        self.ref_del.clicked.connect(self._del_ref)
        rr.addWidget(self.ref_play)
        rr.addWidget(self.ref_add)
        rr.addStretch(1)
        rr.addWidget(self.ref_del)
        self.refs_row = QWidget()
        self.refs_row.setLayout(rr)
        self.add(self.refs_row)

        self.add(label("Phrase de test", "SectionTitle"))
        self.test = QPlainTextEdit()
        self.test.setMaximumHeight(70)
        from ...config import settings

        self.test.setPlainText(settings().get("preview_sentence"))
        self.add(self.test)
        tr = QHBoxLayout()
        self.listen = button("Écouter", "headphones", "primary")
        self.listen.clicked.connect(self._listen)
        self.narr = button("Narrateur", "user", tooltip="Utiliser comme voix principale du projet")
        self.narr.clicked.connect(self._set_narrator)
        tr.addWidget(self.listen, 1)
        tr.addWidget(self.narr)
        self.add(tr)
        self.add(None)
        br = QHBoxLayout()
        dup = IconButton("copy", "Dupliquer", 34, 16)
        dup.clicked.connect(self._duplicate)
        exp = IconButton("download", "Exporter la voix (.alsvoice)", 34, 16)
        exp.clicked.connect(self._export)
        dele = button("Supprimer", "trash", "danger")
        dele.clicked.connect(self._delete)
        br.addWidget(dup)
        br.addWidget(exp)
        br.addStretch(1)
        br.addWidget(dele)
        self.add(br)
        self.setEnabled(False)

    def set_voice(self, voice: VoiceProfile | None) -> None:
        self.voice = voice
        self.setEnabled(voice is not None)
        if voice is None:
            return
        self._loading = True
        self.avatar.set(voice.name, voice.color)
        self.avatar._icon = "mic" if voice.is_clone else None
        self.name.setText(voice.name)
        kind = {"clone": "Voix clonée", "blend": "Mélange de voix"}.get(voice.kind, "Voix intégrée")
        self.sub.setText(f"{kind} · {voice.engine_voice or 'référence personnelle'}")
        self.lang.setCurrentIndex(max(0, self.lang.findData(voice.language)))
        self.engine.clear()
        rvc = voice.engine == "rvc"
        if voice.is_clone and not rvc:
            for eid in engines.CLONING_ENGINES:
                e = engines.get_engine(eid)
                self.engine.addItem(icons.icon("mic", e.info.accent, 16), e.info.name, eid)
        else:
            e = engines.get_engine(voice.engine)
            self.engine.addItem(e.info.name if e else voice.engine, voice.engine)
        self.engine.setCurrentIndex(max(0, self.engine.findData(voice.engine)))
        self.engine.setEnabled(voice.is_clone and not rvc)
        self._loading = False
        self._fill_base()
        self._build_params()
        self._fill_refs()
        for w in (self.refs_title, self.refs, self.refs_row):
            w.setVisible(voice.is_clone)
        self.refs_title.setText("Modèle de voix" if rvc else "Enregistrements de référence")
        for b in (self.ref_play, self.ref_add, self.ref_del):
            b.setEnabled(not rvc)

    def _build_params(self) -> None:
        while self.params_box.count():
            it = self.params_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self.voice is None:
            return
        eng = engines.get_engine(self.voice.engine)
        if eng is None:
            return
        st, msg = eng.status()
        self.engine_hint.setText(msg if st == engines.READY else f"⚠ {msg}")
        params = eng.merged_params(self.voice)
        for spec in eng.info.params:
            s = ParamSlider(spec, params.get(spec.key, spec.default))
            s.changed.connect(self._param_changed)
            self.params_box.addWidget(s)
        reset = button("Valeurs par défaut", "refresh", "ghost")
        reset.clicked.connect(self._reset_params)
        self.params_box.addWidget(reset, 0, Qt.AlignLeft)

    def _fill_refs(self) -> None:
        self.refs.clear()
        if self.voice is None:
            return
        from ...core import audio

        for p in self.voice.reference_paths():
            if p.suffix.lower() in (".pth", ".index"):
                kind = "modèle RVC" if p.suffix.lower() == ".pth" else "index (ressemblance)"
                size = f"{p.stat().st_size / 1e6:.0f} Mo" if p.exists() else "manquant"
                self.refs.addItem(QListWidgetItem(icons.icon("package", theme.CURRENT.accent, 16),
                                                  f"{p.name}  ·  {kind}  ·  {size}"))
                continue
            dur = audio.duration_of(p) if p.exists() else 0
            it = QListWidgetItem(icons.icon("wave", theme.CURRENT.accent, 16),
                                 f"{p.name}  ·  {dur:.1f} s" if p.exists() else f"{p.name} (manquant)")
            it.setData(Qt.UserRole, str(p))
            self.refs.addItem(it)
        if self.refs.count():
            self.refs.setCurrentRow(0)

    # -- modifications -----------------------------------------------------------------
    def _save(self) -> None:
        if self._loading or self.voice is None:
            return
        self.voice.name = self.name.text().strip() or self.voice.name
        self.voice.language = self.lang.currentData() or self.voice.language
        self.ctx.library.save(self.voice)
        self.avatar.set(self.voice.name, self.voice.color)
        self.page.refresh_library(keep=self.voice.id)

    def _set_color(self, c: str) -> None:
        if self.voice is not None:
            self.voice.color = c
            self._save()

    def _fill_base(self) -> None:
        v = self.voice
        show = v is not None and v.engine in ("fastclone", "rvc")
        self.base_lbl.setVisible(show)
        self.base.setVisible(show)
        if not show:
            return
        self.base.blockSignals(True)
        self.base.clear()
        self.base.addItem("Automatique (selon le timbre)", "")
        edge = engines.get_engine("edge")
        for b in edge.list_builtin_voices():
            if b.language in ("fr", "en"):
                self.base.addItem(f"{b.name} — {b.locale}", b.id)
        self.base.setCurrentIndex(max(0, self.base.findData(v.engine_voice or "")))
        self.base.blockSignals(False)

    def _base_changed(self, _i: int) -> None:
        if self._loading or self.voice is None or self.voice.engine not in ("fastclone", "rvc"):
            return
        self.voice.engine_voice = self.base.currentData() or ""
        self.ctx.library.save(self.voice)

    def _engine_changed(self, _i: int) -> None:
        if self._loading or self.voice is None:
            return
        eid = self.engine.currentData()
        if eid and eid != self.voice.engine:
            self.voice.engine = eid
            self.voice.params = {}
            if self.voice.is_clone:
                self.voice.engine_voice = ""
            self.ctx.library.save(self.voice)
            self._build_params()
            self._fill_base()
            self.page.refresh_library(keep=self.voice.id)

    def _param_changed(self, key: str, value: float) -> None:
        if self.voice is not None:
            self.voice.params[key] = value
            self.ctx.library.save(self.voice)

    def _reset_params(self) -> None:
        if self.voice is not None:
            self.voice.params = {}
            self.ctx.library.save(self.voice)
            self._build_params()

    def _listen(self) -> None:
        if self.voice is not None:
            self.listen.setEnabled(False)
            self.ctx.preview_voice(self.voice, self.test.toPlainText().strip() or None,
                                   on_done=lambda _ok: self.listen.setEnabled(True))

    def _set_narrator(self) -> None:
        if self.voice is not None:
            self.ctx.project.narrator_voice_id = self.voice.id
            self.ctx.mark_dirty()
            from ...config import settings

            settings().set("default_voice_id", self.voice.id)
            self.ctx.toast(f"« {self.voice.name} » est maintenant le narrateur.", "success")
            self.ctx.voices_changed.emit()

    def _play_ref(self) -> None:
        it = self.refs.currentItem()
        if it is not None and Path(it.data(Qt.UserRole)).exists():
            self.ctx.play(it.data(Qt.UserRole), f"Référence — {self.voice.name if self.voice else ''}")

    def _add_ref(self) -> None:
        if self.voice is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ajouter un enregistrement de référence", "",
                                              "Audio (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4)")
        if not path:
            return
        from ...core import audio

        voice = self.voice
        target = self.ctx.library.voice_dir(voice) / f"reference_{len(voice.references) + 1:02d}.wav"

        def work():
            data, sr = audio.read_audio(path)
            start, end = audio.best_speech_window(data, sr, 20.0)
            audio.prepare_reference(path, target, start / sr, end / sr)
            return target

        def done(p):
            voice.references.append(Path(p).name)
            self.ctx.library.save(voice)
            self._fill_refs()
            self.ctx.toast("Extrait ajouté.", "success")

        self._task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error"))

    def _del_ref(self) -> None:
        it = self.refs.currentItem()
        if self.voice is None or it is None:
            return
        if len(self.voice.references) <= 1:
            self.ctx.toast("Une voix clonée doit garder au moins un extrait.", "warning")
            return
        name = Path(it.data(Qt.UserRole)).name
        self.voice.references = [r for r in self.voice.references if Path(r).name != name]
        try:
            Path(it.data(Qt.UserRole)).unlink()
        except OSError:
            pass
        self.ctx.library.save(self.voice)
        self._fill_refs()

    def _duplicate(self) -> None:
        if self.voice is not None:
            v = self.ctx.library.duplicate(self.voice.id)
            self.page.refresh_library(keep=v.id if v else None)
            self.ctx.voices_changed.emit()

    def _export(self) -> None:
        if self.voice is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la voix", f"{self.voice.name}{VOICE_PACK_EXT}",
                                              f"Voix AudioLivre (*{VOICE_PACK_EXT})")
        if path:
            self.ctx.library.export_pack(self.voice.id, Path(path))
            self.ctx.toast("Voix exportée.", "success")

    def _delete(self) -> None:
        if self.voice is None:
            return
        if QMessageBox.question(self, "Supprimer la voix",
                                f"Supprimer « {self.voice.name} » de votre bibliothèque ?") != QMessageBox.Yes:
            return
        self.ctx.library.delete(self.voice.id)
        self.voice = None
        self.page.refresh_library()
        self.ctx.voices_changed.emit()


class CatalogTab(QWidget):
    def __init__(self, page: "VoicesPage"):
        super().__init__()
        self.page = page
        self.ctx = page.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.engine = QComboBox()
        self.engine.setMinimumWidth(260)
        for eng in engines.all_engines():
            if eng.info.id in ("edge", "sapi", "xtts", "kokoro"):
                self.engine.addItem(icons.icon("globe" if eng.info.online else "cpu", eng.info.accent, 16),
                                    eng.info.name, eng.info.id)
        self.engine.currentIndexChanged.connect(self.reload)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher une voix…")
        self.search.textChanged.connect(self._filter)
        self.lang = QComboBox()
        self.lang.addItem("Toutes les langues", "")
        for code, name in LANGS[:-1]:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(1)
        self.lang.currentIndexChanged.connect(self._filter)
        refresh = IconButton("refresh", "Actualiser la liste", 36, 18)
        refresh.clicked.connect(lambda: self.reload(refresh=True))
        top.addWidget(self.engine)
        top.addWidget(self.search, 1)
        top.addWidget(self.lang)
        top.addWidget(refresh)
        lay.addLayout(top)
        self.status = label("", "Hint", wrap=True)
        lay.addWidget(self.status)
        self.list = QListWidget()
        self.list.setIconSize(QSize(22, 22))
        self.list.itemDoubleClicked.connect(lambda _it: self._preview())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        prev = button("Écouter", "headphones")
        prev.clicked.connect(self._preview)
        add = button("Ajouter à ma bibliothèque", "plus", "primary")
        add.clicked.connect(self._add)
        row.addWidget(prev)
        row.addStretch(1)
        row.addWidget(add)
        lay.addLayout(row)

        # mélange Kokoro
        self.blend = Card(obj="CardFlat", margins=(14, 12, 14, 12))
        self.blend.add(card_title("Créer une voix par mélange", "Mélangez deux voix Kokoro pour obtenir un timbre "
                                  "unique.", "palette"))
        br = QHBoxLayout()
        self.blend_a = QComboBox()
        self.blend_b = QComboBox()
        self.blend_ratio = QSlider(Qt.Horizontal)
        self.blend_ratio.setRange(0, 100)
        self.blend_ratio.setValue(50)
        mk = button("Créer le mélange", "sparkles")
        mk.clicked.connect(self._make_blend)
        br.addWidget(self.blend_a, 1)
        br.addWidget(self.blend_ratio, 1)
        br.addWidget(self.blend_b, 1)
        br.addWidget(mk)
        self.blend.add(br)
        lay.addWidget(self.blend)
        self._voices: list = []

    def _engine(self):
        return engines.get_engine(self.engine.currentData() or "edge")

    def reload(self, *_args, refresh: bool = False) -> None:
        eng = self._engine()
        if eng is None:
            return
        self.blend.setVisible(eng.info.id == "kokoro")
        st, msg = eng.status()
        self.status.setText(f"{eng.info.description}\nÉtat : {msg}")
        self.list.clear()
        self.list.addItem("Chargement…")

        def done(voices):
            self._voices = voices
            self._filter()
            if eng.info.id == "kokoro":
                for cb in (self.blend_a, self.blend_b):
                    cb.clear()
                    for v in voices:
                        cb.addItem(v.name, v.id)
                if self.blend_b.count() > 1:
                    self.blend_b.setCurrentIndex(1)

        self._task = tasks.run(lambda: eng.list_builtin_voices(refresh), on_done=done,
                               on_error=lambda m, _t: self.status.setText(f"Erreur : {m}"))

    def _filter(self) -> None:
        self.list.clear()
        q = self.search.text().strip().lower()
        lang = self.lang.currentData()
        for v in self._voices:
            if lang and v.language not in (lang, "multi", ""):
                continue
            if q and q not in f"{v.name} {v.locale} {v.description}".lower():
                continue
            g = {"F": "♀", "M": "♂"}.get(v.gender, "")
            extra = f" · {v.description}" if v.description else ""
            it = QListWidgetItem(icons.icon("user", theme.CURRENT.accent if v.gender == "F" else theme.CURRENT.info, 20),
                                 f"{v.name}   {g}   {v.locale or v.language}{extra}")
            it.setData(Qt.UserRole, v)
            self.list.addItem(it)
        if not self.list.count():
            self.list.addItem("Aucune voix ne correspond.")

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def _as_profile(self, bv) -> VoiceProfile:
        eng = self._engine()
        lang = bv.language if bv.language not in ("", "multi") else (self.ctx.project.metadata.language or "fr")
        import random

        return VoiceProfile(name=f"{bv.name}" + (f" ({bv.locale})" if bv.locale else ""), engine=eng.info.id,
                            engine_voice=bv.id, language=lang, gender=bv.gender, color=random.choice(COLORS),
                            description=f"{eng.info.name} — {bv.description}".strip(" —"))

    def _preview(self) -> None:
        bv = self._selected()
        if bv is not None:
            self.ctx.preview_voice(self._as_profile(bv))

    def _add(self) -> None:
        bv = self._selected()
        if bv is None:
            return
        v = self.ctx.library.save(self._as_profile(bv))
        self.ctx.toast(f"« {v.name} » ajoutée à votre bibliothèque.", "success")
        self.page.refresh_library(keep=v.id)
        self.ctx.voices_changed.emit()

    def _make_blend(self) -> None:
        a, b = self.blend_a.currentData(), self.blend_b.currentData()
        if not a or not b or a == b:
            self.ctx.toast("Choisissez deux voix différentes.", "warning")
            return
        r = self.blend_ratio.value() / 100
        spec = f"{a}:{1 - r:.2f},{b}:{r:.2f}"
        v = VoiceProfile(name=f"Mélange {a} + {b}", engine="kokoro", kind="blend", engine_voice=spec,
                         language="fr" if a.startswith("f") or b.startswith("f") else "en", color=COLORS[5])
        self.ctx.preview_voice(v)
        self.ctx.library.save(v)
        self.page.refresh_library(keep=v.id)
        self.ctx.voices_changed.emit()


class CastTab(QWidget):
    def __init__(self, page: "VoicesPage"):
        super().__init__()
        self.page = page
        self.ctx = page.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(14)
        main = Card()
        main.add(card_title("Voix principales", "Le narrateur lit tout le texte, sauf les répliques attribuées à "
                            "un personnage.", "user"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.narrator = QComboBox()
        self.narrator.currentIndexChanged.connect(self._changed)
        self.dialogue = QComboBox()
        self.dialogue.currentIndexChanged.connect(self._changed)
        self.detect = ToggleSwitch("Détecter automatiquement les dialogues (—, -, «, \")")
        self.detect.toggled.connect(self._changed)
        self.incises = ToggleSwitch("Le narrateur lit les incises (« dit-il », « répondit Marie »)")
        self.incises.setToolTip("Les répliques entre guillemets, même au milieu d'un paragraphe, sont lues par la "
                                "voix des dialogues ; le récit et les incises par le narrateur.")
        self.incises.toggled.connect(self._changed)
        g.addWidget(label("Narrateur", "Muted"), 0, 0)
        g.addWidget(self.narrator, 0, 1)
        g.addWidget(IconButton("play", "Écouter", 34, 14, color=theme.CURRENT.accent), 0, 2)
        g.addWidget(label("Voix des dialogues", "Muted"), 1, 0)
        g.addWidget(self.dialogue, 1, 1)
        g.addWidget(IconButton("play", "Écouter", 34, 14, color=theme.CURRENT.accent), 1, 2)
        g.itemAtPosition(0, 2).widget().clicked.connect(lambda: self._preview(self.narrator))
        g.itemAtPosition(1, 2).widget().clicked.connect(lambda: self._preview(self.dialogue))
        g.setColumnStretch(1, 1)
        main.add(g)
        main.add(self.detect)
        main.add(self.incises)
        lay.addWidget(main)

        roles = Card()
        rt = QHBoxLayout()
        rt.addWidget(card_title("Personnages", "Dans le manuscrit, écrivez « @Nom: réplique » ou encadrez un passage "
                                "par « [voix:Nom] … [/voix] ».", "users"), 1)
        det = button("Détecter dans le texte", "search")
        det.clicked.connect(self._detect)
        addb = button("Ajouter", "plus")
        addb.clicked.connect(self._add_role)
        rt.addWidget(det)
        rt.addWidget(addb)
        roles.add(rt)
        self.roles_box = QVBoxLayout()
        self.roles_box.setSpacing(8)
        roles.add(self.roles_box)
        lay.addWidget(roles)
        lay.addStretch(1)
        self._loading = False

    def _fill_combo(self, combo: QComboBox, current: str, first: str | None) -> None:
        combo.blockSignals(True)
        combo.clear()
        if first:
            combo.addItem(first, "")
        for v in self.ctx.library.all():
            combo.addItem(icons.icon("mic" if v.is_clone else "user", v.color, 16), v.name, v.id)
        combo.setCurrentIndex(max(0, combo.findData(current)))
        combo.blockSignals(False)

    def reload(self) -> None:
        pr = self.ctx.project
        self._loading = True
        self._fill_combo(self.narrator, pr.narrator_voice_id, None)
        self._fill_combo(self.dialogue, pr.production.dialogue_voice_id, "Comme le narrateur")
        self.detect.setChecked(pr.production.detect_dialogues)
        self.incises.setChecked(pr.production.narrator_reads_incises)
        self._loading = False
        while self.roles_box.count():
            it = self.roles_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not pr.cast:
            self.roles_box.addWidget(label("Aucun personnage pour l'instant.", "Hint"))
        for name, vid in sorted(pr.cast.items()):
            row = QFrame()
            row.setObjectName("CardFlat")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.addWidget(Avatar(name, COLORS[sum(map(ord, name)) % len(COLORS)], 32))
            n = label(name)
            n.setStyleSheet("font-weight: 700;")
            rl.addWidget(n, 1)
            combo = QComboBox()
            combo.setMinimumWidth(260)
            self._fill_combo(combo, vid, "Comme le narrateur")
            combo.currentIndexChanged.connect(lambda _i, name=name, combo=combo: self._set_role(name, combo))
            rl.addWidget(combo)
            pb = IconButton("play", "Écouter", 32, 14, color=theme.CURRENT.accent)
            pb.clicked.connect(lambda _=False, combo=combo: self._preview(combo))
            rl.addWidget(pb)
            rm = IconButton("trash", "Retirer", 32, 15, color=theme.CURRENT.danger)
            rm.clicked.connect(lambda _=False, name=name: self._remove_role(name))
            rl.addWidget(rm)
            self.roles_box.addWidget(row)

    def _changed(self, *_a) -> None:
        if self._loading:
            return
        pr = self.ctx.project
        pr.narrator_voice_id = self.narrator.currentData() or pr.narrator_voice_id
        pr.production.dialogue_voice_id = self.dialogue.currentData() or ""
        pr.production.detect_dialogues = self.detect.isChecked()
        pr.production.narrator_reads_incises = self.incises.isChecked()
        self.ctx.mark_dirty()

    def _preview(self, combo: QComboBox) -> None:
        vid = combo.currentData() or self.ctx.project.narrator_voice_id
        v = self.ctx.library.get(vid)
        if v is not None:
            self.ctx.preview_voice(v)

    def _set_role(self, name: str, combo: QComboBox) -> None:
        self.ctx.project.cast[name] = combo.currentData() or ""
        self.ctx.mark_dirty()

    def _remove_role(self, name: str) -> None:
        self.ctx.project.cast.pop(name, None)
        self.ctx.mark_dirty()
        self.reload()

    def _add_role(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Nouveau personnage", "Nom du personnage :")
        if ok and name.strip():
            self.ctx.project.cast.setdefault(name.strip(), "")
            self.ctx.mark_dirty()
            self.reload()

    def _detect(self) -> None:
        found = []
        for ch in self.ctx.project.chapters:
            for n in find_characters(ch.text):
                if n not in self.ctx.project.cast and n not in found:
                    found.append(n)
        for n in found:
            self.ctx.project.cast[n] = ""
        if found:
            self.ctx.mark_dirty()
            self.reload()
        self.ctx.toast(f"{len(found)} personnage(s) trouvé(s)." if found else
                       "Aucun nouveau personnage balisé (@Nom:) dans le manuscrit.", "info")


class VoicesPage(Page):
    name = "voices"

    def __init__(self, ctx):
        super().__init__(ctx, "Voix & clonage", "Choisissez des voix gratuites, clonez la vôtre en quelques "
                         "secondes et distribuez les rôles.")
        imp = button("Importer une voix", "upload", tooltip=f"Fichier {VOICE_PACK_EXT} partagé")
        imp.clicked.connect(self._import_pack)
        clone = button("Cloner une voix", "mic", "primary")
        clone.clicked.connect(self.open_clone_wizard)
        rvc = button("Modèle .pth", "upload", tooltip="Importer un modèle de voix RVC (.pth + .index)")
        rvc.clicked.connect(self.import_rvc)
        self.header.add_action(imp)
        self.header.add_action(rvc)
        self.header.add_action(clone)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.body.addWidget(self.tabs, 1)

        lib = QWidget()
        ll = QHBoxLayout(lib)
        ll.setContentsMargins(0, 10, 0, 0)
        ll.setSpacing(18)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.grid_host)
        ll.addWidget(self.scroll, 1)
        self.editor = VoiceEditor(self)
        ed_scroll = QScrollArea()
        ed_scroll.setWidgetResizable(True)
        ed_scroll.setFrameShape(QFrame.NoFrame)
        ed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ed_scroll.setWidget(self.editor)
        ed_scroll.setFixedWidth(450)
        ll.addWidget(ed_scroll)
        self.tabs.addTab(lib, icons.icon("mic", theme.CURRENT.text, 16), "Ma bibliothèque")

        self.catalog = CatalogTab(self)
        self.tabs.addTab(self.catalog, icons.icon("globe", theme.CURRENT.text, 16), "Catalogue de voix")
        self.cast = CastTab(self)
        self.tabs.addTab(self.cast, icons.icon("users", theme.CURRENT.text, 16), "Distribution des rôles")
        self.tabs.currentChanged.connect(self._tab_changed)
        self._cards: dict[str, VoiceCard] = {}
        self._selected: str | None = None
        self._catalog_loaded = False
        ctx.voices_changed.connect(lambda: self.refresh_library(keep=self._selected))

    def on_show(self) -> None:
        self.refresh_library(keep=self._selected)
        self.cast.reload()

    def on_project_changed(self) -> None:
        self.cast.reload()

    def show_cast(self) -> None:
        self.tabs.setCurrentWidget(self.cast)

    def _tab_changed(self, i: int) -> None:
        if self.tabs.widget(i) is self.catalog and not self._catalog_loaded:
            self._catalog_loaded = True
            self.catalog.reload()
        elif self.tabs.widget(i) is self.cast:
            self.cast.reload()

    def refresh_library(self, keep: str | None = None) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._cards.clear()
        voices = self.ctx.library.all()
        if not voices:
            self.grid.addWidget(EmptyState("mic", "Aucune voix", "Clonez votre voix ou ajoutez-en une depuis le "
                                           "catalogue."), 0, 0)
        cols = 2 if self.width() < 1500 else 3
        narr = self.ctx.project.narrator_voice_id
        for i, v in enumerate(voices):
            card = VoiceCard(v, v.id == narr)
            card.clicked.connect(self.select)
            card.play.connect(self._play)
            card.star.connect(self._star)
            self._cards[v.id] = card
            self.grid.addWidget(card, i // cols, i % cols)
        target = keep if keep in self._cards else (voices[0].id if voices else None)
        self.select(target)

    def select(self, voice_id: str | None) -> None:
        self._selected = voice_id
        for vid, c in self._cards.items():
            c.set_selected(vid == voice_id)
        self.editor.set_voice(self.ctx.library.get(voice_id) if voice_id else None)

    def _play(self, voice_id: str) -> None:
        v = self.ctx.library.get(voice_id)
        if v is not None:
            self.ctx.preview_voice(v)

    def _star(self, voice_id: str) -> None:
        v = self.ctx.library.get(voice_id)
        if v is not None:
            v.favorite = not v.favorite
            self.ctx.library.save(v)
            self.refresh_library(keep=voice_id)

    def _import_pack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer une voix", "", f"Voix AudioLivre (*{VOICE_PACK_EXT})")
        if not path:
            return
        try:
            v = self.ctx.library.import_pack(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Import impossible", str(exc))
            return
        self.ctx.toast(f"Voix « {v.name} » importée.", "success")
        self.refresh_library(keep=v.id)
        self.ctx.voices_changed.emit()

    def import_rvc(self) -> None:
        from ..dialogs.rvc_import import RVCImportDialog

        dlg = RVCImportDialog(self.ctx, self)
        if dlg.exec() and dlg.voice is not None:
            self.tabs.setCurrentIndex(0)
            self.refresh_library(keep=dlg.voice.id)
            self.ctx.voices_changed.emit()

    def open_clone_wizard(self) -> None:
        from ..dialogs.clone_wizard import CloneWizard

        dlg = CloneWizard(self.ctx, self)
        if dlg.exec() and dlg.voice is not None:
            self.tabs.setCurrentIndex(0)
            self.refresh_library(keep=dlg.voice.id)
            self.ctx.voices_changed.emit()
