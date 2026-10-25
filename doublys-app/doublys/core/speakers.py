"""Regroupement des répliques par personne à partir des empreintes vocales (ECAPA)."""

from __future__ import annotations

import numpy as np

from .models import Line, Person

COLORS = ["#FF6B4A", "#4FC3F7", "#B388FF", "#69F0AE", "#FFD54F", "#FF7AB6", "#4DD0E1", "#AED581", "#FFB74D",
          "#9575CD", "#F06292", "#7986CB"]
MIN_EMBED_SECONDS = 0.8  # en dessous, l'empreinte est peu fiable : la réplique suit sa voisine


def _normalize(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)


def agglomerate(emb: np.ndarray, threshold: float, max_clusters: int = 0) -> np.ndarray:
    """Regroupement hiérarchique (lien moyen, distance cosinus). Renvoie une étiquette par ligne."""
    n = len(emb)
    if n == 0:
        return np.zeros(0, dtype=int)
    if n == 1:
        return np.zeros(1, dtype=int)
    x = _normalize(np.asarray(emb, dtype=np.float64))
    sim = x @ x.T
    np.fill_diagonal(sim, -np.inf)
    sizes = np.ones(n)
    active = np.ones(n, dtype=bool)
    members = [[i] for i in range(n)]
    clusters = n
    while clusters > 1:
        flat = int(np.argmax(sim))
        i, j = divmod(flat, n)
        best = sim[i, j]
        if not np.isfinite(best):
            break
        if (1.0 - best) > threshold and (max_clusters <= 0 or clusters <= max_clusters):
            break
        # lien moyen (formule de Lance-Williams) : la similarité moyenne est pondérée par les tailles
        new = (sim[i] * sizes[i] + sim[j] * sizes[j]) / (sizes[i] + sizes[j])
        sim[i, :] = new
        sim[:, i] = new
        sim[i, i] = -np.inf
        sim[j, :] = -np.inf
        sim[:, j] = -np.inf
        sizes[i] += sizes[j]
        active[j] = False
        members[i].extend(members[j])
        members[j] = []
        clusters -= 1
    labels = np.zeros(n, dtype=int)
    for k, idx in enumerate(i for i in range(n) if active[i]):
        labels[members[idx]] = k
    return labels


def assign_people(lines: list[Line], embeddings: dict[str, list[float]], threshold: float = 0.62,
                  max_speakers: int = 0, min_seconds: float = 3.0) -> list[Person]:
    """Attribue une personne (P1…Pn par ordre d'apparition) à chaque réplique. Modifie ``lines``."""
    usable = [ln for ln in lines if ln.id in embeddings and ln.length >= MIN_EMBED_SECONDS]
    if not usable:
        usable = [ln for ln in lines if ln.id in embeddings]
    if not usable:
        person = Person(name="P1", color=COLORS[0])
        for ln in lines:
            ln.person_id = person.id
        return [person] if lines else []
    emb = np.array([embeddings[ln.id] for ln in usable], dtype=np.float64)
    labels = agglomerate(emb, threshold, max_speakers)
    groups: dict[int, list[int]] = {}
    for k, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(k)

    def centroid(idx: list[int]) -> np.ndarray:
        c = emb[idx].mean(axis=0)
        return c / (np.linalg.norm(c) + 1e-9)

    # petits groupes (moins de ``min_seconds`` de parole) rattachés au groupe le plus proche
    def talk(idx):
        return sum(usable[k].length for k in idx)

    changed = True
    while changed and len(groups) > 1:
        changed = False
        small = min(groups, key=lambda g: talk(groups[g]))
        if talk(groups[small]) < min_seconds:
            c = centroid(groups[small])
            others = [g for g in groups if g != small]
            target = max(others, key=lambda g: float(centroid(groups[g]) @ c))
            groups[target].extend(groups.pop(small))
            changed = True
    label_of = {}
    for g, idx in groups.items():
        for k in idx:
            label_of[usable[k].id] = g
    # répliques sans empreinte fiable : même personne que la réplique la plus proche dans le temps
    ordered = sorted(lines, key=lambda x: x.start)
    for ln in ordered:
        if ln.id in label_of:
            continue
        if ln.id in embeddings:
            v = np.asarray(embeddings[ln.id], dtype=np.float64)
            v = v / (np.linalg.norm(v) + 1e-9)
            label_of[ln.id] = max(groups, key=lambda g: float(centroid(groups[g]) @ v))
            continue
        near = min((o for o in ordered if o.id in label_of), key=lambda o: abs(o.start - ln.start), default=None)
        label_of[ln.id] = label_of[near.id] if near is not None else next(iter(groups))
    # numérotation par ordre d'apparition
    order: list[int] = []
    for ln in ordered:
        g = label_of[ln.id]
        if g not in order:
            order.append(g)
    people = {g: Person(name=f"P{i + 1}", color=COLORS[i % len(COLORS)]) for i, g in enumerate(order)}
    for ln in lines:
        ln.person_id = people[label_of[ln.id]].id
    return [people[g] for g in order]


def keep_names(old: list[Person], new: list[Person], lines_old: dict[str, str], lines: list[Line]) -> list[Person]:
    """Après un nouveau regroupement, garde le nom et la voix choisis pour la personne qui partage le plus de
    répliques avec l'ancienne."""
    by_old = {p.id: p for p in old}
    for p in new:
        votes: dict[str, float] = {}
        for ln in lines:
            if ln.person_id == p.id and lines_old.get(ln.id) in by_old:
                votes[lines_old[ln.id]] = votes.get(lines_old[ln.id], 0.0) + ln.length
        if votes:
            src = by_old[max(votes, key=votes.get)]
            if not src.name.startswith("P") or not src.name[1:].isdigit():
                p.name = src.name
            for attr in ("voice_mode", "base_voice", "params", "rvc_model", "rvc_index", "color"):
                setattr(p, attr, getattr(src, attr))
            if src.reference_source == "file":
                p.reference, p.reference_source = src.reference, "file"
    return new
