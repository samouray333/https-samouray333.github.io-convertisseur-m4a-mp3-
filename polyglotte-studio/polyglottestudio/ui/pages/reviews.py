"""Page Révisions : répétition espacée (J+1, J+3, J+7, J+14, J+30), calendrier, séances audio de révision."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import (QAbstractItemView, QCalendarWidget, QHBoxLayout, QHeaderView, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem)

from ...core import renderer, srs
from ...core.models import REVIEW_STEPS
from .. import icons, tasks, theme
from ..widgets import Card, StatTile, button, card_title, label
from .base import Page


def _qdate(day: dt.date) -> QDate:
    return QDate(day.year, day.month, day.day)


def _pydate(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


class ReviewsPage(Page):
    name = "reviews"

    def __init__(self, ctx):
        super().__init__(ctx, "Révisions", "Chaque mot étudié revient à J+1, J+3, J+7, J+14 puis J+30. Écoutez la "
                         "séance du jour : le mot en français, un silence pour le dire, puis la bonne réponse.",
                         scroll=True)
        self._task = None
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.t_due = StatTile("clock", "0", "à réviser aujourd'hui", theme.CURRENT.accent2)
        self.t_sched = StatTile("refresh", "0", "en cours de révision")
        self.t_learned = StatTile("award", "0", "mots acquis (J+30 passé)", theme.CURRENT.success)
        self.t_mastery = StatTile("star", "0 %", "maîtrise du cours", theme.CURRENT.accent2)
        self.t_lessons = StatTile("book", "0/0", "leçons étudiées")
        for t in (self.t_due, self.t_sched, self.t_learned, self.t_mastery, self.t_lessons):
            tiles.addWidget(t, 1)
        self.body.addLayout(tiles)

        row = QHBoxLayout()
        row.setSpacing(18)
        cal_card = Card()
        cal_card.add(card_title("Calendrier de révision", "Les jours dorés ont une séance prévue (en supposant que "
                                "chaque séance est faite à sa date). Cliquez sur un jour pour voir ses mots.", "clock"))
        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.cal.setMinimumHeight(300)
        self.cal.setMinimumDate(QDate.currentDate().addDays(-60))
        self.cal.clicked.connect(self._day_clicked)
        cal_card.add(self.cal)
        row.addWidget(cal_card, 2)

        day_card = Card()
        self.day_title = label("Aujourd'hui", "SectionTitle")
        day_card.add(self.day_title)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Raté", "Langue apprise", "Traduction", "Leçon", "Étape"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(260)
        day_card.add(self.table)
        br = QHBoxLayout()
        self.listen_btn = button("Écouter la séance", "headphones", "primary", tooltip="Produit et lit l'audio de "
                                 "révision de ce jour (voix d'explication et voix natives)")
        self.listen_btn.clicked.connect(self.listen_session)
        self.done_btn = button("Séance terminée", "check", tooltip="Les mots passent à l'étape suivante ; ceux cochés "
                               "« Raté » reviennent demain")
        self.done_btn.clicked.connect(self.complete)
        export = button("Exporter les séances", "download", tooltip="Un MP3 par séance des 30 prochains jours "
                        "(page Export, format « Révisions »)")
        export.clicked.connect(self._go_export)
        for w in (self.listen_btn, self.done_btn, export):
            br.addWidget(w)
        br.addStretch(1)
        day_card.add(br)
        self.day_hint = label("", "Hint", wrap=True)
        day_card.add(self.day_hint)
        row.addWidget(day_card, 3)
        self.body.addLayout(row)

        lessons = Card()
        lessons.add(card_title("Leçons étudiées", "Marquez une leçon comme étudiée le jour où vous l'avez écoutée : "
                               "ses mots et phrases entrent dans le calendrier.", "book"))
        self.lessons = QListWidget()
        self.lessons.setMinimumHeight(180)
        self.lessons.itemChanged.connect(self._lesson_toggled)
        lessons.add(self.lessons)
        self.body.addWidget(lessons)
        self.body.addStretch(1)
        self._day = srs.today()
        self._loading = False

    # -- affichage ---------------------------------------------------------------------
    def on_project_changed(self) -> None:
        self._day = srs.today()
        self.reload()

    def on_show(self) -> None:
        self.reload()

    def reload(self) -> None:
        pr = self.ctx.project
        srs.prune(pr)
        p = srs.progress(pr)
        self.t_due.set_value(str(p.due_today))
        self.t_sched.set_value(str(p.scheduled))
        self.t_learned.set_value(str(p.learned))
        self.t_mastery.set_value(f"{int(round(srs.mastery(pr) * 100))} %")
        self.t_lessons.set_value(f"{p.lessons_studied}/{p.lessons}")
        self._paint_calendar()
        self._fill_day()
        self._fill_lessons()

    def _paint_calendar(self) -> None:
        self.cal.setDateTextFormat(QDate(), QTextCharFormat())  # efface les couleurs précédentes
        today = srs.today()
        fc = srs.forecast(self.ctx.project, today, 60)
        gold = QColor(theme.CURRENT.accent2)
        for day, states in fc.items():
            f = QTextCharFormat()
            f.setBackground(QBrush(QColor(gold.red(), gold.green(), gold.blue(), 90 if day > today else 170)))
            f.setFontWeight(700)
            f.setToolTip(f"{len(states)} mot(s) à réviser")
            self.cal.setDateTextFormat(_qdate(day), f)
        self._forecast = fc

    def _states_for(self, day: dt.date):
        today = srs.today()
        if day <= today:
            return srs.due_items(self.ctx.project, day, include_overdue=day == today)
        return self._forecast.get(day, [])

    def _fill_day(self) -> None:
        pr = self.ctx.project
        day = self._day
        today = srs.today()
        states = self._states_for(day)
        pairs = srs.items_for(pr, states)
        name = "Aujourd'hui" if day == today else day.strftime("%d/%m/%Y")
        self.day_title.setText(f"{name} — {len(pairs)} mot(s) et phrase(s)")
        self.table.setRowCount(len(pairs))
        for r, ((ch, it), st) in enumerate(zip(pairs, states)):
            miss = QTableWidgetItem()
            miss.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            miss.setCheckState(Qt.Unchecked)
            miss.setData(Qt.UserRole, it.id)
            self.table.setItem(r, 0, miss)
            self.table.setItem(r, 1, QTableWidgetItem(it.term + (f"  ({it.translit})" if it.translit else "")))
            self.table.setItem(r, 2, QTableWidgetItem(it.translation))
            self.table.setItem(r, 3, QTableWidgetItem(ch.title))
            step = REVIEW_STEPS[min(st.step, len(REVIEW_STEPS) - 1)]
            self.table.setItem(r, 4, QTableWidgetItem(f"J+{step}"))
        self.done_btn.setEnabled(day == today and bool(pairs))
        self.listen_btn.setEnabled(bool(pairs))
        if not pr.reviews:
            self.day_hint.setText("Aucun mot en révision : marquez une leçon comme étudiée (ci-dessous, ou bouton "
                                  "« Étudiée » de la page Leçons).")
        elif day > today:
            self.day_hint.setText("Séance à venir : vous pouvez déjà l'écouter, elle sera notée faite le jour venu.")
        else:
            self.day_hint.setText("Écoutez la séance, cochez « Raté » pour les mots oubliés, puis « Séance terminée ».")

    def _fill_lessons(self) -> None:
        pr = self.ctx.project
        self._loading = True
        self.lessons.clear()
        for ch in pr.chapters:
            when = pr.studied.get(ch.id)
            text = f"{ch.title} — {len(ch.vocab)} mot(s) et phrase(s)" + (f" · étudiée le {when[8:10]}/{when[5:7]}"
                                                                         if when else "")
            it = QListWidgetItem(icons.icon("check" if when else "book", theme.CURRENT.success if when
                                            else theme.CURRENT.muted, 16), text)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if when else Qt.Unchecked)
            it.setData(Qt.UserRole, ch.id)
            self.lessons.addItem(it)
        self._loading = False

    # -- actions -----------------------------------------------------------------------
    def _day_clicked(self, qd: QDate) -> None:
        self._day = _pydate(qd)
        self._fill_day()

    def _lesson_toggled(self, it: QListWidgetItem) -> None:
        if self._loading:
            return
        pr = self.ctx.project
        ch = pr.chapter_by_id(it.data(Qt.UserRole))
        if ch is None:
            return
        if it.checkState() == Qt.Checked:
            n = srs.mark_studied(pr, ch)
            self.ctx.toast(f"« {ch.title} » : {n} élément(s) programmé(s), première révision demain.", "success")
        else:
            srs.unmark_studied(pr, ch)
        self.ctx.mark_dirty()
        self.reload()

    def failed_ids(self) -> set[str]:
        out = set()
        for r in range(self.table.rowCount()):
            cell = self.table.item(r, 0)
            if cell is not None and cell.checkState() == Qt.Checked:
                out.add(cell.data(Qt.UserRole))
        return out

    def complete(self) -> None:
        pr = self.ctx.project
        failed = self.failed_ids()
        n = srs.complete_session(pr, srs.today(), failed)
        self.ctx.mark_dirty()
        self.ctx.toast(f"Séance enregistrée : {n - len(failed)} réussi(s), {len(failed)} à revoir demain.", "success")
        self.reload()

    def listen_session(self) -> None:
        pr = self.ctx.project
        ch = srs.review_chapter(pr, self._day, self._states_for(self._day))
        if ch is None:
            return
        lib = self.ctx.library

        def work():
            rc = renderer.build_chapter_plan(pr, ch, lib, kind="review")
            rep = renderer.Renderer(pr, lib).render([rc])
            if rep.failed_segments:
                raise RuntimeError(rep.blocked or rep.failed_segments[0][2])
            return renderer.chapter_output(pr, rc.id)

        def done(path):
            self.listen_btn.setEnabled(True)
            self.ctx.play(path, ch.title)

        def fail(msg, _tb):
            self.listen_btn.setEnabled(True)
            self.ctx.toast(f"Séance non produite : {msg}", "error", 7000)

        self.listen_btn.setEnabled(False)
        self.ctx.toast("Préparation de la séance de révision…", "info", 3000)
        self._task = tasks.run(work, on_done=done, on_error=fail)

    def _go_export(self) -> None:
        if "reviews" not in self.ctx.project.export.formats:
            self.ctx.project.export.formats.append("reviews")
            self.ctx.mark_dirty()
        self.ctx.navigate("export")
