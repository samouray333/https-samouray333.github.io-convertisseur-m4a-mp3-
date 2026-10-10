"""Import d'un modèle de voix RVC (.pth + .index), seul ou dans une archive .zip."""

from __future__ import annotations

import random
import re
import shutil
import zipfile
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, \
    QVBoxLayout

from ...core.models import VoiceProfile
from ..widgets import button, card_title, label

COLORS = ["#7C5CFF", "#FF7AB6", "#4DD0E1", "#FFB74D", "#81C784", "#BA68C8", "#4FC3F7", "#F06292"]
MAX_SIZE = 600 * 1024 * 1024


def _pick_index(names: list[str], stem: str) -> str | None:
    """Choisit l'index qui accompagne le modèle (« added_… » de préférence, sinon le plus proche du nom)."""
    idx = [n for n in names if n.lower().endswith(".index") and "trained_" not in Path(n).name.lower()]
    if not idx:
        return None
    key = re.sub(r"[^a-z0-9]", "", stem.lower())
    idx.sort(key=lambda n: (key not in re.sub(r"[^a-z0-9]", "", n.lower()), not Path(n).name.startswith("added_")))
    return idx[0]


def _pick_model(names: list[str]) -> str | None:
    """Modèle final : un .pth qui n'est pas un point de sauvegarde d'entraînement (G_…, D_…)."""
    pths = [n for n in names if n.lower().endswith(".pth") and not re.match(r"^[GD]_\d+", Path(n).name)]
    return pths[0] if pths else None


def find_files(path: Path) -> tuple[str | None, str | None]:
    """(modèle, index) dans un dossier ou une archive .zip ; chemins ou noms d'entrée de l'archive."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir()]
        model = _pick_model(names)
        return model, _pick_index(names, Path(model).stem if model else path.stem)
    names = [str(p) for p in path.parent.iterdir() if p.is_file()]
    return str(path), _pick_index(names, path.stem)


def clean_name(stem: str) -> str:
    name = re.sub(r"(_v[12]|_e\d+|_s\d+|_\d+e|_ov2.*|_[0-9]+)$", "", stem, flags=re.I)
    return re.sub(r"[_]+", " ", name).strip() or stem


class RVCImportDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.voice: VoiceProfile | None = None
        self._zip: Path | None = None
        self._model_entry = ""
        self._index_entry: str | None = None
        self._index_from_zip = True
        self.setWindowTitle("Importer un modèle de voix (.pth)")
        self.resize(720, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(card_title("Importer un modèle de voix RVC",
                                 "Choisissez le fichier .pth (ou l'archive .zip qui le contient). L'index .index "
                                 "est trouvé automatiquement s'il est à côté ; il améliore la ressemblance.",
                                 "upload"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.model = QLineEdit()
        self.model.setReadOnly(True)
        pick = button("Choisir…", "folder")
        pick.clicked.connect(self._choose_model)
        g.addWidget(label("Modèle", "Muted"), 0, 0)
        g.addWidget(self.model, 0, 1)
        g.addWidget(pick, 0, 2)
        self.index = QLineEdit()
        self.index.setReadOnly(True)
        self.index.setPlaceholderText("Facultatif")
        pick_i = button("Choisir…", "folder")
        pick_i.clicked.connect(self._choose_index)
        g.addWidget(label("Index", "Muted"), 1, 0)
        g.addWidget(self.index, 1, 1)
        g.addWidget(pick_i, 1, 2)
        self.name = QLineEdit()
        g.addWidget(label("Nom de la voix", "Muted"), 2, 0)
        g.addWidget(self.name, 2, 1, 1, 2)
        self.gender = QComboBox()
        self.gender.addItem("Voix masculine", "M")
        self.gender.addItem("Voix féminine", "F")
        self.gender.setToolTip("Choisit la voix Microsoft qui lit le texte avant la conversion")
        g.addWidget(label("Timbre", "Muted"), 3, 0)
        g.addWidget(self.gender, 3, 1)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.consent = QCheckBox("Ce modèle a été créé à partir de ma voix, ou avec l'accord explicite de la personne, "
                                 "ou sa licence autorise cet usage.")
        self.consent.toggled.connect(self._update)
        lay.addWidget(self.consent)
        lay.addWidget(label("Les modèles de célébrités, de comédiens de doublage ou de personnages trouvés en ligne "
                            "sont en général faits sans leur accord : leur utilisation, surtout dans un livre "
                            "publié, peut être illégale.", "Hint", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Annuler", kind="ghost")
        cancel.clicked.connect(self.reject)
        self.ok = button("Importer", "check", "primary")
        self.ok.clicked.connect(self._import)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self._update()

    # ------------------------------------------------------------------------------
    def set_source(self, path: Path) -> None:
        try:
            model, index = find_files(path)
        except (OSError, zipfile.BadZipFile) as exc:
            self.ctx.toast(f"Fichier illisible : {exc}", "error")
            return
        if model is None:
            self.ctx.toast("Aucun modèle .pth dans cette archive.", "warning")
            return
        self._zip = path if path.suffix.lower() == ".zip" else None
        self.model.setText(f"{path.name} → {Path(model).name}" if self._zip else model)
        self._model_entry = model
        self._index_entry = index
        self._index_from_zip = True
        self.index.setText((f"{path.name} → {Path(index).name}" if self._zip else index) if index else "")
        if not self.name.text().strip():
            self.name.setText(clean_name(Path(model).stem))
        self._update()

    def _choose_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Modèle de voix RVC", "", "Modèle RVC (*.pth *.zip)")
        if path:
            self.set_source(Path(path))

    def _choose_index(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Index du modèle", "", "Index RVC (*.index)")
        if path:
            self._index_entry = path
            self._index_from_zip = False
            self.index.setText(path)

    def _update(self) -> None:
        self.ok.setEnabled(bool(self.model.text()) and self.consent.isChecked())

    def _copy(self, entry: str, target: Path, from_zip: bool) -> None:
        if from_zip and self._zip is not None:
            with zipfile.ZipFile(self._zip) as zf:
                info = zf.getinfo(entry)
                if info.file_size > MAX_SIZE:
                    raise ValueError("Fichier trop volumineux pour un modèle de voix.")
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        else:
            if Path(entry).stat().st_size > MAX_SIZE:
                raise ValueError("Fichier trop volumineux pour un modèle de voix.")
            shutil.copy2(entry, target)

    def _import(self) -> None:
        lib = self.ctx.library
        voice = VoiceProfile(name=self.name.text().strip() or "Modèle RVC", engine="rvc", kind="clone",
                             consent=True, gender=self.gender.currentData(),
                             language=self.ctx.project.metadata.language or "fr", color=random.choice(COLORS),
                             description="Modèle de voix RVC importé")
        lib.save(voice)
        d = lib.voice_dir(voice)
        index_from_zip = self._zip is not None and self._index_from_zip
        try:
            self._copy(self._model_entry, d / "modele.pth", self._zip is not None)
            with open(d / "modele.pth", "rb") as fh:
                if fh.read(2) != b"PK":  # les modèles PyTorch récents sont des archives zip
                    raise ValueError("Ce fichier n'est pas un modèle PyTorch (.pth) valide.")
            voice.references = ["modele.pth"]
            if self._index_entry:
                self._copy(self._index_entry, d / "modele.index", index_from_zip)
                voice.references.append("modele.index")
        except Exception as exc:
            lib.delete(voice.id)
            self.ctx.toast(f"Import impossible : {exc}", "error", 6500)
            return
        self.voice = lib.save(voice)
        from ...core import engines

        ready = engines.get_engine("rvc").is_ready()
        self.ctx.toast(f"Voix « {voice.name} » importée." + ("" if ready else " Installez le moteur « Modèles de "
                       "voix RVC » dans Moteurs IA pour l'utiliser."), "success", 6500)
        self.accept()
