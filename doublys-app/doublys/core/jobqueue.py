"""File d'attente : plusieurs vidéos doublées l'une après l'autre (la nuit par exemple), reprise après un arrêt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import settings

WAITING, RUNNING, DONE, ERROR = "waiting", "running", "done", "error"
STATE_LABELS = {WAITING: "en attente", RUNNING: "en cours", DONE: "terminée", ERROR: "erreur"}


@dataclass
class QueueItem:
    path: str  # projet .doublys
    state: str = WAITING
    message: str = ""
    result: str = ""  # vidéo exportée

    @property
    def title(self) -> str:
        return Path(self.path).stem


def items() -> list[QueueItem]:
    out = []
    for d in settings().get("queue") or []:
        if isinstance(d, dict) and d.get("path"):
            out.append(QueueItem(**{k: v for k, v in d.items() if k in QueueItem.__dataclass_fields__}))
    return out


def save(entries: list[QueueItem]) -> None:
    settings().set("queue", [asdict(e) for e in entries])


def add(paths: list[str]) -> int:
    entries = items()
    known = {e.path for e in entries}
    n = 0
    for p in paths:
        if p not in known:
            entries.append(QueueItem(path=p))
            known.add(p)
            n += 1
    save(entries)
    return n


def update(path: str, **fields) -> None:
    entries = items()
    for e in entries:
        if e.path == path:
            for k, v in fields.items():
                setattr(e, k, v)
    save(entries)


def remove(paths: list[str]) -> None:
    save([e for e in items() if e.path not in set(paths)])


def next_waiting() -> QueueItem | None:
    for e in items():
        if e.state in (WAITING, RUNNING):  # « en cours » : interrompue (fermeture, coupure) → reprise
            return e
    return None


def pending_count() -> int:
    return sum(1 for e in items() if e.state in (WAITING, RUNNING))
