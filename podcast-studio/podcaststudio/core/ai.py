"""Assistant IA (DeepSeek) : qui parle, émotions, débit, mots mis en valeur, pauses dramatiques et prononciation
des noms propres.

Le texte du livre n'est jamais réécrit par l'IA : elle renvoie des propositions par paragraphe numéroté,
que l'utilisateur valide et que l'application applique sous forme de balises (« @Marie: », « [triste] »,
« [lent] », « *mot* », « [pause 1.5s] »).
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
from .textproc import (EMOTION_ALIASES, EMOTION_END_RE, EMPHASIS_RE, MARK_RE, NARRATOR_NAMES, PAUSE_RE, SOUND_RE,
                       RATE_ALIASES, RATE_END_RE, VOICE_END_RE, VOICE_SWITCH_RE, parse_prefixes, rate_name)

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
            "Accept": "application/json", "User-Agent": f"PodCastStudio/{__version__}"})
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

    def chat_json(self, system: str, user: str, max_tokens: int = 8000, temperature: float = 0.2) -> dict:
        model = self.pick_model()
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
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
_TRAILING_PAUSE_RE = re.compile(r"\s*" + PAUSE_RE.pattern + r"\s*$", re.IGNORECASE)
MIN_PAUSE_MS = 300
MAX_PAUSE_MS = 4000


def pause_tag(ms: int) -> str:
    return f"[pause {ms / 1000:g}s]"
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
    pause_ms: int = 0  # balise « [pause …] » en fin de paragraphe (retirée de ``body``)
    rate: str = ""  # débit : « lent », « rapide »… (balise retirée de ``body``)

    @property
    def emphasis(self) -> list[str]:
        return [m.group(1) for m in EMPHASIS_RE.finditer(self.body)]

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
        if (in_voice or s.startswith(("#", "%%")) or PAUSE_RE.fullmatch(s) or EMOTION_END_RE.match(s)
                or SOUND_RE.fullmatch(s) or MARK_RE.fullmatch(s)
                or RATE_END_RE.match(s) or not parse_prefixes(s)[0]):
            continue
        lead = raw[:len(raw) - len(raw.lstrip())]
        trail = raw[len(raw.rstrip()):]
        body = raw.strip()
        speaker = None
        m = _SPEAKER_TAG_RE.match(body)
        if m:
            speaker = m.group(1).strip()
            body = body[m.end():]
        rest, emotion, rate, _e, seen_rate = parse_prefixes(body)
        body = body[len(body) - len(rest):] if rest else ""  # balises d'émotion et de débit retirées
        rate_label = rate_name(rate) if seen_rate else ""
        if not any(ch.isalnum() for ch in body):
            continue
        pause_ms = 0
        pm = _TRAILING_PAUSE_RE.search(body)
        if pm and any(ch.isalnum() for ch in body[:pm.start()]):
            value, unit = pm.group(1), pm.group(2)
            v = float(value.replace(",", "."))
            pause_ms = int(v if unit and unit.lower() == "ms" else v * 1000)
            body = body[:pm.start()]
        paras.append(Paragraph(len(paras) + 1, i, lead, body, trail, speaker, emotion, pause_ms, rate_label))
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
    pause_ms: int = 0  # pause après le paragraphe (0 = aucune)
    old_pause_ms: int = 0
    rate: str = ""  # « lent », « très lent », « rapide », « très rapide » ou vide
    old_rate: str = ""
    emphasis: list[str] = field(default_factory=list)  # mots à mettre en valeur (*mot*)
    old_emphasis: list[str] = field(default_factory=list)


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


PROMPT_HEAD = "Tu aides à préparer un livre audio. On te donne des paragraphes numérotés d'un chapitre de livre."

RULE_SPEAKER = ("Pour chaque paragraphe qui contient une réplique (des paroles prononcées, entre guillemets ou après "
                "un tiret de dialogue), indique le personnage qui parle. Déduis-le du texte (« dit Marie », "
                "alternance des répliques, contexte). Utilise toujours le même nom pour un même personnage, de "
                "préférence son prénom.")
RULE_EMOTION = ("Pour les paragraphes dont le ton est nettement marqué, indique une émotion parmi : joyeux, triste, "
                "colère, chuchoté, calme, peur, excité. Sois sobre : la plupart des paragraphes sont neutres.")
RULE_RATE = ("Débit : pour un passage qui gagne à être lu plus lentement (moment grave ou solennel, émotion, "
             "description contemplative) ou plus vite (action, poursuite, panique), indique « debit » : lent, "
             "très lent, rapide ou très rapide. Sois sobre : la plupart des paragraphes gardent le débit normal.")
RULE_EMPHASIS = ("Mise en valeur : dans une phrase forte, indique dans « insister » le mot (ou les deux ou trois "
                 "mots) sur lequel un comédien appuierait, recopié exactement comme dans le texte. Rare : un "
                 "paragraphe sur dix au plus, deux mots au maximum par paragraphe.")
RULE_PAUSE = ("Comme un comédien qui lit le livre, repère les moments forts où un silence s'impose après le "
              "paragraphe : révélation, chute d'une scène, phrase choc, suspense avant un rebondissement, moment "
              "d'émotion. Indique alors « pause » en secondes (de 0.5 à 3). Sois très sobre : une pause tous les 8 "
              "à 15 paragraphes au plus, jamais au milieu d'un échange rapide de répliques.")
RULE_NAMES = ("Relève les noms propres inventés ou étrangers dont la lecture française n'est pas évidente, avec "
              "une orthographe simple qui se lit correctement en français (exemple : « Siobhan » → « Chivône »).")


def system_prompt(pauses: bool = True, prosody: bool = True) -> str:
    rules = [RULE_SPEAKER, RULE_EMOTION]
    example = '"n": 3, "personnage": "Marie", "emotion": "colère"'
    fields = ["un personnage", "une émotion"]
    if prosody:
        rules += [RULE_RATE, RULE_EMPHASIS]
        example += ', "debit": "lent", "insister": ["jamais"]'
        fields += ["un débit", "des mots à mettre en valeur"]
    if pauses:
        rules.append(RULE_PAUSE)
        example += ', "pause": 1.5'
        fields.append("une pause")
    rules.append(RULE_NAMES)
    numbered = "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    wanted = ", ".join(fields[:-1]) + " ou " + fields[-1]
    return (f"{PROMPT_HEAD}\n\n{numbered}\n\n"
            "N'invente jamais de texte et ne recopie pas les paragraphes. Réponds uniquement avec un objet JSON de "
            "cette forme :\n"
            f'{{"paragraphes": [{{{example}}}],\n'
            ' "personnages": [{"nom": "Marie", "genre": "F"}],\n'
            ' "noms": [{"mot": "Siobhan", "prononciation": "Chivône"}]}\n'
            f"Dans « paragraphes », ne mets que ceux qui ont {wanted} (null pour un champ vide). "
            "« genre » vaut F, M ou ?. Laisse les listes vides s'il n'y a rien.")


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


def _clean_pause(value) -> int:
    try:
        seconds = float(str(value).replace(",", ".").strip().rstrip("s"))
    except (TypeError, ValueError):
        return 0
    if seconds <= 0:
        return 0
    return int(round(min(max(seconds * 1000, MIN_PAUSE_MS), MAX_PAUSE_MS) / 100) * 100)


def _clean_rate(value) -> str:
    if not isinstance(value, str):
        return ""
    factor = RATE_ALIASES.get(value.strip().lower().strip("[]"))
    return rate_name(factor) if factor else ""


def _clean_emphasis(value, body: str) -> list[str]:
    """Mots à mettre en valeur réellement présents dans le paragraphe (deux au plus)."""
    items = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    out: list[str] = []
    for w in items:
        if not isinstance(w, str):
            continue
        w = w.strip().strip("*\"«» ")
        if (w and len(w) <= 40 and len(w.split()) <= 3 and w not in out
                and re.search(r"(?<![\w*])" + re.escape(w) + r"(?![\w*])", body)):
            out.append(w)
    return out[:2]


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
             progress: ProgressCb | None = None, cancel=None, pauses: bool = True,
             prosody: bool = True) -> Annotation:
    """Analyse un chapitre et renvoie les propositions (le texte n'est pas modifié)."""
    _parts, paras = split_paragraphs(text)
    result = Annotation()
    if not paras:
        return result
    characters: dict[str, str] = {n: "?" for n in (known_characters or [])}
    names: dict[str, str] = {}
    found: dict[int, dict] = {}
    by_number = {p.number: p for p in paras}
    prompt = system_prompt(pauses, prosody)
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
        data = client.chat_json(prompt, "\n".join(lines))
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
            pause = _clean_pause(item.get("pause")) if pauses else 0
            rate = _clean_rate(item.get("debit", item.get("rate"))) if prosody else ""
            emphasis = (_clean_emphasis(item.get("insister", item.get("emphasis")), by_number[n].body)
                        if prosody else [])
            if speaker or emotion or pause or rate or emphasis:
                found[n] = {"speaker": speaker, "emotion": emotion, "pause": pause, "rate": rate,
                            "emphasis": emphasis}
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
        f = found[p.number]
        new_speaker = f["speaker"] or p.speaker
        new_emotion = f["emotion"] or p.emotion
        new_pause = f["pause"] or p.pause_ms
        new_rate = f["rate"] or p.rate
        new_emphasis = f["emphasis"] or p.emphasis
        if (new_speaker, new_emotion, new_pause, new_rate, new_emphasis) == (
                p.speaker, p.emotion, p.pause_ms, p.rate, p.emphasis):
            continue
        excerpt = p.flat if len(p.flat) <= 160 else p.flat[:157] + "…"
        result.paragraphs.append(ParagraphSuggestion(p.number, excerpt, new_speaker, new_emotion,
                                                     p.speaker, p.emotion, pause_ms=new_pause,
                                                     old_pause_ms=p.pause_ms, rate=new_rate, old_rate=p.rate,
                                                     emphasis=new_emphasis, old_emphasis=p.emphasis))
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
        rate = _clean_rate(s.rate) if s.rate else ""
        prefix = ((f"@{speaker}: " if speaker else "") + (f"[{emotion}] " if emotion else "")
                  + (f"[{rate}] " if rate else ""))
        pause = max(0, min(int(s.pause_ms or 0), MAX_PAUSE_MS))
        suffix = f" {pause_tag(pause)}" if pause else ""
        body = p.body.rstrip()
        if sorted(s.emphasis or []) != sorted(p.emphasis):
            body = mark_emphasis(EMPHASIS_RE.sub(lambda m: m.group(1), body), s.emphasis or [])
        parts[p.part] = p.lead + prefix + body + suffix + p.trail
    return "".join(parts)


def mark_emphasis(body: str, words: list[str]) -> str:
    """Entoure d'astérisques la première occurrence de chaque mot (« *jamais* »)."""
    for w in words:
        w = w.strip().strip("*")
        if not w:
            continue
        m = re.search(r"(?<![\w*])" + re.escape(w) + r"(?![\w*])", body)
        if m:
            body = body[:m.start()] + "*" + m.group(0) + "*" + body[m.end():]
    return body


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


# =======================================================================================
# Podcast : écriture du dialogue et notes d'épisode
# =======================================================================================
DIALOGUE_STYLES = {
    "conversation": "conversation détendue et chaleureuse entre amis passionnés",
    "interview": "interview : l'animateur pose les questions, l'invité développe ses réponses",
    "debat": "débat courtois où chacun défend un point de vue argumenté",
    "recit": "récit à plusieurs voix, vivant, avec suspense",
    "info": "émission d'information claire, rythmée et factuelle",
}
WORDS_PER_MINUTE = 150


@dataclass
class DialogueLine:
    speaker: str
    text: str
    emotion: str = ""


def dialogue_prompt(hosts: list[tuple[str, str, str]], style: str, minutes: float, language: str = "fr") -> str:
    people = "\n".join(f"- {name} ({role}){' : ' + bio if bio else ''}" for name, role, bio in hosts)
    emotions = ", ".join(sorted(set(EMOTION_ALIASES.values()) - {""}))
    words = int(minutes * WORDS_PER_MINUTE)
    lang = "français" if language.startswith("fr") else language
    return f"""Tu es scénariste de podcasts. Écris en {lang} le script parlé d'un épisode à partir des notes de
l'utilisateur. Style : {DIALOGUE_STYLES.get(style, style)}.
Participants (utilise exactement ces noms) :
{people}
Règles :
- environ {words} mots au total (≈ {minutes:g} minutes d'écoute) ;
- phrases courtes et naturelles à l'oral, relances, réactions brèves (« Exactement ! », « Ah oui ? ») ;
- l'animateur ouvre l'épisode (accueil, sujet) et le conclut (résumé, au revoir) ;
- n'invente pas de faits précis absents des notes (chiffres, citations, dates) ;
- pas de didascalies, pas de bruitages, pas de markdown : uniquement ce qui est dit.
Réponds en JSON : {{"title": "titre accrocheur de l'épisode", "description": "2 à 4 phrases pour les notes
d'épisode", "lines": [{{"speaker": "Nom", "text": "réplique", "emotion": ""}}]}}.
« emotion » est vide ou l'une de : {emotions}."""


def write_dialogue(notes: str, hosts: list[tuple[str, str, str]], client: DeepSeekClient, minutes: float = 10,
                   style: str = "conversation", language: str = "fr") -> tuple[str, str, list[DialogueLine]]:
    """Script d'épisode : (titre, description, répliques). ``hosts`` : [(nom, rôle, présentation)]."""
    if not notes.strip():
        raise AIError("Écrivez d'abord le sujet ou les notes de l'épisode.")
    if not hosts:
        raise AIError("Ajoutez au moins un animateur dans la page Animateurs.")
    names = {n.strip().lower(): n for n, _r, _b in hosts}
    data = client.chat_json(dialogue_prompt(hosts, style, minutes, language), notes[:20000],
                            max_tokens=8000, temperature=0.8)
    lines: list[DialogueLine] = []
    for raw in data.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        text = " ".join(str(raw.get("text") or "").split())
        speaker = names.get(str(raw.get("speaker") or "").strip().lower())
        if not text:
            continue
        if speaker is None:  # nom inconnu : la réplique revient au premier animateur
            speaker = hosts[0][0]
        lines.append(DialogueLine(speaker, text, _clean_emotion(raw.get("emotion"))))
    if not lines:
        raise AIError("DeepSeek n'a pas renvoyé de dialogue. Réessayez ou précisez vos notes.")
    return str(data.get("title") or "").strip(), str(data.get("description") or "").strip(), lines


def dialogue_to_script(lines: list[DialogueLine]) -> str:
    """Répliques au format du script (« @Nom: [émotion] texte »), une par paragraphe."""
    out = []
    for ln in lines:
        tag = f"[{ln.emotion}] " if ln.emotion else ""
        out.append(f"@{ln.speaker}: {tag}{ln.text}")
    return "\n\n".join(out)


def episode_notes(title: str, script: str, client: DeepSeekClient) -> tuple[str, str]:
    """Titre et description (notes d'épisode) proposés à partir du script."""
    clean = re.sub(r"\[[^\]\n]*\]|^@[^:\n]{1,40}:", "", script, flags=re.M)
    data = client.chat_json(
        "Tu rédiges les notes d'épisode d'un podcast. Réponds en JSON : {\"title\": \"titre court et accrocheur "
        "(70 caractères maximum)\", \"description\": \"3 à 5 phrases qui donnent envie d'écouter, sans "
        "inventer d'information\"}. Langue : celle du script.",
        f"Titre actuel : {title}\n\nScript :\n{clean[:15000]}", max_tokens=1200, temperature=0.6)
    return str(data.get("title") or title).strip(), str(data.get("description") or "").strip()


def pick_trailer(passages: list[tuple[int, str, str, float]], client: DeepSeekClient, seconds: float = 30) -> list[int]:
    """Numéros des passages qui font la meilleure bande-annonce. ``passages`` : [(n, épisode, texte, durée)]."""
    if not passages:
        return []
    listing = "\n".join(f"[{n}] ({ep}, {d:.0f} s) {text}" for n, ep, text, d in passages)[:24000]
    system = f"""Tu montes la bande-annonce d'un podcast. Choisis des passages qui, enchaînés dans l'ordre que tu
donnes, durent environ {seconds:.0f} secondes au total, donnent envie d'écouter (accroche, moment drôle ou
surprenant, question intrigante) et se comprennent sans contexte. Évite les salutations et les passages qui
dévoilent une conclusion. Réponds en JSON : {{"passages": [numéros dans l'ordre de montage]}}."""
    data = client.chat_json(system, listing, max_tokens=600, temperature=0.5)
    valid = {n: d for n, _e, _t, d in passages}
    out: list[int] = []
    total = 0.0
    for n in data.get("passages") or []:
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if n in valid and n not in out and total + valid[n] <= seconds + 6:
            out.append(n)
            total += valid[n]
    if not out:
        raise AIError("DeepSeek n'a pas choisi de passages. Réessayez.")
    return out


def rewrite_line(text: str, style: str, client: DeepSeekClient, speaker: str = "", context: str = "") -> str:
    """Nouvelle version d'une réplique : plus courte, plus drôle, plus naturelle, plus simple, plus enthousiaste."""
    styles = {"courte": "plus courte (deux fois moins de mots), sans perdre l'idée",
              "drole": "plus drôle, avec une pointe d'humour bienveillant",
              "naturelle": "plus naturelle à l'oral, comme dans une vraie conversation",
              "simple": "plus simple, avec des mots du quotidien",
              "enthousiaste": "plus enthousiaste et énergique"}
    who = f" prononcée par {speaker}" if speaker else ""
    system = (f"Tu réécris une réplique de podcast{who}, {styles.get(style, style)}. Garde la même langue et le même "
              "sens, n'ajoute pas de faits. Pas de guillemets ni de didascalies. "
              'Réponds en JSON : {"replique": "..."}')
    user = (f"Contexte (répliques autour) :\n{context[:3000]}\n\n" if context else "") + f"Réplique : {text}"
    data = client.chat_json(system, user, max_tokens=800, temperature=0.8)
    new = " ".join(str(data.get("replique") or data.get("text") or "").split()).strip('«»" ')
    if not new:
        raise AIError("DeepSeek n'a pas proposé de nouvelle version. Réessayez.")
    return new


def propose_chapters(script: str, client: DeepSeekClient, max_chapters: int = 8) -> list[tuple[int, str]]:
    """Chapitres de l'épisode : [(paragraphe où il commence, titre court)]."""
    _parts, paras = split_paragraphs(script)
    if len(paras) < 3:
        raise AIError("L'épisode est trop court pour être découpé en chapitres.")
    numbered = "\n".join(f"[{p.number}] {(p.speaker + ' : ') if p.speaker else ''}{p.flat}" for p in paras)[:24000]
    system = f"""Découpe cet épisode de podcast en 3 à {max_chapters} chapitres qui suivent les changements de sujet.
Le premier chapitre commence au paragraphe 1. Titres courts (2 à 6 mots), sans numéro.
Réponds en JSON : {{"chapitres": [{{"debut": numéro, "titre": "..."}}]}}."""
    data = client.chat_json(system, numbered, max_tokens=1200, temperature=0.3)
    valid = {p.number for p in paras}
    out: list[tuple[int, str]] = []
    for c in data.get("chapitres") or data.get("chapters") or []:
        if not isinstance(c, dict):
            continue
        try:
            n = int(c.get("debut") or c.get("start"))
        except (TypeError, ValueError):
            continue
        title = " ".join(str(c.get("titre") or c.get("title") or "").split())[:60]
        if n in valid and title and all(n != m for m, _ in out):
            out.append((n, title))
    if not out:
        raise AIError("DeepSeek n'a pas proposé de chapitres. Réessayez.")
    return sorted(out)


def apply_chapters(script: str, chapters: list[tuple[int, str]]) -> str:
    """Insère « [chapitre: Titre] » avant les paragraphes choisis (les anciens repères sont retirés)."""
    script = re.sub(r"(?m)^[ \t]*\[\s*chapitre\s*[:=][^\]\n]*\][ \t]*\n?(?:[ \t]*\n)?", "", script)
    parts, paras = split_paragraphs(script)
    wanted = dict(chapters)
    for p in paras:
        if p.number in wanted:
            parts[p.part] = p.lead + f"[chapitre: {wanted[p.number]}]\n\n" + parts[p.part][len(p.lead):]
    return "".join(parts)
