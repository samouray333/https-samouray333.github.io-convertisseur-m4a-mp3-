"""Traduction en ligne par DeepSeek (option) : par lots, avec le contexte et un nombre de caractères à ne pas
dépasser pour chaque réplique, afin que la voix française tienne dans le temps de la voix d'origine."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable

from .. import __version__

DEFAULT_BASE_URL = "https://api.deepseek.com"
# Modèles rapides et peu coûteux d'abord ; la liste réelle est lue sur le compte de l'utilisateur.
PREFERRED_MODELS = ("deepseek-v4-flash", "deepseek-flash", "deepseek-chat", "deepseek-v4", "deepseek-v4-pro")
BATCH_LINES = 40
CONTEXT_LINES = 4

ProgressCb = Callable[[str], None]


class AIError(RuntimeError):
    pass


def _http_message(code: int, detail: str = "") -> str:
    if code == 401:
        return "Clé API DeepSeek refusée : vérifiez-la dans Paramètres → Traduction en ligne."
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
            raise AIError("Aucune clé API DeepSeek : ajoutez-la dans Paramètres → Traduction en ligne.")
        self.api_key = api_key.strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self._thinking_param = True

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": f"Doublys/{__version__}"})
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
# Traduction des répliques
# ---------------------------------------------------------------------------------------
SYSTEM_TRANSLATE = (
    "Tu es adaptateur de doublage professionnel (version française d'une vidéo en {source}). On te donne des "
    "répliques numérotées, dans l'ordre, avec la personne qui parle et un nombre maximal de caractères. "
    "Traduis chaque réplique en français naturel, oral et fidèle au sens, en tenant compte des répliques "
    "voisines (contexte). Respecte impérativement la limite de caractères de chaque réplique (elle correspond au "
    "temps de parole disponible) : reformule plus court si nécessaire, sans rien inventer. Garde le registre "
    "(tutoiement ou vouvoiement cohérent entre les mêmes personnes), les noms propres et les chiffres. "
    "Réponds uniquement en JSON : {\"lines\": [{\"n\": 1, \"fr\": \"…\"}, …]} avec une entrée par réplique "
    "numérotée, sans les répliques de contexte."
)
SYSTEM_SHORTEN = (
    "Tu es adaptateur de doublage. Raccourcis la réplique française pour qu'elle tienne dans la limite de "
    "caractères indiquée, en gardant le sens et un français oral naturel, cohérent avec le contexte. Réponds "
    "uniquement en JSON : {\"fr\": \"…\"}."
)


def _clean_fr(text) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text.strip('"').strip()


def translate_lines(items: list[dict], client: DeepSeekClient, progress: ProgressCb | None = None,
                    cancel=None, source: str = "anglais", glossary: list | None = None) -> list[str]:
    """``items`` : [{"en": texte d'origine, "person": "P1", "budget": 42}, …] → traductions (même ordre)."""
    out = [""] * len(items)
    system = SYSTEM_TRANSLATE.replace("{source}", source)
    if glossary:
        system += (" Glossaire à respecter (terme d'origine → rendu français, à garder tel quel) : "
                   + " ; ".join(f"{a} → {b}" for a, b in glossary) + ".")
    for b0 in range(0, len(items), BATCH_LINES):
        if cancel is not None and cancel.is_set():
            break
        batch = list(range(b0, min(len(items), b0 + BATCH_LINES)))
        before = [i for i in range(max(0, b0 - CONTEXT_LINES), b0)]
        after = [i for i in range(batch[-1] + 1, min(len(items), batch[-1] + 1 + CONTEXT_LINES))]
        parts = []
        if before:
            parts.append("Contexte précédent (ne pas traduire) :")
            parts += [f"- {items[i].get('person', '')}: {items[i]['en']}"
                      + (f" → {out[i]}" if out[i] else "") for i in before]
        parts.append("Répliques à traduire :")
        for k, i in enumerate(batch, 1):
            it = items[i]
            parts.append(f"{k}. [{it.get('person', '')}, max {int(it.get('budget', 80))} caractères] {it['en']}")
        if after:
            parts.append("Contexte suivant (ne pas traduire) :")
            parts += [f"- {items[i].get('person', '')}: {items[i]['en']}" for i in after]
        data = client.chat_json(system, "\n".join(parts), max_tokens=8000)
        got = {}
        for entry in data.get("lines", []) if isinstance(data.get("lines"), list) else []:
            try:
                got[int(entry.get("n"))] = _clean_fr(entry.get("fr"))
            except (TypeError, ValueError, AttributeError):
                continue
        for k, i in enumerate(batch, 1):
            out[i] = got.get(k, "")
        if progress:
            progress(f"{batch[-1] + 1} répliques traduites sur {len(items)}")
    return out


def shorten_line(fr: str, en: str, budget: int, client: DeepSeekClient, before: str = "", after: str = "") -> str:
    user = (f"Contexte avant : {before or '—'}\nContexte après : {after or '—'}\nOriginal : {en}\n"
            f"Réplique française actuelle ({len(fr)} caractères) : {fr}\nLimite : {budget} caractères.")
    data = client.chat_json(SYSTEM_SHORTEN, user, max_tokens=1000)
    text = _clean_fr(data.get("fr"))
    if not text:
        raise AIError("DeepSeek n'a pas proposé de version plus courte.")
    return text


SYSTEM_OCR = (
    "Tu relis des sous-titres anglais lus automatiquement dans l'image d'une vidéo (OCR). Corrige uniquement les "
    "fautes de lecture (lettres confondues comme l/I/1, rn/m, 0/O, mots collés ou coupés, ponctuation), en t'aidant "
    "du contexte et du glossaire de noms propres. Ne reformule pas, ne traduis pas, garde le même sens et le même "
    "nombre de répliques. Réponds uniquement en JSON : {\"lines\": [{\"i\": numéro, \"text\": \"…\"}, …]}."
)


def correct_ocr(texts: list[str], client: DeepSeekClient, glossary: list[str] | None = None,
                progress: ProgressCb | None = None, cancel=None) -> list[str]:
    """Textes OCR corrigés (même ordre, même nombre) ; un texte non rendu reste tel quel."""
    out = list(texts)
    for start in range(0, len(texts), BATCH_LINES):
        if cancel is not None and cancel.is_set():
            break
        part = texts[start:start + BATCH_LINES]
        user = ("Glossaire : " + (", ".join(glossary or []) or "—") + "\n" +
                "\n".join(f"{start + k}: {t}" for k, t in enumerate(part)))
        data = client.chat_json(SYSTEM_OCR, user, max_tokens=4000)
        for item in (data or {}).get("lines", []) if isinstance(data, dict) else []:
            try:
                i = int(item.get("i"))
            except (TypeError, ValueError, AttributeError):
                continue
            text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
            if start <= i < start + len(part) and text:
                out[i] = text
        if progress:
            progress(f"Relecture des sous-titres : {min(len(texts), start + BATCH_LINES)} sur {len(texts)}")
    return out
