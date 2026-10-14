"""Page Langues et voix : langue apprise et accent, langue d'explication, voix natives de chaque langue."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem)

from ...core import course, languages, textproc
from ...core.models import LEVEL_LABELS, LEVELS
from .. import icons, tasks, theme
from ..dialogs.new_course import fill_locales, language_combo
from ..widgets import Card, IconButton, button, card_title, label
from .base import Page

OFFLINE_MODES = {
    "fallback": "Voix Microsoft (en ligne), voix hors ligne si le service ne répond pas",
    "prefer": "Voix hors ligne d'abord quand la langue en a (Kokoro, XTTS), sinon Microsoft",
    "none": "Uniquement les voix Microsoft",
}


class LanguagesPage(Page):
    name = "languages"

    def __init__(self, ctx):
        super().__init__(ctx, "Langues et voix", "Choisissez la langue apprise, son accent et les voix natives qui "
                         "la parlent. Les passages balisés dans une autre langue ont aussi leur voix native.",
                         scroll=True)
        self._loading = False
        refresh = button("Actualiser la liste Microsoft", "refresh", tooltip="Télécharge la liste à jour des voix "
                         "Microsoft gratuites (plus de 300 voix)")
        refresh.clicked.connect(self.refresh_edge)
        self.header.add_action(refresh)

        # ---- langues du cours
        c1 = Card()
        c1.add(card_title("Langues du cours", "La langue d'explication lit les consignes, traductions et "
                          "explications ; la langue apprise est lue par des voix natives.", "globe"))
        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(label("Langue apprise", "Muted"))
        self.target = language_combo("en")
        self.target.setMinimumWidth(260)
        self.target.currentIndexChanged.connect(self._target_changed)
        r1.addWidget(self.target, 1)
        r1.addWidget(label("Accent", "Muted"))
        self.locale = QComboBox()
        self.locale.setMinimumWidth(200)
        self.locale.currentIndexChanged.connect(self._meta_changed)
        r1.addWidget(self.locale, 1)
        c1.add(r1)
        r2 = QHBoxLayout()
        r2.setSpacing(10)
        r2.addWidget(label("Expliquée en", "Muted"))
        self.explain = language_combo("fr")
        self.explain.setMinimumWidth(260)
        self.explain.currentIndexChanged.connect(self._meta_changed)
        r2.addWidget(self.explain, 1)
        r2.addWidget(label("Niveau", "Muted"))
        self.level = QComboBox()
        for lv in LEVELS:
            self.level.addItem(LEVEL_LABELS[lv], lv)
        self.level.currentIndexChanged.connect(self._meta_changed)
        r2.addWidget(self.level, 1)
        c1.add(r2)
        self.instr = label("", "Hint", wrap=True)
        c1.add(self.instr)
        self.instr_btn = button("Traduire les consignes avec l'IA", "sparkles", tooltip="« Écoutez puis répétez », "
                                "« Comment dit-on… » : consignes lues dans la langue d'explication")
        self.instr_btn.clicked.connect(self.ai_instructions)
        c1.add(self.instr_btn)
        self.body.addWidget(c1)

        # ---- voix natives
        c2 = Card()
        c2.add(card_title("Voix natives", "Cochez les voix à utiliser, dans l'ordre de préférence : la première lit "
                          "les mots et les phrases, les suivantes donnent leur voix aux personnages des dialogues "
                          "(en alternant femmes et hommes). Sans choix, les voix sont choisies automatiquement.",
                          "users"))
        r3 = QHBoxLayout()
        r3.addWidget(label("Langue", "Muted"))
        self.voice_lang = QComboBox()
        self.voice_lang.setMinimumWidth(280)
        self.voice_lang.currentIndexChanged.connect(self._fill_voices)
        r3.addWidget(self.voice_lang, 1)
        self.gender = QComboBox()
        for key, text in (("", "Femmes et hommes"), ("F", "Voix de femmes"), ("M", "Voix d'hommes")):
            self.gender.addItem(text, key)
        self.gender.currentIndexChanged.connect(self._fill_voices)
        r3.addWidget(self.gender)
        c2.add(r3)
        self.voices = QListWidget()
        self.voices.setMinimumHeight(260)
        self.voices.itemChanged.connect(self._voices_changed)
        self.voices.itemDoubleClicked.connect(lambda it: self._preview(it))
        c2.add(self.voices)
        r4 = QHBoxLayout()
        play = button("Écouter", "headphones", "primary")
        play.clicked.connect(lambda: self._preview(self.voices.currentItem()))
        up = IconButton("up", "Monter (préférée)", 34, 16)
        up.clicked.connect(lambda: self._move(-1))
        down = IconButton("down", "Descendre", 34, 16)
        down.clicked.connect(lambda: self._move(1))
        reset = button("Choix automatique", "refresh", tooltip="Oublier les voix cochées pour cette langue")
        reset.clicked.connect(self._reset)
        keep = button("Ajouter à mes voix", "plus", tooltip="Copie la voix dans la bibliothèque (page Voix) pour la "
                      "régler ou l'utiliser comme voix d'explication")
        keep.clicked.connect(self._keep)
        for w in (play, up, down, reset, keep):
            r4.addWidget(w)
        r4.addStretch(1)
        c2.add(r4)
        self.voice_info = label("", "Faint", wrap=True)
        c2.add(self.voice_info)
        self.body.addWidget(c2)

        # ---- voix hors ligne
        c3 = Card()
        c3.add(card_title("Sans connexion Internet", "Les voix Microsoft sont gratuites mais en ligne. Kokoro (léger, "
                          "8 langues) et XTTS-v2 (17 langues) fonctionnent hors ligne, sans carte NVIDIA : "
                          "installez-les dans Moteurs IA.", "zap"))
        r5 = QHBoxLayout()
        self.offline = QComboBox()
        for key, text in OFFLINE_MODES.items():
            self.offline.addItem(text, key)
        self.offline.currentIndexChanged.connect(self._offline_changed)
        r5.addWidget(self.offline, 1)
        eng = button("Moteurs IA", "cpu")
        eng.clicked.connect(lambda: self.ctx.navigate("engines"))
        r5.addWidget(eng)
        c3.add(r5)
        self.offline_info = label("", "Hint", wrap=True)
        c3.add(self.offline_info)
        self.body.addWidget(c3)

        # ---- catalogue
        c4 = Card()
        c4.add(card_title("Toutes les langues", "Recherchez une langue pour voir ses accents, ses voix et sa "
                          "prononciation écrite.", "list"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher : japonais, swahili, hindi…")
        self.search.textChanged.connect(self._fill_catalog)
        c4.add(self.search)
        self.catalog = QTableWidget(0, 6)
        self.catalog.setHorizontalHeaderLabels(["Langue", "Nom natif", "Balise", "Accents", "Voix Microsoft",
                                                "Hors ligne"])
        self.catalog.verticalHeader().setVisible(False)
        self.catalog.setEditTriggers(QTableWidget.NoEditTriggers)
        self.catalog.setSelectionBehavior(QTableWidget.SelectRows)
        self.catalog.setMinimumHeight(320)
        for c in range(6):
            self.catalog.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch if c in (0, 1, 3)
                                                                 else QHeaderView.ResizeToContents)
        self.catalog.cellDoubleClicked.connect(self._catalog_pick)
        c4.add(self.catalog)
        c4.add(label("Double-cliquez sur une langue pour voir et écouter ses voix ci-dessus.", "Faint"))
        self.body.addWidget(c4)
        self.body.addStretch(1)
        ctx.voices_changed.connect(self._fill_voices)
        ctx.engines_changed.connect(self._update_offline_info)

    # -- synchronisation ---------------------------------------------------------------
    def on_project_changed(self) -> None:
        self.voice_lang.clear()  # nouvelle liste : la langue apprise du projet est sélectionnée
        self.reload()

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        pr = self.ctx.project
        m = pr.metadata
        self._loading = True
        self.target.setCurrentIndex(max(0, self.target.findData(languages.get(m.target_language).code
                                                                 if languages.get(m.target_language) else "en")))
        fill_locales(self.locale, m.target_language, m.target_locale)
        self.explain.setCurrentIndex(max(0, self.explain.findData(course.explain_code(pr))))
        self.level.setCurrentIndex(max(0, self.level.findData(m.level)))
        self.offline.setCurrentIndex(max(0, self.offline.findData(pr.production.native_offline)))
        self._fill_voice_langs()
        self._loading = False
        self._update_instr()
        self._fill_voices()
        self._update_offline_info()
        if self.catalog.rowCount() == 0:
            self._fill_catalog()

    def project_languages(self) -> list[str]:
        """Langues utilisées : langue apprise du cours, des leçons, des intervenants et des balises."""
        pr = self.ctx.project
        out = [pr.metadata.target_language]
        for ch in pr.chapters:
            out.append(pr.target_of(ch)[0])
            out += [languages.get(t).code for t in textproc.languages_in(ch.text) if languages.get(t)]
        out += [h.language for h in pr.hosts if h.language]
        out.append(course.explain_code(pr))
        return [c for c in dict.fromkeys(out) if languages.get(c)]

    def _fill_voice_langs(self, select: str = "") -> None:
        current = select or self.voice_lang.currentData() or self.ctx.project.metadata.target_language
        self.voice_lang.blockSignals(True)
        self.voice_lang.clear()
        used = self.project_languages()
        for code in used:
            tag = " (langue apprise)" if code == self.ctx.project.metadata.target_language else \
                " (explication)" if code == course.explain_code(self.ctx.project) else ""
            self.voice_lang.addItem(icons.icon("globe", theme.CURRENT.accent2 if tag else theme.CURRENT.muted, 16),
                                    languages.language_name(code, True) + tag, code)
        for lang in languages.sorted_languages():
            if lang.code not in used:
                self.voice_lang.addItem(lang.name, lang.code)
        self.voice_lang.setCurrentIndex(max(0, self.voice_lang.findData(current)))
        self.voice_lang.blockSignals(False)

    # -- langues du cours --------------------------------------------------------------
    def _target_changed(self, *_a) -> None:
        if self._loading:
            return
        code = self.target.currentData() or "en"
        fill_locales(self.locale, code)
        self._meta_changed()
        self._fill_voice_langs(code)
        self._fill_voices()

    def _meta_changed(self, *_a) -> None:
        if self._loading:
            return
        m = self.ctx.project.metadata
        m.target_language = self.target.currentData() or "en"
        m.target_locale = self.locale.currentData() or ""
        new_explain = self.explain.currentData() or "fr"
        if new_explain != course.explain_code(self.ctx.project):
            self.ctx.project.instructions = {}  # consignes traduites pour l'ancienne langue
        m.language = new_explain
        m.level = self.level.currentData() or "A1"
        self.ctx.mark_dirty()
        self._update_instr()
        if self.voice_lang.currentData() == m.target_language:
            self._fill_voices()

    def _update_instr(self) -> None:
        pr = self.ctx.project
        code = course.explain_code(pr)
        builtin = course.has_builtin_instructions(code)
        translated = bool(pr.instructions)
        if builtin:
            self.instr.setText(f"Consignes lues en {languages.language_name(code).lower()} (intégrées).")
        elif translated:
            self.instr.setText(f"Consignes lues en {languages.language_name(code).lower()} (traduites par l'IA).")
        else:
            self.instr.setText(f"Les consignes intégrées existent en français, anglais, espagnol, allemand, italien, "
                               f"portugais et néerlandais : pour le {languages.language_name(code).lower()}, elles "
                               "seront lues en anglais tant qu'elles ne sont pas traduites.")
        self.instr_btn.setVisible(not builtin)

    def ai_instructions(self) -> None:
        from ...core import ai, lang_ai

        pr = self.ctx.project
        code = course.explain_code(pr)

        def work():
            return lang_ai.translate_instructions(ai.client_from_settings(), code)

        def done(tr):
            pr.instructions = tr
            self.ctx.mark_dirty()
            self._update_instr()
            self.ctx.toast("Consignes traduites.", "success")

        self.ctx.toast("DeepSeek traduit les consignes…", "info", 2500)
        self._task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 7000))

    # -- voix natives ------------------------------------------------------------------
    def _resolver(self):
        from ...core import renderer

        return renderer.VoiceResolver(self.ctx.project, self.ctx.library)

    def _fill_voices(self, *_a) -> None:
        if self._loading:
            return
        pr = self.ctx.project
        code = self.voice_lang.currentData() or pr.metadata.target_language
        locale = pr.metadata.target_locale if code == pr.metadata.target_language else ""
        gender = self.gender.currentData() or ""
        res = self._resolver()
        chosen = [v for v in pr.language_voices.get(code, [])]
        auto = languages.native_voices(code, locale, gender, res.edge_available(), "fallback", None)
        ids = chosen + [nv.id for nv in auto if nv.id not in chosen]
        self.voices.blockSignals(True)
        self.voices.clear()
        installed = res.installed()
        for vid in ids:
            v = self.ctx.library.get(vid)
            nv = languages.parse_native_id(vid)
            if v is None:
                continue
            if gender and v.gender and v.gender != gender:
                continue
            g = {"F": "femme", "M": "homme"}.get(v.gender, "")
            extra = []
            if nv is not None and nv.offline:
                extra.append("hors ligne" + ("" if nv.engine in installed else " — moteur à installer"))
            if nv is not None and nv.multilingual:
                extra.append("multilingue")
            text = f"{v.name}" + (f" · {g}" if g else "") + (f" · {', '.join(extra)}" if extra else "")
            it = QListWidgetItem(icons.icon("user", v.color, 16), text)
            it.setData(Qt.UserRole, vid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if vid in chosen else Qt.Unchecked)
            self.voices.addItem(it)
        self.voices.blockSignals(False)
        main = res.native_ids(code, locale)
        first = self.ctx.library.get(main[0]) if main else None
        self.voice_info.setText(f"{self.voices.count()} voix proposées. Voix utilisée pour les mots et phrases : "
                                f"{first.name if first else '—'}"
                                + ("" if chosen else " (choix automatique)") + ".")

    def _voices_changed(self, *_a) -> None:
        code = self.voice_lang.currentData()
        if not code:
            return
        checked = [self.voices.item(i).data(Qt.UserRole) for i in range(self.voices.count())
                   if self.voices.item(i).checkState() == Qt.Checked]
        pr = self.ctx.project
        if checked:
            pr.language_voices[code] = checked
        else:
            pr.language_voices.pop(code, None)
        self.ctx.mark_dirty()
        self._fill_voices()

    def _move(self, delta: int) -> None:
        r = self.voices.currentRow()
        code = self.voice_lang.currentData()
        it = self.voices.currentItem()
        if it is None or not code:
            return
        vid = it.data(Qt.UserRole)
        chosen = self.ctx.project.language_voices.setdefault(code, [])
        if vid not in chosen:
            chosen.append(vid)
        i = chosen.index(vid)
        j = max(0, min(len(chosen) - 1, i + delta))
        chosen[i], chosen[j] = chosen[j], chosen[i]
        self.ctx.mark_dirty()
        self._fill_voices()
        self.voices.setCurrentRow(max(0, min(self.voices.count() - 1, r + delta)))

    def _reset(self) -> None:
        code = self.voice_lang.currentData()
        if code and self.ctx.project.language_voices.pop(code, None) is not None:
            self.ctx.mark_dirty()
        self._fill_voices()

    def _preview(self, it) -> None:
        if it is None:
            self.ctx.toast("Sélectionnez une voix.", "info")
            return
        v = self.ctx.library.get(it.data(Qt.UserRole))
        if v is not None:
            code = self.voice_lang.currentData() or v.language
            self.ctx.preview_voice(v, languages.sample_sentence(code) or None, language=code)

    def _keep(self) -> None:
        it = self.voices.currentItem()
        if it is None:
            return
        v = self.ctx.library.save_native(it.data(Qt.UserRole))
        if v is not None:
            self.ctx.voices_changed.emit()
            self.ctx.toast(f"« {v.name} » ajoutée à vos voix.", "success")

    # -- hors ligne --------------------------------------------------------------------
    def _offline_changed(self, *_a) -> None:
        if self._loading:
            return
        self.ctx.project.production.native_offline = self.offline.currentData() or "fallback"
        self.ctx.mark_dirty()
        self._update_offline_info()

    def _update_offline_info(self) -> None:
        installed = self._resolver().installed()
        parts = [f"Kokoro : {'installé' if 'kokoro' in installed else 'non installé'} (anglais, espagnol, français, "
                 "hindi, italien, japonais, portugais, chinois)",
                 f"XTTS-v2 : {'installé' if 'xtts' in installed else 'non installé'} (17 langues)"]
        self.offline_info.setText(" · ".join(parts))

    def refresh_edge(self) -> None:
        from ...core import engines

        eng = engines.get_engine("edge")

        def work():
            return len(eng.list_builtin_voices(refresh=True))

        def done(n):
            self.ctx.toast(f"{n} voix Microsoft disponibles.", "success")
            self._fill_catalog()
            self._fill_voices()

        self._task = tasks.run(work, on_done=done, on_error=lambda m, _t: self.ctx.toast(m, "error", 6000))

    # -- catalogue ---------------------------------------------------------------------
    def _fill_catalog(self, *_a) -> None:
        q = self.search.text().strip().lower()
        live = self._resolver().edge_available()
        rows = []
        for lang in languages.sorted_languages():
            hay = f"{lang.name} {lang.native} {lang.code} " + " ".join(f"{loc} {lbl}" for loc, lbl in lang.locales)
            if q and q not in hay.lower():
                continue
            n = len(languages.edge_voices_for(lang.code, "", live))
            off = ", ".join(e for e, ok in (("Kokoro", bool(languages.kokoro_voices_for(lang.code))),
                                            ("XTTS", lang.code in languages.XTTS_LANGS)) if ok)
            rows.append((lang, n, off))
        self.catalog.setRowCount(len(rows))
        for r, (lang, n, off) in enumerate(rows):
            vals = [lang.name, lang.native, f"[{lang.code}]", ", ".join(lbl for _l, lbl in lang.locales),
                    str(n), off or "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(Qt.UserRole, lang.code)
                self.catalog.setItem(r, c, it)

    def _catalog_pick(self, row: int, _col: int) -> None:
        cell = self.catalog.item(row, 0)
        if cell is None:
            return
        code = cell.data(Qt.UserRole)
        idx = self.voice_lang.findData(code)
        if idx >= 0:
            self.voice_lang.setCurrentIndex(idx)
