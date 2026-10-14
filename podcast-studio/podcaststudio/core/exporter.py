"""Export du podcast : un MP3 par épisode (jingles, étiquettes ID3), flux RSS, WAV, FLAC, Opus, vidéo, rapport."""

from __future__ import annotations

import dataclasses
import html
import logging
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import __version__
from . import audio, ffmpeg
from .mastering import MasteringOptions, master_file
from .models import BookMetadata, ExportSettings

log = logging.getLogger(__name__)

ProgressCb = Callable[[str, float], None]


@dataclass
class ExportItem:
    title: str
    source: Path  # rendu brut de l'épisode
    kind: str = "chapter"  # opening | chapter | closing
    cues: list[tuple[float, float, str]] = field(default_factory=list)  # sous-titres (début, fin, texte)
    # épisode de podcast
    id: str = ""
    number: int = 0
    season: int = 0
    description: str = ""
    pub_date: str = ""
    episode_type: str = "full"
    chapters: list[tuple[float, str]] = field(default_factory=list)  # (début en secondes, titre)


@dataclass
class ExportResult:
    output_dir: Path
    files: list[Path] = field(default_factory=list)
    report: Path | None = None
    stats: list[tuple[str, audio.AudioStats]] = field(default_factory=list)
    duration: float = 0.0
    warnings: list[str] = field(default_factory=list)

    episodes: list[tuple[ExportItem, Path, float]] = field(default_factory=list)  # MP3 par épisode
    feed: Path | None = None

    @property
    def acx_ok(self) -> bool:
        return all(s.acx_ok for _, s in self.stats)


EPISODES_DIR = "episodes"


def safe_filename(name: str, max_len: int = 90) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if not name:
        name = "sans titre"
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if name.upper() in reserved:
        name = "_" + name
    return name[:max_len].rstrip(". ")


def credits_text(template: str, meta: BookMetadata) -> str:
    values = {
        "title": meta.title or "Sans titre",
        "subtitle": meta.subtitle,
        "subtitle_sentence": (meta.subtitle.rstrip(".") + ". ") if meta.subtitle else "",
        "author": meta.author or "un auteur inconnu",
        "narrator": meta.narrator or "une voix de synthèse",
        "publisher": meta.publisher,
        "year": meta.year,
        "copyright": meta.copyright,
    }
    # variables remplacées une à une : une accolade isolée dans le texte ne casse rien
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)
    lines = [re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ---------------------------------------------------------------------------------------
# Couverture
# ---------------------------------------------------------------------------------------
def prepare_cover(src: str | Path, dst: str | Path, size: int = 2400) -> Path | None:
    """Produit une couverture carrée JPEG (2400 × 2400 pour ACX) sans déformer l'image."""
    src_p = Path(src)
    if not src_p.is_file():
        return None
    dst_p = Path(dst)
    vf = (f"scale={size}:{size}:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=0x101018,format=yuvj420p")
    try:
        ffmpeg.run_ffmpeg(["-i", str(src_p), "-vf", vf, "-frames:v", "1", "-q:v", "2", str(dst_p)])
        return dst_p
    except Exception as exc:
        log.warning("Couverture non convertie : %s", exc)
        return None


# ---------------------------------------------------------------------------------------
# Étiquettes
# ---------------------------------------------------------------------------------------
def tag_mp3(path: Path, meta: BookMetadata, title: str, track: int | None, total: int | None,
            cover: Path | None) -> None:
    from mutagen.id3 import (APIC, COMM, ID3, TALB, TCOM, TCON, TCOP, TDRC, TIT2, TPE1, TPE2, TPUB, TRCK,
                             ID3NoHeaderError)

    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TALB(encoding=3, text=meta.title or title))
    if meta.author:
        tags.add(TPE1(encoding=3, text=meta.author))
        tags.add(TPE2(encoding=3, text=meta.author))
    if meta.narrator:
        tags.add(TCOM(encoding=3, text=meta.narrator))
    tags.add(TCON(encoding=3, text=meta.genre or "Audiobook"))
    if meta.year:
        tags.add(TDRC(encoding=3, text=meta.year))
    if meta.publisher:
        tags.add(TPUB(encoding=3, text=meta.publisher))
    if meta.copyright:
        tags.add(TCOP(encoding=3, text=meta.copyright))
    if meta.description:
        tags.add(COMM(encoding=3, lang="fra", desc="", text=meta.description))
    if track:
        tags.add(TRCK(encoding=3, text=f"{track}/{total}" if total else str(track)))
    if cover and cover.is_file():
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover.read_bytes()))
    tags.save(str(path), v2_version=3)


def clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def episode_notes(it: ExportItem, with_chapters: bool) -> str:
    """Description de l'épisode, suivie des chapitres horodatés (« 03:12 La rubrique »)."""
    notes = it.description.strip()
    if with_chapters and len(it.chapters) >= 2:
        lines = "\n".join(f"{clock(t)} {title}" for t, title in it.chapters)
        notes = (notes + "\n\n" if notes else "") + "Chapitres :\n" + lines
    return notes


def write_mp3_chapters(path: Path, chapters: list[tuple[float, str]], duration: float) -> None:
    """Chapitres ID3 (CHAP + CTOC), affichés par Apple Podcasts, Overcast, Pocket Casts…"""
    from mutagen import id3

    if len(chapters) < 2:
        return
    tags = id3.ID3(str(path))
    tags.delall("CHAP")
    tags.delall("CTOC")
    ids = []
    for i, (start, title) in enumerate(chapters):
        end = chapters[i + 1][0] if i + 1 < len(chapters) else duration
        cid = f"chp{i}"
        ids.append(cid)
        tags.add(id3.CHAP(element_id=cid, start_time=int(start * 1000), end_time=int(max(start, end) * 1000),
                          sub_frames=[id3.TIT2(encoding=3, text=title)]))
    tags.add(id3.CTOC(element_id="toc", flags=id3.CTOCFlags.TOP_LEVEL | id3.CTOCFlags.ORDERED, child_element_ids=ids,
                      sub_frames=[id3.TIT2(encoding=3, text="Chapitres")]))
    tags.save(str(path), v2_version=3)


def chapters_json(chapters: list[tuple[float, str]]) -> str:
    """Chapitres au format Podcasting 2.0 (balise <podcast:chapters> du flux)."""
    import json

    return json.dumps({"version": "1.2.0", "chapters": [{"startTime": round(t, 2), "title": title}
                                                         for t, title in chapters]}, ensure_ascii=False, indent=1)


def tag_episode_mp3(path: Path, meta: BookMetadata, it: ExportItem, cover: Path | None) -> None:
    """Étiquettes ID3 d'un épisode (dont les cadres « podcast » reconnus par les applications d'écoute)."""
    from mutagen import id3

    tag_mp3(path, meta, it.title, it.number or None, None, cover)
    tags = id3.ID3(str(path))
    tags.add(id3.TCON(encoding=3, text="Podcast"))
    tags.add(id3.TALB(encoding=3, text=meta.title or "Podcast"))
    if meta.narrator:
        tags.add(id3.TCOM(encoding=3, text=meta.narrator))
    tags.delall("COMM")
    if it.description:
        tags.add(id3.COMM(encoding=3, lang="fra", desc="", text=it.description))
        tags.add(id3.TDES(encoding=3, text=it.description))
    if it.pub_date:
        tags.add(id3.TDRL(encoding=3, text=it.pub_date))
        tags.add(id3.TDRC(encoding=3, text=it.pub_date[:4]))
    if it.season:
        tags.add(id3.TPOS(encoding=3, text=str(it.season)))
    tags.add(id3.PCST(value=1))
    if it.id:
        tags.add(id3.TGID(encoding=3, text=it.id))
    if meta.media_base_url:
        tags.add(id3.WFED(encoding=3, url=meta.media_base_url.rstrip("/") + "/feed.xml"))
    tags.save(str(path), v2_version=3)


def tag_mp4(path: Path, meta: BookMetadata, cover: Path | None) -> None:
    from mutagen.mp4 import MP4, MP4Cover

    m = MP4(str(path))
    if m.tags is None:
        m.add_tags()
    t = m.tags
    t["\xa9nam"] = [meta.title or "Livre audio"]
    t["\xa9alb"] = [meta.title or "Livre audio"]
    if meta.author:
        t["\xa9ART"] = [meta.author]
        t["aART"] = [meta.author]
    if meta.narrator:
        t["\xa9wrt"] = [meta.narrator]
    t["\xa9gen"] = [meta.genre or "Audiobook"]
    if meta.year:
        t["\xa9day"] = [meta.year]
    if meta.description:
        t["desc"] = [meta.description[:250]]
        t["\xa9cmt"] = [meta.description]
    if meta.copyright:
        t["cprt"] = [meta.copyright]
    t["stik"] = [2]  # type de média : livre audio
    t["\xa9too"] = [f"PodCast Studio {__version__}"]
    if cover and cover.is_file():
        t["covr"] = [MP4Cover(cover.read_bytes(), imageformat=MP4Cover.FORMAT_JPEG)]
    m.save()


def tag_flac(path: Path, meta: BookMetadata, title: str, track: int, total: int, cover: Path | None) -> None:
    from mutagen.flac import FLAC, Picture

    f = FLAC(str(path))
    f["title"] = title
    f["album"] = meta.title or title
    if meta.author:
        f["artist"] = meta.author
        f["albumartist"] = meta.author
    if meta.narrator:
        f["composer"] = meta.narrator
        f["performer"] = meta.narrator
    f["genre"] = meta.genre or "Audiobook"
    if meta.year:
        f["date"] = meta.year
    f["tracknumber"] = str(track)
    f["tracktotal"] = str(total)
    if meta.description:
        f["description"] = meta.description
    if cover and cover.is_file():
        pic = Picture()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.data = cover.read_bytes()
        f.clear_pictures()
        f.add_picture(pic)
    f.save()


def _ffmetadata(meta: BookMetadata, chapters: list[tuple[str, float, float]]) -> str:
    e = ffmpeg.escape_metadata
    lines = [";FFMETADATA1",
             f"title={e(meta.title)}", f"album={e(meta.title)}",
             f"artist={e(meta.author)}", f"album_artist={e(meta.author)}",
             f"composer={e(meta.narrator)}", f"genre={e(meta.genre or 'Audiobook')}",
             f"date={e(meta.year)}", f"comment={e(meta.description)}", f"copyright={e(meta.copyright)}",
             f"publisher={e(meta.publisher)}", "encoder=PodCast Studio"]
    for title, start, end in chapters:
        lines += ["", "[CHAPTER]", "TIMEBASE=1/1000", f"START={int(round(start * 1000))}",
                  f"END={int(round(end * 1000))}", f"title={e(title)}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------
# Export principal
# ---------------------------------------------------------------------------------------
def export_audiobook(
    items: list[ExportItem],
    meta: BookMetadata,
    settings: ExportSettings,
    mastering: MasteringOptions,
    out_dir: str | Path,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> ExportResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = ExportResult(output_dir=out)
    formats = list(dict.fromkeys(settings.formats)) or ["mp3_chapters"]
    if "rss" in formats and "mp3_chapters" not in formats:
        formats.insert(0, "mp3_chapters")  # le flux RSS pointe vers les MP3 des épisodes
    items = [it for it in items if it.source.exists()]
    if not items:
        raise ValueError("Aucun épisode produit à exporter. Lancez d'abord la production.")

    def report(msg: str, frac: float):
        if cancel is not None and cancel.is_set():
            raise ffmpeg.Cancelled()
        if progress:
            progress(msg, max(0.0, min(1.0, frac)))

    total_steps = len(items) + len(formats) * max(1, len(items) // 3) + 3
    step = 0

    def advance(msg: str, n: float = 1.0):
        nonlocal step
        step += n
        report(msg, step / total_steps)

    with tempfile.TemporaryDirectory(prefix="export-") as td:
        td = Path(td)
        # 1) Couverture
        cover = None
        if meta.cover_path:
            # Apple Podcasts : image carrée de 1400 à 3000 pixels
            cover = prepare_cover(meta.cover_path, out / "couverture.jpg", 3000 if settings.acx_cover else 1400)
            if cover is None:
                result.warnings.append("La couverture n'a pas pu être convertie.")
            else:
                result.files.append(cover)

        # 2) Musique puis mastering de chaque piste
        mastered: list[tuple[ExportItem, Path, float]] = []
        offsets: dict[int, float] = {}
        for i, it in enumerate(items, 1):
            report(f"Mastering : {it.title}", step / total_steps)
            src = it.source
            try:
                each = settings.jingles_each_episode
                src, offsets[i] = add_music(src, td / f"{i:03d}-music.wav", settings, it.kind,
                                            first=each or i == 1, last=each or i == len(items), cancel=cancel)
            except ffmpeg.Cancelled:
                raise
            except Exception as exc:
                log.warning("Musique non ajoutée à « %s » : %s", it.title, exc)
                result.warnings.append(f"Musique non ajoutée à « {it.title} » : {exc}")
                offsets[i] = 0.0
            if offsets[i] and it.cues:
                it = dataclasses.replace(it, cues=[(a + offsets[i], b + offsets[i], t) for a, b, t in it.cues])
            if it.chapters and offsets[i]:  # le jingle d'intro devient le premier chapitre
                it = dataclasses.replace(it, chapters=[(0.0, "Générique")]
                                         + [(t + offsets[i], title) for t, title in it.chapters])
            if settings.chapters_in_notes:
                it = dataclasses.replace(it, description=episode_notes(it, True))
            dst = td / f"{i:03d}.wav"
            stats = master_file(src, dst, mastering, cancel=cancel)
            result.stats.append((it.title, stats))
            mastered.append((it, dst, stats.duration))
            advance(f"Mastering : {it.title}")
        result.duration = sum(d for _, _, d in mastered)
        ac = str(max(audio.channels_of(p) for _, p, _ in mastered))  # « 2 » pour un podcast en stéréo

        n = len(mastered)
        base_name = safe_filename(meta.title or "Podcast")

        def track_name(idx: int, it: ExportItem) -> str:
            try:
                name = settings.file_pattern.format(index=idx, number=it.number or idx, season=it.season,
                                                    title=it.title, book=meta.title, podcast=meta.title)
            except (KeyError, IndexError, ValueError):
                name = f"{it.number or idx:03d} - {it.title}"
            return safe_filename(name)

        # Liste de chapitres (pour M4B et MP3 unique)
        chapters: list[tuple[str, float, float]] = []
        t = 0.0
        for it, _p, d in mastered:
            chapters.append((it.title, t, t + d))
            t += d
        concat = ffmpeg.concat_list_file([p for _, p, _ in mastered], td / "concat.txt")
        metafile = td / "meta.txt"
        metafile.write_text(_ffmetadata(meta, chapters), encoding="utf-8")

        for fmt in formats:
            if fmt == "m4b":
                target = out / f"{base_name}.m4b"
                report("Encodage du livre audio M4B…", step / total_steps)
                ffmpeg.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(metafile),
                                   "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                                   "-c:a", "aac", "-b:a", settings.m4b_bitrate, "-ac", ac, "-ar", "44100",
                                   "-movflags", "+faststart", "-f", "mp4", str(target)],
                                  result.duration, lambda f: report("Encodage M4B…", (step + f * max(1, n // 3)) / total_steps),
                                  cancel)
                tag_mp4(target, meta, cover)
                result.files.append(target)
                advance("M4B terminé", max(1, n // 3))
            elif fmt == "mp3_chapters":
                folder = out / EPISODES_DIR  # nom sans accent ni espace : il fait partie des adresses du flux RSS
                folder.mkdir(exist_ok=True)
                playlist = []
                for idx, (it, src, d) in enumerate(mastered, 1):
                    report(f"MP3 : {it.title}", step / total_steps)
                    target = folder / f"{track_name(idx, it)}.mp3"
                    ffmpeg.run_ffmpeg(["-i", str(src), "-c:a", "libmp3lame", "-b:a", settings.mp3_bitrate,
                                       "-ar", "44100", "-ac", ac, "-id3v2_version", "3", str(target)],
                                      cancel=cancel)
                    tag_episode_mp3(target, meta, it, cover)
                    if len(it.chapters) >= 2:
                        write_mp3_chapters(target, it.chapters, d)
                        target.with_suffix(".chapters.json").write_text(chapters_json(it.chapters), encoding="utf-8")
                    result.files.append(target)
                    result.episodes.append((it, target, d))
                    playlist.append((target.name, d, it.title))
                    advance(f"MP3 : {it.title}", max(1, n // 3) / n)
                m3u = ["#EXTM3U"] + [f"#EXTINF:{int(d)},{t}\n{name}" for name, d, t in playlist]
                (folder / f"{base_name}.m3u").write_text("\n".join(m3u) + "\n", encoding="utf-8")
            elif fmt == "mp3_single":
                target = out / f"{base_name}.mp3"
                report("Encodage du MP3 unique…", step / total_steps)
                ffmpeg.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(metafile),
                                   "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
                                   "-c:a", "libmp3lame", "-b:a", settings.mp3_bitrate, "-ar", "44100", "-ac", ac,
                                   "-id3v2_version", "3", str(target)], result.duration, None, cancel)
                tag_mp3(target, meta, meta.title or "Podcast", None, None, cover)
                result.files.append(target)
                advance("MP3 unique terminé", max(1, n // 3))
            elif fmt in ("wav", "flac", "opus"):
                folder = out / f"{base_name} - {fmt.upper()}"
                folder.mkdir(exist_ok=True)
                for idx, (it, src, _d) in enumerate(mastered, 1):
                    report(f"{fmt.upper()} : {it.title}", step / total_steps)
                    stem = track_name(idx, it)
                    if fmt == "wav":
                        target = folder / f"{stem}.wav"
                        shutil.copy2(src, target)
                    elif fmt == "flac":
                        target = folder / f"{stem}.flac"
                        ffmpeg.run_ffmpeg(["-i", str(src), "-c:a", "flac", "-compression_level", "8", str(target)],
                                          cancel=cancel)
                        tag_flac(target, meta, it.title, idx, n, cover)
                    else:
                        target = folder / f"{stem}.opus"
                        ffmpeg.run_ffmpeg(["-i", str(src), "-c:a", "libopus", "-b:a", settings.opus_bitrate,
                                           "-application", "voip", "-ar", "48000",
                                           "-metadata", f"title={it.title}", "-metadata", f"album={meta.title}",
                                           "-metadata", f"artist={meta.author}", "-metadata", f"track={idx}/{n}",
                                           str(target)], cancel=cancel)
                    result.files.append(target)
                    advance(f"{fmt.upper()} : {it.title}", max(1, n // 3) / n)

        # Sous-titres synchronisés
        if "subtitles" in formats and any(it.cues for it, _p, _d in mastered):
            folder = out / f"{base_name} - Sous-titres"
            folder.mkdir(exist_ok=True)
            book_cues: list[tuple[float, float, str]] = []
            t0 = 0.0
            for idx, (it, _src, d) in enumerate(mastered, 1):
                stem = track_name(idx, it)
                (folder / f"{stem}.srt").write_text(to_srt(it.cues), encoding="utf-8")
                (folder / f"{stem}.lrc").write_text(to_lrc(it.cues, it.title, meta), encoding="utf-8")
                book_cues += [(a + t0, b + t0, txt) for a, b, txt in it.cues]
                t0 += d
            (folder / f"{base_name} (tous les épisodes).srt").write_text(to_srt(book_cues), encoding="utf-8")
            (folder / f"{base_name} (tous les épisodes).lrc").write_text(to_lrc(book_cues, meta.title, meta),
                                                                     encoding="utf-8")
            result.files.append(folder / f"{base_name} (tous les épisodes).srt")
            advance("Sous-titres terminés", 0.5)

        # Vidéos pour YouTube
        if "video" in formats:
            folder = out / f"{base_name} - Vidéos"
            folder.mkdir(exist_ok=True)
            for idx, (it, src, d) in enumerate(mastered, 1):
                report(f"Vidéo : {it.title}", step / total_steps)
                target = folder / f"{track_name(idx, it)}.mp4"
                make_video(src, target, cover, it.cues, td, d, cancel=cancel)
                result.files.append(target)
                advance(f"Vidéo : {it.title}", max(1, n // 3) / n)

        # Extrait commercial (ACX : 1 à 5 minutes, sans musique ni crédits)
        if settings.make_sample:
            body = next(((it, p, d) for it, p, d in mastered if it.kind == "chapter"), None)
            if body is not None:
                it, src, d = body
                length = max(30.0, min(settings.sample_minutes * 60.0, d))
                target = out / f"{base_name} - Extrait.mp3"
                fade_start = max(0.0, length - 3.0)
                ffmpeg.run_ffmpeg(["-i", str(src), "-t", f"{length:.2f}", "-af", f"afade=t=out:st={fade_start:.2f}:d=3",
                                   "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", ac,
                                   "-id3v2_version", "3", str(target)], cancel=cancel)
                tag_mp3(target, meta, f"{meta.title} (extrait)", None, None, cover)
                result.files.append(target)
        # Flux RSS (après les MP3, dont il donne la taille et la durée)
        if "rss" in formats and result.episodes:
            from .rss import write_feed

            result.feed = write_feed(meta, result.episodes, out / "feed.xml", cover, settings.rss_only_due)
            result.files.append(result.feed)
            if not meta.media_base_url:
                result.warnings.append("Adresse de publication non renseignée : le flux RSS utilise des liens "
                                       "relatifs. Indiquez l'adresse en ligne du dossier avant de le publier.")
        advance("Finalisation")

        if settings.write_report:
            result.report = write_report(result, meta, mastering, out / "Rapport qualité.html")
    report("Export terminé", 1.0)
    return result


def write_report(result: ExportResult, meta: BookMetadata, mastering: MasteringOptions, path: Path) -> Path:
    rows = []
    for title, s in result.stats:
        checks = s.acx_checks()
        cells = "".join(
            f'<td class="{"ok" if ok else "ko"}">{html.escape(label)}</td>' for ok, label in checks.values()
        )
        badge = '<span class="badge ok">Conforme</span>' if s.acx_ok else '<span class="badge ko">À vérifier</span>'
        rows.append(f"<tr><td>{html.escape(title)}</td>{cells}<td>{badge}</td></tr>")
    files = "".join(f"<li>{html.escape(f.name)}</li>" for f in result.files)
    verdict = ("Tous les épisodes respectent les critères techniques d'un podcast (≈ -16 LUFS)."
               if result.acx_ok else "Certains épisodes ne respectent pas tous les critères : voir le détail.")
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport qualité — {html.escape(meta.title)}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1020;color:#e8e8f4;margin:0;padding:32px}}
h1{{margin:0 0 4px;font-size:26px}} .sub{{color:#9aa0c3;margin-bottom:24px}}
.card{{background:#191a33;border-radius:14px;padding:20px 24px;margin-bottom:20px;border:1px solid #2a2c52}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #2a2c52}}
th{{color:#9aa0c3;font-weight:600}} td.ok{{color:#7ee2a8}} td.ko{{color:#ff8a8a}}
.badge{{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}} .badge.ok{{background:#1f4d36;color:#7ee2a8}}
.badge.ko{{background:#5a2330;color:#ff9a9a}} .verdict{{font-size:16px}}
</style></head><body>
<h1>{html.escape(meta.title or 'Podcast')}</h1>
<div class="sub">{html.escape(meta.author)} — animé par {html.escape(meta.narrator or 'des voix de synthèse')} ·
Durée totale : {audio_duration(result.duration)} · Mastering : {html.escape(mastering.preset)} ·
Généré le {time.strftime('%d/%m/%Y à %H:%M')} par PodCast Studio {__version__}</div>
<div class="card verdict">{verdict}</div>
<div class="card"><table><tr><th>Épisode</th><th>RMS</th><th>Crête</th><th>Bruit de fond</th><th>Durée</th><th></th></tr>
{''.join(rows)}</table></div>
<div class="card"><b>Fichiers produits</b><ul>{files}</ul></div>
<div class="card">Rappel podcast : MP3 128 kb/s (voix) à 44,1 kHz, volume autour de -16 LUFS (Apple Podcasts,
Spotify), crêtes ≤ -1 dB, couverture carrée de 1400 à 3000 pixels (JPEG), un titre et une description par épisode.
Pour publier : déposez le dossier « episodes », la couverture et feed.xml à l'adresse indiquée dans les
informations du podcast, puis soumettez l'adresse du flux à Apple Podcasts, Spotify for Creators, Deezer…
Vérifiez aussi que vous disposez des droits sur les textes et musiques et, pour une voix clonée, du consentement
de la personne.</div>
</body></html>"""
    path.write_text(page, encoding="utf-8")
    return path


def audio_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min {s:02d} s" if h else f"{m} min {s:02d} s"


# ---------------------------------------------------------------------------------------
# Musique
# ---------------------------------------------------------------------------------------
def _music_chain(gain_db: float, length: float | None = None, fade_in: float = 0.5, fade_out: float = 3.0,
                 layout: str = "mono") -> str:
    parts = ["aresample=44100", f"aformat=sample_fmts=fltp:channel_layouts={layout}"]
    if length:
        parts.append(f"atrim=0:{length:.3f}")
    parts.append(f"volume={gain_db:.2f}dB")
    if fade_in:
        parts.append(f"afade=t=in:d={fade_in:.2f}")
    if length and fade_out:
        parts.append(f"afade=t=out:st={max(0.0, length - fade_out):.3f}:d={fade_out:.2f}")
    return ",".join(parts)


def _level_db(path: Path) -> float:
    try:
        st = audio.analyze_file(path)
        return st.rms_db
    except Exception:
        data, sr = audio.read_audio(path)
        return audio.analyze_array(data, sr).rms_db


def add_music(src: Path, dst: Path, settings: ExportSettings, kind: str, first: bool, last: bool,
              cancel: threading.Event | None = None) -> tuple[Path, float]:
    """Ajoute fond sonore / jingles à une piste ; renvoie (fichier, décalage du début de la voix)."""
    bg = Path(settings.background_music) if settings.background_music else None
    intro = Path(settings.intro_music) if settings.intro_music and first else None
    outro = Path(settings.outro_music) if settings.outro_music and last else None
    bg = bg if (bg and bg.is_file() and kind == "chapter") else None
    intro = intro if (intro and intro.is_file()) else None
    outro = outro if (outro and outro.is_file()) else None
    if not (bg or intro or outro):
        return src, 0.0
    voice_db = _level_db(src)
    if voice_db < -90:
        return src, 0.0
    current = src
    offset = 0.0
    step = 0
    layout = "stereo" if audio.channels_of(src) == 2 else "mono"
    voice_fmt = f"aresample=44100,aformat=sample_fmts=fltp:channel_layouts={layout}"

    def next_path() -> Path:
        nonlocal step
        step += 1
        return dst.with_name(f"{dst.stem}-{step}.wav")

    if bg is not None:
        dur = audio.duration_of(current)
        gain = voice_db + settings.background_level_db - _level_db(bg)
        out = next_path()
        graph = (f"[1:a]{_music_chain(gain, dur, 2.0, 3.0, layout)}[m];[0:a]{voice_fmt},asplit=2[v1][v2];"
                 f"[m][v2]sidechaincompress=threshold=0.04:ratio=5:attack=40:release=600[duck];"
                 f"[v1][duck]amix=inputs=2:duration=first:normalize=0[out]")
        ffmpeg.run_ffmpeg(["-i", str(current), "-stream_loop", "-1", "-i", str(bg), "-filter_complex", graph,
                           "-map", "[out]", "-t", f"{dur:.3f}", "-c:a", "pcm_f32le", str(out)], dur, None, cancel)
        current = out
    if intro is not None:
        length = min(audio.duration_of(intro) or 20.0, 25.0)
        gain = voice_db - 3.0 - _level_db(intro)
        out = next_path()
        graph = (f"[1:a]{_music_chain(gain, length, 0.3, min(3.0, length / 3), layout)},apad=pad_dur=0.8[i];"
                 f"[0:a]{voice_fmt}[v];[i][v]concat=n=2:v=0:a=1[out]")
        ffmpeg.run_ffmpeg(["-i", str(current), "-i", str(intro), "-filter_complex", graph, "-map", "[out]",
                           "-c:a", "pcm_f32le", str(out)], None, None, cancel)
        offset = length + 0.8
        current = out
    if outro is not None:
        length = min(audio.duration_of(outro) or 30.0, 40.0)
        gain = voice_db - 3.0 - _level_db(outro)
        out = next_path()
        graph = (f"[0:a]{voice_fmt},apad=pad_dur=0.6[v];[1:a]{_music_chain(gain, length, 1.0, min(4.0, length / 3), layout)}[o];"
                 f"[v][o]concat=n=2:v=0:a=1[out]")
        ffmpeg.run_ffmpeg(["-i", str(current), "-i", str(outro), "-filter_complex", graph, "-map", "[out]",
                           "-c:a", "pcm_f32le", str(out)], None, None, cancel)
        current = out
    return current, offset


# ---------------------------------------------------------------------------------------
# Sous-titres et vidéo
# ---------------------------------------------------------------------------------------
def _ts(t: float, sep: str = ",") -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s_ = divmod(rem, 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s_, ms = s_ + 1, 0
    return f"{h:02d}:{m:02d}:{s_:02d}{sep}{ms:03d}"


def _wrap_cue(text: str, width: int = 42) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def split_cues(cues: list[tuple[float, float, str]], max_chars: int = 84) -> list[tuple[float, float, str]]:
    """Coupe les passages longs en sous-titres lisibles (durée répartie selon la longueur)."""
    out = []
    for start, end, text in cues:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if len(text) <= max_chars:
            out.append((start, end, text))
            continue
        pieces = re.split(r"(?<=[.!?…;:,])\s+", text)
        groups, cur = [], ""
        for p in pieces:
            if cur and len(cur) + 1 + len(p) > max_chars:
                groups.append(cur)
                cur = p
            else:
                cur = (cur + " " + p) if cur else p
        if cur:
            groups.append(cur)
        total = sum(len(g) for g in groups) or 1
        t = start
        for g in groups:
            d = (end - start) * len(g) / total
            out.append((t, t + d, g))
            t += d
    return out


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    blocks = []
    for i, (a, b, text) in enumerate(split_cues(cues), 1):
        blocks.append(f"{i}\n{_ts(a)} --> {_ts(b)}\n{_wrap_cue(text)}\n")
    return "\n".join(blocks)


def to_lrc(cues: list[tuple[float, float, str]], title: str, meta: BookMetadata) -> str:
    lines = [f"[ti:{title}]", f"[ar:{meta.author}]", f"[al:{meta.title}]", "[by:PodCast Studio]"]
    for a, _b, text in split_cues(cues):
        m, s_ = divmod(max(0.0, a), 60)
        lines.append(f"[{int(m):02d}:{s_:05.2f}]{text}")
    return "\n".join(lines) + "\n"


def _video_encoder() -> list[str]:
    for name, opts in (("libx264", ["-preset", "veryfast", "-tune", "stillimage", "-crf", "26"]),
                       ("libopenh264", ["-b:v", "1500k"]),
                       ("h264_mf", ["-b:v", "1500k"]),
                       ("mpeg4", ["-q:v", "5"])):
        if ffmpeg.has_encoder(name):
            return ["-c:v", name, *opts]
    return ["-c:v", "mpeg4", "-q:v", "5"]


def make_video(audio_src: Path, target: Path, cover: Path | None, cues: list[tuple[float, float, str]], td: Path,
               duration: float, cancel: threading.Event | None = None) -> Path:
    """Vidéo 1280 × 720 : couverture sur fond flouté, onde sonore animée, sous-titres intégrés."""
    args = []
    if cover and cover.is_file():
        args += ["-loop", "1", "-framerate", "25", "-i", str(cover)]
        graph = ("[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,boxblur=24:2,"
                 "eq=brightness=-0.18[bg];[0:v]scale=-2:440[fg];[bg][fg]overlay=(W-w)/2:50[base];")
    else:
        args += ["-f", "lavfi", "-i", "color=c=0x1d1640:s=1280x720:r=25"]
        graph = "[0:v]null[base];"
    args += ["-i", str(audio_src)]
    graph += ("[1:a]aformat=channel_layouts=mono,showwaves=s=1280x150:mode=cline:rate=25:"
              "colors=0xE9E2FF,format=rgba,colorchannelmixer=aa=0.85[w];"
              "[base][w]overlay=0:H-175:shortest=1,format=yuv420p[v]")
    sub_args: list[str] = []
    if cues:
        srt = td / f"{target.stem}.srt"
        srt.write_text(to_srt(cues), encoding="utf-8")
        args += ["-i", str(srt)]
        sub_args = ["-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=fra"]
    ffmpeg.run_ffmpeg([*args, "-filter_complex", graph, "-map", "[v]", "-map", "1:a", *sub_args,
                       *_video_encoder(), "-r", "25", "-c:a", "aac", "-b:a", "128k", "-shortest",
                       "-movflags", "+faststart", str(target)], duration, None, cancel)
    return target

