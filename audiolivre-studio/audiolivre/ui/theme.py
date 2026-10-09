"""Thème visuel : palettes sombre/claire et feuille de style Qt."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ACCENTS = {
    "Violet": "#7C5CFF",
    "Rose": "#FF4FA3",
    "Océan": "#2F9BFF",
    "Émeraude": "#10B981",
    "Ambre": "#F59E0B",
    "Corail": "#FF6B5A",
}


@dataclass
class Palette:
    name: str
    bg: str
    sidebar: str
    surface: str
    surface2: str
    surface3: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent2: str
    success: str = "#34D399"
    warning: str = "#FBBF24"
    danger: str = "#F87171"
    info: str = "#38BDF8"

    @property
    def dark(self) -> bool:
        return self.name == "dark"


def _mix(c1: str, c2: str, t: float) -> str:
    a, b = QColor(c1), QColor(c2)
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    ).name()


def make_palette(theme: str = "dark", accent: str = "#7C5CFF") -> Palette:
    accent2 = _mix(accent, "#FF4FA3", 0.55) if accent.upper() != "#FF4FA3" else "#FF8A5B"
    if theme == "light":
        return Palette("light", bg="#F4F5FB", sidebar="#FFFFFF", surface="#FFFFFF", surface2="#F7F7FC",
                       surface3="#EEEFF8", border="#E2E4F0", text="#17182E", muted="#646985", faint="#A3A7C2",
                       accent=accent, accent2=accent2, success="#059669", warning="#D97706", danger="#DC2626",
                       info="#0284C7")
    return Palette("dark", bg="#0D0E1B", sidebar="#111226", surface="#16182F", surface2="#1C1E3A",
                   surface3="#24274A", border="#2A2D54", text="#ECEDF8", muted="#9A9EC4", faint="#5F6390",
                   accent=accent, accent2=accent2)


CURRENT: Palette = make_palette()


def rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.3f})"


def base_font_family() -> str:
    families = set(QFontDatabase.families())
    for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Ubuntu", "Noto Sans", "DejaVu Sans"):
        if f in families:
            return f
    return QApplication.font().family()


def stylesheet(p: Palette, check_icon: str = "") -> str:
    acc_soft = rgba(p.accent, 0.16 if p.dark else 0.10)
    rgba(p.accent, 0.26 if p.dark else 0.16)
    hover = rgba("#FFFFFF", 0.05) if p.dark else rgba("#000000", 0.04)
    sel_text = "#FFFFFF"
    return f"""
* {{ outline: none; }}
QWidget {{ color: {p.text}; font-size: 10pt; }}
QMainWindow, #Root {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface3}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

/* ---------- Barre latérale ---------- */
#Sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#BrandTitle {{ font-size: 13pt; font-weight: 700; }}
#BrandSub {{ color: {p.muted}; font-size: 8.5pt; }}
#NavButton {{ text-align: left; padding: 10px 14px; border-radius: 10px; border: none; background: transparent;
             color: {p.muted}; font-weight: 600; font-size: 10pt; }}
#NavButton:hover {{ background: {hover}; color: {p.text}; }}
#NavButton:checked {{ background: {acc_soft}; color: {p.text}; }}
#SidebarSection {{ color: {p.faint}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 12px 14px 4px 14px; }}
#ProjectChip {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 12px; }}

/* ---------- Pages ---------- */
#PageTitle {{ font-size: 20pt; font-weight: 700; }}
#PageSubtitle {{ color: {p.muted}; font-size: 10.5pt; }}
#SectionTitle {{ font-size: 12pt; font-weight: 700; }}
#Muted {{ color: {p.muted}; }}
#Faint {{ color: {p.faint}; }}
#Hint {{ color: {p.muted}; font-size: 9pt; }}
#BigNumber {{ font-size: 22pt; font-weight: 700; }}
#StatLabel {{ color: {p.muted}; font-size: 9pt; }}

#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#CardFlat {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 12px; }}
#CardHover {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#CardHover:hover {{ border: 1px solid {p.accent}; background: {p.surface2}; }}
#VoiceCard {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#VoiceCard:hover {{ border: 1px solid {rgba(p.accent, 0.7)}; }}
#VoiceCard[selected="true"] {{ border: 2px solid {p.accent}; background: {p.surface2}; }}
#DropZone {{ background: {rgba(p.accent, 0.05)}; border: 2px dashed {rgba(p.accent, 0.55)}; border-radius: 18px; }}
#DropZone[hover="true"] {{ background: {acc_soft}; border: 2px dashed {p.accent}; }}
#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; }}

/* ---------- Boutons ---------- */
QPushButton {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; padding: 8px 16px;
              font-weight: 600; }}
QPushButton:hover {{ background: {p.surface3}; border-color: {rgba(p.accent, 0.6)}; }}
QPushButton:pressed {{ background: {acc_soft}; }}
QPushButton:disabled {{ color: {p.faint}; background: {p.surface}; border-color: {p.border}; }}
QPushButton#Primary {{ border: none; color: white; padding: 9px 20px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.accent}, stop:1 {p.accent2}); }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {_mix(p.accent, '#FFFFFF', 0.12)},
    stop:1 {_mix(p.accent2, '#FFFFFF', 0.12)}); }}
QPushButton#Primary:disabled {{ background: {p.surface3}; color: {p.faint}; }}
QPushButton#Danger {{ color: {p.danger}; }}
QPushButton#Danger:hover {{ background: {rgba(p.danger, 0.12)}; border-color: {p.danger}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.muted}; padding: 6px 10px; }}
QPushButton#Ghost:hover {{ background: {hover}; color: {p.text}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 5px; }}
QToolButton:hover {{ background: {hover}; }}
QToolButton:checked {{ background: {acc_soft}; }}
QToolButton#Round {{ border-radius: 20px; }}
QToolButton#PlayBig {{ border-radius: 22px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 {p.accent}, stop:1 {p.accent2}); }}
QToolButton#PlayBig:hover {{ background: {p.accent}; }}
QToolButton::menu-indicator {{ image: none; }}

/* ---------- Champs ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 9px; padding: 6px 9px;
    selection-background-color: {p.accent}; selection-color: {sel_text}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ min-height: 20px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p.accent}; }}
QPlainTextEdit#Editor {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; padding: 18px 22px;
    font-size: 11.5pt; }}
QPlainTextEdit#Console {{ background: {_mix(p.bg, '#000000', 0.25) if p.dark else '#F0F1F8'}; border-radius: 12px;
    font-family: 'Cascadia Mono', 'Consolas', 'DejaVu Sans Mono', monospace; font-size: 9pt; color: {p.muted}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px;
    selection-background-color: {acc_soft}; selection-color: {p.text}; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator {{ border: 2px solid {p.faint}; border-radius: 5px; background: transparent; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url("{check_icon}"); }}
QRadioButton::indicator {{ border: 2px solid {p.faint}; border-radius: 10px; }}
QRadioButton::indicator:checked {{ border: 5px solid {p.accent}; }}

/* ---------- Listes & tableaux ---------- */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; padding: 4px;
    selection-background-color: {acc_soft}; selection-color: {p.text}; alternate-background-color: {p.surface2}; }}
QListWidget::item, QTreeWidget::item, QListView::item {{ border-radius: 9px; padding: 8px; margin: 1px 2px; }}
QListWidget::item:hover, QTreeWidget::item:hover, QListView::item:hover {{ background: {hover}; }}
QListWidget::item:selected, QTreeWidget::item:selected, QListView::item:selected, QTableWidget::item:selected {{
    background: {acc_soft}; color: {p.text}; }}
QHeaderView::section {{ background: transparent; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
    padding: 8px 6px; font-weight: 600; }}
QTableWidget {{ gridline-color: transparent; }}
QTableWidget::item {{ padding: 6px; border-bottom: 1px solid {rgba(p.border, 0.6)}; }}

/* ---------- Divers ---------- */
QProgressBar {{ background: {p.surface3}; border: none; border-radius: 5px; height: 10px; text-align: center;
    color: transparent; max-height: 10px; }}
QProgressBar::chunk {{ border-radius: 5px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 {p.accent}, stop:1 {p.accent2}); }}
QSlider::groove:horizontal {{ height: 6px; background: {p.surface3}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.accent}, stop:1 {p.accent2});
    border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; border: 3px solid {p.accent}; width: 12px; height: 12px;
    margin: -6px 0; border-radius: 9px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(p.muted, 0.35)}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {rgba(p.muted, 0.6)}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {rgba(p.muted, 0.35)}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {p.muted}; padding: 9px 18px; margin-right: 6px; border-radius: 10px;
    font-weight: 600; }}
QTabBar::tab:selected {{ background: {acc_soft}; color: {p.text}; }}
QTabBar::tab:hover:!selected {{ background: {hover}; }}
QMenu {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 22px 8px 12px; border-radius: 7px; }}
QMenu::item:selected {{ background: {acc_soft}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QSplitter::handle {{ background: transparent; }}
QDialog {{ background: {p.bg}; }}
QMessageBox {{ background: {p.surface}; }}
QGroupBox {{ border: 1px solid {p.border}; border-radius: 12px; margin-top: 14px; padding: 14px 12px 10px 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {p.muted}; }}

#PlayerBar {{ background: {p.sidebar}; border-top: 1px solid {p.border}; }}
#Badge {{ border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 700; }}
#Toast {{ background: {p.surface3}; border: 1px solid {p.border}; border-radius: 12px; }}
"""


def apply(app: QApplication, theme: str = "dark", accent: str = "#7C5CFF") -> Palette:
    global CURRENT
    CURRENT = make_palette(theme, accent)
    p = CURRENT
    app.setStyle("Fusion")
    font = QFont(base_font_family())
    font.setPointSizeF(10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p.bg))
    pal.setColor(QPalette.WindowText, QColor(p.text))
    pal.setColor(QPalette.Base, QColor(p.surface2))
    pal.setColor(QPalette.AlternateBase, QColor(p.surface))
    pal.setColor(QPalette.Text, QColor(p.text))
    pal.setColor(QPalette.Button, QColor(p.surface2))
    pal.setColor(QPalette.ButtonText, QColor(p.text))
    pal.setColor(QPalette.Highlight, QColor(p.accent))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor(p.surface3))
    pal.setColor(QPalette.ToolTipText, QColor(p.text))
    pal.setColor(QPalette.PlaceholderText, QColor(p.faint))
    pal.setColor(QPalette.Link, QColor(p.accent))
    app.setPalette(pal)
    from . import icons

    icons.clear_cache()
    app.setStyleSheet(stylesheet(p, icons.check_icon_file()))
    return p
