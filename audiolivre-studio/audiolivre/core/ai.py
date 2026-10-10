"""Assistant IA (DeepSeek) : qui parle, émotions et prononciation des noms propres.

Le texte du livre n'est jamais réécrit par l'IA : elle renvoie des propositions par paragraphe numéroté,
que l'utilisateur valide et que l'application applique sous forme de balises (« @Marie: », « [triste] »).
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .. import __version__
from .models import LexiconEntry, VoiceProfile
from .textproc import (EMOTION_ALIASES, EMOTION_END_RE, EMOTION_RE, NARRATOR_NAMES, PAUSE_RE, VOICE_END_RE,
                       VOICE_SWITCH_RE)

DEFAULT_BASE_URL = "https://api.deepseek.com"
# Modèles rapides et peu coûteux d'abord ; la liste réelle est lue sur le compte de l'utilisateur.
PREFERRED_MODELS = ("deepseek-v4-flash", "deepseek-flash", "deepseek-chat", "deepseek-v4", "deepseek-v4-pro")
BATCH_CHARS = 12000
BATCH_PARAGRAPHS = 60
CONTEXT_PARAGRAPHS = 3

ProgressCb = Callable[[str], None]


class AIError(RuntimeError):
    pass


def _http_message(code: int, detail: str = "") -> str:
    if code == 401:
        return "Clé API DeepSeek refusée : vérifiez-la dans Paramètres → Assistant IA."
    if code == 402:
        return "Solde DeepSeek insuffisant : rechargez votre compte sur platform.deepseek.com."
    if code == 429:
        return "DeepSeek reçoit trop de demandes : réessayez dans un moment."
    if code >= 500:
        return "Le service DeepSeek est momentanément indisponible : réessayez plus tard."
    return f"DeepSeek a refusé la demande (erreur {code}). {detail}".strip()


# ---------------------------------------------------------------------------------------
# Client (API compatible OpenAI)
# ---------------------------------------------------------------------------------------
class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, model: str = "", timeout: float = 180):
        if not api_key.strip():
            raise AIError("Aucune clé API DeepSeek : ajoutez-la dans Paramètres → Assistant IA.")
        self.api_key = api_key.strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self._thinking_param = True

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": f"AudioLivreStudio/{__version__}"})
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        last: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    return json.loads(resp.read().decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
                except Exception:
                    detail = ""
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    last = exc
                    continue
                err = AIError(_http_message(exc.code, detail))
                err.code = exc.code  # type: ignore[attr-defined]
                err.detail = detail  # type: ignore[attr-defined]
                raise err from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                if attempt < 2:
                    time.sleep(2)
                    continue
        raise AIError(f"Impossible de joindre DeepSeek ({last}). Vérifiez votre connexion Internet.")

    def list_models(self) -> list[str]:
        data = self._request("GET", "/models")
        return [str(m.get("id")) for m in data.get("data", []) if m.get("id")]

    def pick_model(self) -> str:
        if self.model:
            return self.model
        available = self.list_models()
        for name in PREFERRED_MODELS:
            if name in available:
                self.model = name
                return name
        usable = [m for m in available if "reasoner" not in m]
        if not usable:
            raise AIError("Aucun modèle DeepSeek disponible sur ce compte.")
        self.model = usable[0]
        return self.model

    def chat_json(self, system: str, user: str, max_tokens: int = 8000) -> dict:
        model = self.pick_model()
        body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        for attempt in range(3):
            payload = dict(body)
            if self._thinking_param:
                payload["thinking"] = {"type": "disabled"}  # réponse directe, plus rapide et moins chère
            try:
                data = self._request("POST", "/chat/completions", payload)
            except AIError as exc:
                if getattr(exc, "code", 0) == 400 and self._thinking_param:
                    self._thinking_param = False  # modèle qui ne connaît pas ce réglage
                    continue
                raise
            try:
                content = data["choices"][0]["message"].get("content") or ""
            except (KeyError, IndexError, TypeError):
                content = ""
            parsed = parse_json(content)
            if parsed is not None:
                return parsed
        raise AIError("DeepSeek n'a pas renvoyé de réponse exploitable. Réessayez.")


def parse_json(content: str) -> dict | None:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            value = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def client_from_settings() -> DeepSeekClient:
    from ..config import settings
    from .secrets import unprotect

    s = settings()
    return DeepSeekClient(unprotect(s.get("ai_key", "")), s.get("ai_base_url") or DEFAULT_BASE_URL,
                          s.get("ai_model", ""))


# ---------------------------------------------------------------------------------------
# Paragraphes du manuscrit
# ---------------------------------------------------------------------------------------
_SPEAKER_TAG_RE = re.compile(r"^@([^:\n]{1,40}):[ \t]*")
_SPLIT_RE = re.compile(r"(\n[ \t]*\n|\n(?=#)|\n(?=@)|\n(?=\[)|(?<=\])\n)")


@dataclass
class Paragraph:
    number: int  # numéro envoyé à l'IA (1, 2, 3…)
    part: int  # position dans la liste des morceaux du texte
    lead: str  # espaces de début conservés
    body: str  # texte sans balises de personnage ni d'émotion (retours à la ligne conservés)
    trail: str  # espaces de fin conservés
    speaker: str | None
    emotion: str

    @property
    def flat(self) -> str:
        return " ".join(self.body.split())


def split_paragraphs(text: str) -> tuple[list[str], list[Paragraph]]:
    """Découpe le texte en morceaux (pour le reconstituer à l'identique) et en paragraphes annotables."""
    parts = _SPLIT_RE.split(text.replace("\r\n", "\n"))
    paras: list[Paragraph] = []
    in_voice = False
    for i in range(0, len(parts), 2):
        raw = parts[i]
        s = raw.strip()
        if not s:
            continue
        vm = VOICE_SWITCH_RE.match(s)
        if vm:
            in_voice = vm.group(1).strip().lower() not in NARRATOR_NAMES
            continue
        if VOICE_END_RE.match(s):
            in_voice = False
            continue
        standalone = EMOTION_RE.match(s)
        if (in_voice or s.startswith(("#", "%%")) or PAUSE_RE.fullmatch(s) or EMOTION_END_RE.match(s)
                or (standalone and not s[standalone.end():].strip())):
            continue
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        body = raw.strip()
        speaker = None
        m = _SPEAKER_TAG_RE.match(body)
        if m:
            speaker = m.group(1).strip()
            body = body[m.end():]
        emotion = ""
        em = EMOTION_RE.match(body)
        if em:
            emotion = EMOTION_ALIASES.get(em.group(1).lower(), "")
            body = body[em.end():]
        if not any(ch.isalnum() for ch in body):
            continue
        paras.append(Paragraph(len(paras) + 1, i, lead, body, trail, speaker, emotion))
    return parts, paras


# ---------------------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------------------
@dataclass
class ParagraphSuggestion:
    number: int
    excerpt: str
    speaker: str | None
    emotion: str
    old_speaker: str | None = None
    old_emotion: str = ""
    accepted: bool = True


@dataclass
class NameSuggestion:
    word: str
    say: str
    accepted: bool = True


@dataclass
class Annotation:
    paragraphs: list[ParagraphSuggestion] = field(default_factory=list)
    names: list[NameSuggestion] = field(default_factory=list)
    characters: dict[str, str] = field(default_factory=dict)  # nom -> F | M | ?
    model: str = ""


SYSTEM_PROMPT = """Tu aides à préparer un livre audio. On te donne des paragraphes numérotés d'un chapitre de livre.

1. Pour chaque paragraphe qui contient une réplique (des paroles prononcées, entre guillemets ou après un tiret \
de dialogue), indique le personnage qui parle. Déduis-le du texte (« dit Marie », alternance des répliques, \
contexte). Utilise toujours le même nom pour un même personnage, de préférence son prénom.
2. Pour les paragraphes dont le ton est nettement marqué, indique une émotion parmi : joyeux, triste, colère, \
chuchoté, calme, peur, excité. Sois sobre : la plupart des paragraphes sont neutres.
3. Relève les noms propres inventés ou étrangers dont la lecture française n'est pas évidente, avec une \
orthographe simple qui se lit correctement en français (exemple : « Siobhan » → « Chivône »).

N'invente jamais de texte et ne recopie pas les paragraphes. Réponds uniquement avec un objet JSON de cette forme :
{"paragraphes": [{"n": 3, "personnage": "Marie", "emotion": "colère"}],
 "personnages": [{"nom": "Marie", "genre": "F"}],
 "noms": [{"mot": "Siobhan", "prononciation": "Chivône"}]}
Dans « paragraphes », ne mets que ceux qui ont un personnage ou une émotion (null pour un champ vide). \
« genre » vaut F, M ou ?. Laisse les listes vides s'il n'y a rien."""


def _clean_name(name) -> str | None:
    if not isinstance(name, str):
        return None
    name = re.sub(r"[:\n\r@\[\]]", " ", name)
    name = " ".join(name.split())[:40].strip()
    if not name or name.lower() in NARRATOR_NAMES or name.lower() in ("null", "none", "aucun", "inconnu", "?"):
        return None
    return name


def _clean_emotion(value) -> str:
    if not isinstance(value, str):
        return ""
    return EMOTION_ALIASES.get(value.strip().lower().strip("[]"), "")


def _batches(paras: list[Paragraph]) -> list[list[Paragraph]]:
    out: list[list[Paragraph]] = []
    cur: list[Paragraph] = []
    size = 0
    for p in paras:
        if cur and (size + len(p.flat) > BATCH_CHARS or len(cur) >= BATCH_PARAGRAPHS):
            out.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += len(p.flat)
    if cur:
        out.append(cur)
    return out


def annotate(text: str, client: DeepSeekClient, known_characters: list[str] | None = None,
             progress: ProgressCb | None = None, cancel=None) -> Annotation:
    """Analyse un chapitre et renvoie les propositions (le texte n'est pas modifié)."""
    _parts, paras = split_paragraphs(text)
    result = Annotation()
    if not paras:
        return result
    characters: dict[str, str] = {n: "?" for n in (known_characters or [])}
    names: dict[str, str] = {}
    found: dict[int, tuple[str | None, str]] = {}
    batches = _batches(paras)
    for bi, batch in enumerate(batches):
        if cancel is not None and cancel.is_set():
            raise AIError("Analyse annulée.")
        if progress:
            progress(f"Analyse du texte par DeepSeek… ({bi + 1}/{len(batches)})")
        first = batch[0].number
        context = paras[max(0, first - 1 - CONTEXT_PARAGRAPHS):first - 1]
        lines = []
        if characters:
            lines.append("Personnages déjà connus (réutilise exactement ces noms) : " + ", ".join(characters) + ".")
        if context:
            lines.append("\nContexte (ne pas annoter) :")
            lines += [f"[{p.number}] {p.flat}" for p in context]
        lines.append("\nParagraphes à annoter :")
        lines += [f"[{p.number}] {p.flat}" for p in batch]
        data = client.chat_json(SYSTEM_PROMPT, "\n".join(lines))
        numbers = {p.number for p in batch}
        for item in data.get("paragraphes") or data.get("paragraphs") or []:
            if not isinstance(item, dict):
                continue
            try:
                n = int(item.get("n"))
            except (TypeError, ValueError):
                continue
            if n not in numbers:
                continue
            speaker = _clean_name(item.get("personnage", item.get("speaker")))
            emotion = _clean_emotion(item.get("emotion"))
            if speaker or emotion:
                found[n] = (speaker, emotion)
                if speaker and speaker not in characters:
                    characters[speaker] = "?"
        for item in data.get("personnages") or data.get("characters") or []:
            if isinstance(item, dict):
                name = _clean_name(item.get("nom", item.get("name")))
                gender = str(item.get("genre", item.get("gender", "?")) or "?").strip().upper()[:1]
                if name:
                    characters[name] = gender if gender in ("F", "M") else characters.get(name, "?")
        for item in data.get("noms") or data.get("names") or []:
            if isinstance(item, dict):
                word = str(item.get("mot", item.get("word", "")) or "").strip()
                say = str(item.get("prononciation", item.get("say", "")) or "").strip()
                if word and say and word.lower() != say.lower() and len(word) <= 40 and word in text:
                    names.setdefault(word, say)
    for p in paras:
        if p.number not in found:
            continue
        speaker, emotion = found[p.number]
        new_speaker = speaker or p.speaker
        new_emotion = emotion or p.emotion
        if new_speaker == p.speaker and new_emotion == p.emotion:
            continue
        excerpt = p.flat if len(p.flat) <= 160 else p.flat[:157] + "…"
        result.paragraphs.append(ParagraphSuggestion(p.number, excerpt, new_speaker, new_emotion,
                                                     p.speaker, p.emotion))
    used = {s.speaker for s in result.paragraphs if s.speaker}
    result.characters = {n: g for n, g in characters.items() if n in used}
    result.names = [NameSuggestion(w, s) for w, s in names.items()]
    result.model = client.model
    return result


def apply_suggestions(text: str, suggestions: list[ParagraphSuggestion]) -> str:
    """Ajoute les balises acceptées ; tout le reste du texte est conservé à l'identique."""
    parts, paras = split_paragraphs(text)
    wanted = {s.number: s for s in suggestions if s.accepted}
    for p in paras:
        s = wanted.get(p.number)
        if s is None:
            continue
        speaker = _clean_name(s.speaker) if s.speaker else None
        emotion = _clean_emotion(s.emotion) if s.emotion else ""
        prefix = (f"@{speaker}: " if speaker else "") + (f"[{emotion}] " if emotion else "")
        parts[p.part] = p.lead + prefix + p.body + p.trail
    return "".join(parts)


def lexicon_entries(names: list[NameSuggestion], existing: list[LexiconEntry]) -> list[LexiconEntry]:
    known = {e.pattern.lower() for e in existing}
    return [LexiconEntry(pattern=n.word, replacement=n.say, case_sensitive=True, note="Proposé par l'assistant IA")
            for n in names if n.accepted and n.word.lower() not in known]


# Voix Microsoft françaises (et variantes de hauteur) attribuées aux nouveaux personnages
VOICE_POOL = {
    "F": [("fr-FR-DeniseNeural", "Denise", 0), ("fr-FR-VivienneMultilingualNeural", "Vivienne", 0),
          ("fr-FR-EloiseNeural", "Eloise", 0), ("fr-FR-DeniseNeural", "Denise", 8),
          ("fr-FR-VivienneMultilingualNeural", "Vivienne", -6), ("fr-FR-DeniseNeural", "Denise", -8)],
    "M": [("fr-FR-HenriNeural", "Henri", 0), ("fr-FR-RemyMultilingualNeural", "Rémy", 0),
          ("fr-FR-HenriNeural", "Henri", -10), ("fr-FR-RemyMultilingualNeural", "Rémy", 8),
          ("fr-FR-HenriNeural", "Henri", 8), ("fr-FR-RemyMultilingualNeural", "Rémy", -8)],
}


def voices_for_characters(characters: dict[str, str], taken: list[VoiceProfile]) -> dict[str, VoiceProfile]:
    """Propose une voix Microsoft distincte à chaque personnage (en évitant les voix déjà utilisées)."""
    used = {(v.engine_voice, int(round(float(v.params.get("pitch", 0))))) for v in taken if v.engine == "edge"}
    out: dict[str, VoiceProfile] = {}
    toggle = "F"
    for name, gender in characters.items():
        if gender not in ("F", "M"):
            gender, toggle = toggle, ("M" if toggle == "F" else "F")
        pool = VOICE_POOL[gender]
        choice = next((c for c in pool if (c[0], c[2]) not in used), pool[len(out) % len(pool)])
        used.add((choice[0], choice[2]))
        vid, base, pitch = choice
        label = base + (f" {pitch:+d} Hz" if pitch else "")
        out[name] = VoiceProfile(name=f"{name} ({label})", engine="edge", engine_voice=vid, language="fr",
                                 gender=gender, params={"pitch": pitch} if pitch else {},
                                 description=f"Voix proposée par l'assistant IA pour « {name} »")
    return out
