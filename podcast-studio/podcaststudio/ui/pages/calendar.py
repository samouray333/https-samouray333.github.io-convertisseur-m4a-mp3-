"""Page Calendrier : dates de publication des épisodes, planification de la saison, suivi de l'avancement."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import (QAbstractItemView, QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QHBoxLayout,
                               QHeaderView, QTableWidget, QTableWidgetItem, QWidget)

from ...core import renderer, schedule
from .. import theme
from ..widgets import Card, button, card_title, label
from .base import Page

STATUS_KIND = {"À écrire": "faint", "Écrit": "warning", "Produit": "info", "Publié": "success"}


class CalendarPage(Page):
    name = "calendar"

    def __init__(self, ctx):
        super().__init__(ctx, "Calendrier", "Planifiez la publication de vos épisodes et suivez l'avancement de la "
                         "saison. Les dates sont inscrites dans le flux RSS.", scroll=True)
        self._loading = False
        self.summary = label("", "Muted", wrap=True)
        self.body.addWidget(self.summary)

        row = QHBoxLayout()
        row.setSpacing(18)
        cal_card = Card()
        cal_card.add(card_title("Vue d'ensemble", "Les jours de publication sont colorés ; cliquez sur un jour pour "
                                "retrouver l'épisode.", "clock"))
        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.cal.setMinimumHeight(300)
        self.cal.clicked.connect(self._day_clicked)
        cal_card.add(self.cal)
        row.addWidget(cal_card, 2)

        plan = Card()
        plan.add(card_title("Planifier la saison", "Donne une date à chaque épisode, à intervalle régulier, dans "
                            "l'ordre de la liste.", "sparkles"))
        self.start = QDateEdit()
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("dddd dd/MM/yyyy")
        self.start.setDate(QDate.currentDate().addDays(1))
        self.every = QComboBox()
        for key, text in schedule.FREQUENCIES.items():
            self.every.addItem(text, key)
        self.only_missing = QCheckBox("Seulement les épisodes sans date")
        self.only_missing.setChecked(True)
        go = button("Planifier", "clock", "primary")
        go.clicked.connect(self.plan)
        for title, w in (("Premier épisode le", self.start), ("Rythme", self.every)):
            plan.add(label(title, "Muted"))
            plan.add(w)
        plan.add(self.only_missing)
        plan.add(go)
        plan.add(None)
        row.addWidget(plan, 1)
        self.body.addLayout(row)

        tc = Card()
        tc.add(card_title("Épisodes", "Modifiez une date directement ; cochez « Publié » une fois l'épisode en ligne.",
                          "list"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["N°", "Épisode", "Date de publication", "État", "Publié"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(300)
        self.table.cellDoubleClicked.connect(self._open_episode)
        tc.add(self.table)
        self.body.addWidget(tc)
        self.body.addStretch(1)

    # -- affichage ---------------------------------------------------------------------
    def on_project_changed(self) -> None:
        self.reload()

    def on_show(self) -> None:
        self.reload()

    def _produced(self) -> dict[str, bool]:
        pr = self.ctx.project
        try:
            plan = renderer.build_plan(pr, self.ctx.library, include_credits=False)
        except Exception:
            return {}
        return {rc.id: renderer.chapter_is_current(pr, rc) for rc in plan}

    def reload(self) -> None:
        pr = self.ctx.project
        produced = self._produced()
        self._loading = True
        self.table.setRowCount(0)
        p = theme.CURRENT
        for ch in pr.chapters:
            r = self.table.rowCount()
            self.table.insertRow(r)
            kind = {"trailer": "Bande-annonce", "bonus": "Bonus"}.get(ch.episode_type, str(pr.episode_number(ch)))
            for c, text in ((0, kind), (1, ch.title)):
                it = QTableWidgetItem(text)
                it.setData(Qt.UserRole, ch.id)
                if not ch.include:
                    it.setForeground(QColor(p.faint))
                self.table.setItem(r, c, it)
            de = QDateEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("ddd dd/MM/yyyy")
            de.setMinimumDate(QDate(2000, 1, 1))
            de.setSpecialValueText("non planifié")
            d = schedule.parse(ch.pub_date)
            de.setDate(QDate(d.year, d.month, d.day) if d else de.minimumDate())
            de.dateChanged.connect(lambda qd, ch=ch, de=de: self._date_changed(ch, qd, de))
            self.table.setCellWidget(r, 2, de)
            st = schedule.status(ch, produced.get(ch.id, False))
            sit = QTableWidgetItem(st)
            sit.setForeground(QColor(getattr(p, STATUS_KIND[st], p.text)))
            self.table.setItem(r, 3, sit)
            box = QCheckBox()
            box.setChecked(ch.published)
            box.toggled.connect(lambda on, ch=ch: self._published(ch, on))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(10, 0, 10, 0)
            hl.addWidget(box)
            self.table.setCellWidget(r, 4, holder)
        self._loading = False
        self._paint_calendar()
        self._update_summary(produced)

    def _paint_calendar(self) -> None:
        self.cal.setDateTextFormat(QDate(), QTextCharFormat())  # efface les anciennes couleurs
        p = theme.CURRENT
        for ch in self.ctx.project.chapters:
            d = schedule.parse(ch.pub_date)
            if not d or not ch.include:
                continue
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(QColor(p.success if ch.published else p.accent)))
            fmt.setForeground(QBrush(QColor("#FFFFFF")))
            fmt.setToolTip(ch.title)
            self.cal.setDateTextFormat(QDate(d.year, d.month, d.day), fmt)

    def _update_summary(self, produced: dict[str, bool]) -> None:
        eps = [c for c in self.ctx.project.included_chapters()]
        if not eps:
            self.summary.setText("Aucun épisode pour l'instant.")
            return
        counts: dict[str, int] = {}
        for c in eps:
            st = schedule.status(c, produced.get(c.id, False))
            counts[st] = counts.get(st, 0) + 1
        nxt = schedule.next_episode(eps)
        parts = [f"{len(eps)} épisodes"] + [f"{n} {k.lower()}{'s' if n > 1 and not k.endswith('e') else ''}"
                                             for k, n in counts.items()]
        dated = sum(1 for c in eps if schedule.parse(c.pub_date))
        parts.append(f"{dated} planifiés")
        if nxt is not None:
            d = schedule.parse(nxt.pub_date)
            parts.append(f"prochain : « {nxt.title} » le {d.strftime('%d/%m/%Y')}")
        self.summary.setText(" · ".join(parts))

    # -- actions -----------------------------------------------------------------------
    def _date_changed(self, ch, qd: QDate, de: QDateEdit) -> None:
        if self._loading:
            return
        ch.pub_date = "" if qd == de.minimumDate() else qd.toString("yyyy-MM-dd")
        self.ctx.mark_dirty()
        self._paint_calendar()
        self._update_summary(self._produced())

    def _published(self, ch, on: bool) -> None:
        if self._loading:
            return
        ch.published = on
        if on and not ch.pub_date:
            ch.pub_date = date.today().isoformat()
        self.ctx.mark_dirty()
        self.reload()

    def plan(self) -> None:
        qd = self.start.date()
        n = schedule.plan_dates(self.ctx.project.chapters, date(qd.year(), qd.month(), qd.day()),
                                self.every.currentData(), self.only_missing.isChecked())
        if n:
            self.ctx.mark_dirty()
            self.ctx.toast(f"{n} épisode(s) planifié(s).", "success")
        else:
            self.ctx.toast("Tous les épisodes ont déjà une date (décochez « Seulement les épisodes sans date » pour "
                           "tout replanifier).", "info", 6000)
        self.reload()

    def _day_clicked(self, qd: QDate) -> None:
        iso = qd.toString("yyyy-MM-dd")
        for r in range(self.table.rowCount()):
            ch = self.ctx.project.chapter_by_id(self.table.item(r, 1).data(Qt.UserRole))
            if ch is not None and ch.pub_date == iso:
                self.table.selectRow(r)
                return

    def _open_episode(self, row: int, _col: int) -> None:
        cid = self.table.item(row, 1).data(Qt.UserRole)
        page = self.ctx.window.pages.get("manuscript")
        self.ctx.navigate("manuscript")
        if page is not None:
            for i in range(page.list.count()):
                if page.list.item(i).data(Qt.UserRole) == cid:
                    page.list.setCurrentRow(i)
                    break
