"""Préparation du texte pour la synthèse vocale.

- nettoyage des textes importés (césures, retours à la ligne, notes…)
- balises de mise en scène : ``# Titre``, ``[pause 2s]``, ``@Personnage: réplique``, ``[voix:Nom]``
- normalisation (abréviations, nombres, heures, monnaies, chiffres romains, unités)
- lexique de prononciation personnalisé
- découpage en phrases puis en segments adaptés à chaque moteur
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .models import LexiconEntry

UPPER = "A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸÆŒ"
LOWER = "a-zàâäçéèêëîïôöùûüÿæœ"

# =======================================================================================
# Nettoyage des textes importés
# =======================================================================================
_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)


def clean_imported_text(text: str) -> str:
    """Répare les défauts typiques d'un texte extrait d'un PDF ou d'un traitement de texte."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = text.replace(" ", " ").replace(" ", " ")
    # Ligatures typographiques
    for a, b in (("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"), ("ﬄ", "ffl")):
        text = text.replace(a, b)
    # Césures de fin de ligne : « exem-\nple » -> « exemple »
    text = re.sub(rf"([{LOWER}])-\n\s*([{LOWER}])", r"\1\2", text)
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", s) and s:
            continue  # numéro de page isolé
        out.append(s)
    text = "\n".join(out)
    # Retours à la ligne au milieu d'une phrase (texte justifié/coupé) -> espace
    text = re.sub(rf"(?<=[{LOWER},;])\n(?=[{LOWER}(])", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    # Appels de notes : « mot[12] », « mot¹² »
    text = re.sub(r"(?<=\w)\[\d{1,3}\]", "", text)
    text = re.sub(r"(?<=[\w.,;!?»])[¹²³⁴⁵⁶⁷⁸⁹⁰]+", "", text)
    return text.strip()


# =======================================================================================
# Balises de mise en scène
# =======================================================================================
@dataclass
class ScriptItem:
    kind: str  # heading | para | pause
    text: str = ""
    voice_key: str | None = None  # None = narrateur ; nom de personnage ; "__dialogue__"
    pause_ms: int = 0
    level: int = 0


PAUSE_RE = re.compile(r"\[\s*pause\s*[:= ]?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)?\s*\]", re.IGNORECASE)
VOICE_SWITCH_RE = re.compile(r"^\[\s*(?:voix|voice)\s*[:=]\s*([^\]]+?)\s*\]\s*$", re.IGNORECASE)
VOICE_END_RE = re.compile(r"^\[\s*/\s*(?:voix|voice)\s*\]\s*$", re.IGNORECASE)
CHARACTER_LINE_RE = re.compile(r"^@([^:\n]{1,40}):\s*(.+)$", re.S)
DIALOGUE_START_RE = re.compile(r"^\s*(?:[—–]|-\s|«|“|\")")
NARRATOR_NAMES = {"narrateur", "narratrice", "narrator", "défaut", "defaut", "default"}


def _pause_to_ms(value: str, unit: str | None) -> int:
    v = float(value.replace(",", "."))
    if unit and unit.lower() == "ms":
        return int(v)
    return int(v * 1000)


def parse_script(text: str, detect_dialogues: bool = False) -> list[ScriptItem]:
    """Transforme le texte d'un chapitre en éléments (titres, paragraphes, pauses)."""
    items: list[ScriptItem] = []
    current_voice: str | None = None
    paragraphs = re.split(r"\n\s*\n|\n(?=#)|\n(?=@)|\n(?=\[)|(?<=\])\n", text.replace("\r\n", "\n"))
    for raw in paragraphs:
        para = raw.strip()
        if not para:
            continue
        lines = [ln for ln in para.split("\n") if not ln.strip().startswith("%%")]
        para = " ".join(ln.strip() for ln in lines).strip()
        if not para:
            continue
        m = VOICE_SWITCH_RE.match(para)
        if m:
            name = m.group(1).strip()
            current_voice = None if name.lower() in NARRATOR_NAMES else name
            continue
        if VOICE_END_RE.match(para):
            current_voice = None
            continue
        full_pause = PAUSE_RE.fullmatch(para)
        if full_pause:
            items.append(ScriptItem("pause", pause_ms=_pause_to_ms(full_pause.group(1), full_pause.group(2))))
            continue
        hm = re.match(r"^(#{1,6})\s*(.+)$", para)
        if hm:
            items.append(ScriptItem("heading", hm.group(2).strip(), level=len(hm.group(1))))
            continue
        voice = current_voice
        cm = CHARACTER_LINE_RE.match(para)
        if cm:
            name = cm.group(1).strip()
            voice = None if name.lower() in NARRATOR_NAMES else name
            para = cm.group(2).strip()
        elif voice is None and detect_dialogues and DIALOGUE_START_RE.match(para):
            voice = "__dialogue__"
        # pauses en ligne : on coupe le paragraphe
        pos = 0
        for pm in PAUSE_RE.finditer(para):
            chunk = para[pos:pm.start()].strip()
            if chunk:
                items.append(ScriptItem("para", chunk, voice_key=voice))
            items.append(ScriptItem("pause", pause_ms=_pause_to_ms(pm.group(1), pm.group(2))))
            pos = pm.end()
        rest = para[pos:].strip()
        if rest:
            items.append(ScriptItem("para", rest, voice_key=voice))
    return items


def find_characters(text: str) -> list[str]:
    """Liste des personnages balisés (``@Nom:`` ou ``[voix:Nom]``) dans un texte."""
    names: list[str] = []
    for m in re.finditer(r"^@([^:\n]{1,40}):", text, re.M):
        names.append(m.group(1).strip())
    for m in re.finditer(r"^\[\s*(?:voix|voice)\s*[:=]\s*([^\]]+?)\s*\]", text, re.M | re.I):
        names.append(m.group(1).strip())
    seen: list[str] = []
    for n in names:
        if n.lower() not in NARRATOR_NAMES and n not in seen:
            seen.append(n)
    return seen


# =======================================================================================
# Lexique de prononciation
# =======================================================================================
def apply_lexicon(text: str, entries: Iterable[LexiconEntry]) -> str:
    for e in entries:
        if not e.enabled or not e.pattern:
            continue
        flags = 0 if e.case_sensitive else re.IGNORECASE
        if e.regex:
            pattern = e.pattern
        else:
            pattern = re.escape(e.pattern)
            if e.whole_word:
                pattern = r"(?<!\w)" + pattern + r"(?!\w)"
        try:
            if e.regex:
                text = re.sub(pattern, e.replacement, text, flags=flags)
            else:
                text = re.sub(pattern, lambda _m, r=e.replacement: r, text, flags=flags)
        except re.error:
            continue
    return text


# =======================================================================================
# Nombres
# =======================================================================================
def _n2w(n: int | float, lang: str, to: str = "cardinal") -> str:
    try:
        from num2words import num2words

        return num2words(n, lang=_n2w_lang(lang), to=to)
    except Exception:
        return str(n)


def _n2w_lang(lang: str) -> str:
    lang = (lang or "fr").lower().split("-")[0]
    return {"no": "no", "zh": "zh", "pt": "pt", "fr": "fr"}.get(lang, lang)


def _feminine_fr(words: str) -> str:
    return re.sub(r"\bun$", "une", words)


ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int | None:
    s = s.upper()
    if not s or any(c not in ROMAN_VALUES for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = ROMAN_VALUES[c]
        if i + 1 < len(s) and ROMAN_VALUES[s[i + 1]] > v:
            total -= v
        else:
            total += v
    if int_to_roman(total) != s:
        return None
    return total


def int_to_roman(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, r in vals:
        while n >= v:
            out += r
            n -= v
    return out


FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]

KEYWORDS_ROMAN = (r"chapitre|partie|tome|livre|acte|scène|volume|vol\.|chant|section|"
                  r"chapter|part|book|act|scene|canto|appendix|annexe|épisode|episode|saison|season")

FR_UNITS = {
    "km/h": ("kilomètre-heure", "kilomètres-heure"),
    "km": ("kilomètre", "kilomètres"),
    "kg": ("kilo", "kilos"),
    "cm": ("centimètre", "centimètres"),
    "mm": ("millimètre", "millimètres"),
    "mg": ("milligramme", "milligrammes"),
    "ml": ("millilitre", "millilitres"),
    "°C": ("degré Celsius", "degrés Celsius"),
    "°F": ("degré Fahrenheit", "degrés Fahrenheit"),
    "°": ("degré", "degrés"),
    "m²": ("mètre carré", "mètres carrés"),
    "km²": ("kilomètre carré", "kilomètres carrés"),
    "ha": ("hectare", "hectares"),
    "kWh": ("kilowattheure", "kilowattheures"),
    "Go": ("gigaoctet", "gigaoctets"),
    "Mo": ("mégaoctet", "mégaoctets"),
}
EN_UNITS = {
    "km/h": ("kilometer per hour", "kilometers per hour"),
    "mph": ("mile per hour", "miles per hour"),
    "km": ("kilometer", "kilometers"),
    "kg": ("kilogram", "kilograms"),
    "cm": ("centimeter", "centimeters"),
    "mm": ("millimeter", "millimeters"),
    "lbs": ("pound", "pounds"),
    "lb": ("pound", "pounds"),
    "ft": ("foot", "feet"),
    "°C": ("degree Celsius", "degrees Celsius"),
    "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "°": ("degree", "degrees"),
}

CURRENCIES = {
    "€": {"fr": ("euro", "euros", "centime", "centimes"), "en": ("euro", "euros", "cent", "cents")},
    "$": {"fr": ("dollar", "dollars", "cent", "cents"), "en": ("dollar", "dollars", "cent", "cents")},
    "£": {"fr": ("livre", "livres", "penny", "pence"), "en": ("pound", "pounds", "penny", "pence")},
    "CHF": {"fr": ("franc suisse", "francs suisses", "centime", "centimes"),
            "en": ("Swiss franc", "Swiss francs", "centime", "centimes")},
}


def _to_number(s: str, lang: str) -> float | int:
    s = s.replace(" ", "").replace(" ", "").replace(" ", "")
    if lang == "en":
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    if "." in s:
        return float(s)
    return int(s)


def _decimal_words(num_str: str, lang: str) -> str:
    """« 3,05 » -> « trois virgule zéro cinq »."""
    sep = "." if lang == "en" else ","
    num_str = num_str.replace(" ", "")
    if sep not in num_str:
        return _n2w(int(num_str), lang)
    ip, dp = num_str.split(sep, 1)
    word_sep = {"fr": "virgule", "en": "point", "es": "coma", "it": "virgola", "de": "Komma",
                "pt": "vírgula", "nl": "komma"}.get(lang, "virgule")
    lead = len(dp) - len(dp.lstrip("0"))
    zero = _n2w(0, lang)
    parts = [_n2w(int(ip or "0"), lang), word_sep] + [zero] * lead
    if dp.lstrip("0"):
        parts.append(_n2w(int(dp.lstrip("0")), lang))
    return " ".join(parts)


@dataclass
class NormalizeOptions:
    language: str = "fr"
    numbers: bool = True
    abbreviations: bool = True


# Abréviations (motif -> remplacement). Appliquées dans l'ordre.
FR_ABBREVIATIONS: list[tuple[str, str]] = [
    (r"\bav\.\s?J\.?-C\.?", "avant Jésus-Christ"),
    (r"\bapr\.\s?J\.?-C\.?", "après Jésus-Christ"),
    (r"\bJ\.-C\.", "Jésus-Christ"),
    (r"\bc\.-à-d\.?", "c'est-à-dire"),
    (r"\bc-à-d\.?", "c'est-à-dire"),
    (r"\bp\.\s?ex\.", "par exemple"),
    (r"\bMM\.(?=\s)", "Messieurs"),
    (rf"\bM\.(?=\s+[{UPPER}])", "Monsieur"),
    (r"\bMmes\b\.?", "Mesdames"),
    (r"\bMme\b\.?", "Madame"),
    (r"\bMlles\b\.?", "Mesdemoiselles"),
    (r"\bMlle\b\.?", "Mademoiselle"),
    (rf"\bDr\b\.?(?=\s+[{UPPER}])", "Docteur"),
    (rf"\bPr\b\.?(?=\s+[{UPPER}])", "Professeur"),
    (rf"\bMe\b\.?(?=\s+[{UPPER}])", "Maître"),
    (r"\bMgr\b\.?", "Monseigneur"),
    (rf"\bSte(?=[\s-][{UPPER}])", "Sainte"),
    (rf"\bSt(?=[\s-][{UPPER}])", "Saint"),
    (rf"\betc\.(?=\s*$|\s+[{UPPER}])", "et cetera."),
    (r"\betc\.", "et cetera"),
    (r"\bcf\.", "confer"),
    (r"\benv\.(?=\s*\d)", "environ"),
    (r"\bvol\.(?=\s*\d)", "volume"),
    (r"\bchap\.(?=\s*\d)", "chapitre"),
    (r"\bp\.(?=\s*\d)", "page"),
    (r"\bpp\.(?=\s*\d)", "pages"),
    (r"\bfig\.(?=\s*\d)", "figure"),
    (r"\b[nN]°\s?(?=\d)", "numéro "),
    (r"\bBd\b\.?", "boulevard"),
    (r"\bCie\b", "compagnie"),
    (r"\bsvp\b", "s'il vous plaît"),
    (r"\bSVP\b", "s'il vous plaît"),
    (r"\bt\.q\.", "tel que"),
    (r"\bkm/h\b", "km/h"),
    (r"\s&\s", " et "),
]
EN_ABBREVIATIONS: list[tuple[str, str]] = [
    (r"\bMr\.", "Mister"),
    (r"\bMrs\.", "Missus"),
    (r"\bMs\.", "Miz"),
    (rf"\bDr\.(?=\s+[{UPPER}])", "Doctor"),
    (rf"\bSt\.(?=\s+[{UPPER}])", "Saint"),
    (r"\bProf\.", "Professor"),
    (r"\bJr\.", "Junior"),
    (r"\bSr\.", "Senior"),
    (r"\bvs\.", "versus"),
    (rf"\betc\.(?=\s*$|\s+[{UPPER}])", "et cetera."),
    (r"\betc\.", "et cetera"),
    (r"\be\.g\.", "for example"),
    (r"\bi\.e\.", "that is"),
    (r"\bNo\.(?=\s*\d)", "number"),
    (r"\bp\.(?=\s*\d)", "page"),
    (r"\bch\.(?=\s*\d)", "chapter"),
    (r"\s&\s", " and "),
]


def _replace_currency(text: str, lang: str) -> str:
    base = "en" if lang == "en" else "fr"
    num = r"(\d{1,3}(?:[   ]\d{3})+|\d+)(?:[.,](\d{1,2}))?"
    for sym, names in CURRENCIES.items():
        sg, pl, csg, cpl = names[base]
        esc = re.escape(sym)

        def repl(m, sg=sg, pl=pl, csg=csg, cpl=cpl):
            units = int(re.sub(r"\D", "", m.group(1)))
            cents = m.group(2)
            words = _n2w(units, lang) + " " + (sg if units <= 1 else pl)
            if cents:
                c = int(cents.ljust(2, "0"))
                if c:
                    if base == "en":
                        words += " and " + _n2w(c, lang) + " " + (csg if c == 1 else cpl)
                    elif units == 0:
                        words = _n2w(c, lang) + " " + (csg if c == 1 else cpl)
                    else:
                        words += " " + _n2w(c, lang)
            return words

        text = re.sub(num + r"\s?" + esc, repl, text)  # 12,50 €
        text = re.sub(esc + r"\s?" + num, repl, text)  # $12.50
    return text


def _replace_roman(text: str, lang: str) -> str:
    # Mot-clé + chiffre romain : « Chapitre IV » -> « Chapitre quatre »
    def kw(m):
        val = roman_to_int(m.group(2))
        if val is None:
            return m.group(0)
        return f"{m.group(1)} {_n2w(val, lang)}"

    text = re.sub(rf"\b((?i:{KEYWORDS_ROMAN}))\s+([IVXLCDM]{{1,7}})\b(?![.']\w)", kw, text)

    if lang == "fr":
        # Siècles : « XIXe siècle » -> « dix-neuvième siècle »
        def century(m):
            val = roman_to_int(m.group(1))
            if val is None:
                return m.group(0)
            if val == 1:
                return "premier" if m.group(2) in ("er",) else "première" if m.group(2) in ("re", "ère") else "premier"
            return _n2w(val, lang, "ordinal")

        # Deux lettres minimum (« Ce », « Le » ne sont pas des siècles !)
        text = re.sub(r"\b([IVXLC]{2,7})(er|re|ère|e|ème)\b", century, text)
        text = re.sub(r"\b([IVX])(er|re|e|ème)(?=\s+(?:siècle|millénaire|arrondissement|dynastie|République))",
                      century, text)

    # Souverains : « Louis XIV » -> « Louis quatorze » / « Elizabeth II » -> « Elizabeth the Second »
    def regnal(m):
        name, roman = m.group(1), m.group(2)
        val = roman_to_int(roman)
        if val is None or val > 89:
            return m.group(0)
        if lang == "en":
            if roman == "I":
                return m.group(0)
            return f"{name} the {_n2w(val, 'en', 'ordinal').capitalize()}"
        if lang == "fr":
            return f"{name} {'premier' if val == 1 else _n2w(val, lang)}"
        return f"{name} {_n2w(val, lang)}"

    # Au moins deux lettres : « Monsieur X » ou « Madame L » restent intacts.
    text = re.sub(rf"\b([{UPPER}][{LOWER}]+)\s+([IVXL]{{2,6}})\b(?![-'’]\w)", regnal, text)
    if lang == "fr":
        text = re.sub(rf"\b([{UPPER}][{LOWER}]+)\s+Ier\b", r"\1 premier", text)
        text = re.sub(rf"\b([{UPPER}][{LOWER}]+)\s+Ire\b", r"\1 première", text)
    return text


def _replace_times_dates(text: str, lang: str) -> str:
    if lang == "fr":
        def hm(m):
            h, mi = int(m.group(1)), m.group(2)
            if h > 24:
                return m.group(0)
            hw = _feminine_fr(_n2w(h, lang)) + (" heure" if h <= 1 else " heures")
            if mi and int(mi):
                hw += " " + _feminine_fr(_n2w(int(mi), lang))
            return hw

        text = re.sub(r"\b(\d{1,2})\s?[hH]\s?(\d{2})?\b(?!\w)", hm, text)
        text = re.sub(r"\b(\d{1,2}):(\d{2})\b(?!:)", hm, text)

        def date(m):
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            if not (1 <= d <= 31 and 1 <= mo <= 12):
                return m.group(0)
            day = "premier" if d == 1 else _n2w(d, lang)
            yy = int(y) if len(y) == 4 else 2000 + int(y)
            return f"{day} {FR_MONTHS[mo - 1]} {_n2w(yy, lang)}"

        text = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b", date, text)
        text = re.sub(rf"\b1er\s+({'|'.join(FR_MONTHS)})\b", r"premier \1", text, flags=re.I)
    elif lang == "en":
        def ehm(m):
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 24:
                return m.group(0)
            if mi == 0:
                return f"{_n2w(h, lang)} o'clock"
            if mi < 10:
                return f"{_n2w(h, lang)} oh {_n2w(mi, lang)}"
            return f"{_n2w(h, lang)} {_n2w(mi, lang)}"

        text = re.sub(r"\b(\d{1,2}):(\d{2})\b(?!:)", ehm, text)
    return text


def _replace_units_percent(text: str, lang: str) -> str:
    pct = {"fr": "pour cent", "en": "percent", "es": "por ciento", "it": "per cento",
           "de": "Prozent", "pt": "por cento", "nl": "procent"}.get(lang, "pour cent")
    text = re.sub(r"(\d)\s?%", rf"\1 {pct}", text)
    units = FR_UNITS if lang == "fr" else EN_UNITS if lang == "en" else {}
    for unit in sorted(units, key=len, reverse=True):
        sg, pl = units[unit]

        def repl(m, sg=sg, pl=pl):
            num = m.group(1)
            try:
                val = _to_number(num, lang)
            except ValueError:
                return m.group(0)
            return f"{num} {sg if abs(val) < 2 else pl}"

        text = re.sub(r"(\d+(?:[.,]\d+)?)\s?" + re.escape(unit) + r"(?![\w²])", repl, text)
    return text


def _replace_ordinals(text: str, lang: str) -> str:
    if lang == "fr":
        text = re.sub(r"\b1(?:er|ᵉʳ)\b", "premier", text)
        text = re.sub(r"\b1(?:re|ère|ʳᵉ)\b", "première", text)
        text = re.sub(r"\b(\d+)(?:e|ème|è|ᵉ)\b", lambda m: _n2w(int(m.group(1)), lang, "ordinal"), text)
        text = re.sub(r"\b(\d+)(?:es|èmes)\b", lambda m: _n2w(int(m.group(1)), lang, "ordinal") + "s", text)
    elif lang == "en":
        text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", lambda m: _n2w(int(m.group(1)), lang, "ordinal"), text)
    return text


def _replace_numbers(text: str, lang: str) -> str:
    # Plages d'années « 1914-1918 »
    to_word = {"fr": "à", "en": "to", "es": "a", "it": "a", "de": "bis", "pt": "a", "nl": "tot"}.get(lang, "à")
    text = re.sub(r"\b(1\d{3}|20\d{2})\s?[-–]\s?(1\d{3}|20\d{2})\b", rf"\1 {to_word} \2", text)
    if lang == "en":
        text = re.sub(r"\b(\d{1,3}(?:,\d{3})+)(?!\d)", lambda m: m.group(1).replace(",", ""), text)

        def en_num(m):
            s = m.group(0)
            if "." in s:
                return _decimal_words(s, lang)
            n = int(s)
            if 1100 <= n <= 2099 and len(s) == 4 and not (n % 1000 < 10 and n >= 2000):
                return _n2w(n, lang, "year")
            return _n2w(n, lang)

        text = re.sub(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", en_num, text)
    else:
        # Séparateurs de milliers : 10 000 / 10.000
        text = re.sub(r"(?<![\d,.])(\d{1,3}(?:[   ]\d{3})+)(?![\d])",
                      lambda m: re.sub(r"\D", "", m.group(1)), text)
        text = re.sub(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+)(?![\d,]|\.\d)",
                      lambda m: m.group(1).replace(".", ""), text)
        text = re.sub(r"(?<![\w,])\d+,\d+(?![\w])", lambda m: _decimal_words(m.group(0), lang), text)
        text = re.sub(r"(?<![\w])-(\d+)(?![\w])", lambda m: ("moins " if lang == "fr" else "-") + m.group(1), text)
        text = re.sub(r"(?<![\w.])\d+(?![\w])", lambda m: _n2w(int(m.group(0)), lang), text)
    return text


def _cleanup_symbols(text: str, lang: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = re.sub(r"https?://([^/\s]+)\S*", r"\1", text)
    text = re.sub(r"www\.(\S+?)(?=[\s,;)]|$)", r"\1", text)
    text = re.sub(r"(?<=\w)\[\d{1,3}\]", "", text)
    text = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+(?=[\s.,;!?»]|$)", "", text)
    text = re.sub(r"\(\s*\*+\s*\)|(?<=\w)\*+", "", text)
    text = re.sub(r"[*_~|^`<>{}]", " ", text)
    text = text.replace("…", "...")
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"([!?])\1+", r"\1", text)
    # Tirets de dialogue et incises
    text = re.sub(r"^\s*[—–-]\s+", "", text)
    text = re.sub(r"\s[—–]\s", ", ", text)
    text = re.sub(r"[“”„]", '"', text)
    text = re.sub(r"[‘’‚]", "'", text)
    # Émojis et pictogrammes
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    if lang == "fr":
        text = text.replace("§", " paragraphe ").replace("+", " plus ").replace("=", " égale ")
    elif lang == "en":
        text = text.replace("§", " section ").replace("+", " plus ").replace("=", " equals ")
    return text


def normalize_for_speech(text: str, options: NormalizeOptions | None = None,
                         lexicon: Iterable[LexiconEntry] = ()) -> str:
    """Transforme un texte écrit en texte « parlé », prêt pour la synthèse."""
    opts = options or NormalizeOptions()
    lang = (opts.language or "fr").lower().split("-")[0]
    text = apply_lexicon(text, lexicon)
    text = _cleanup_symbols(text, lang)
    if opts.abbreviations:
        table = FR_ABBREVIATIONS if lang == "fr" else EN_ABBREVIATIONS if lang == "en" else []
        for pattern, repl in table:
            text = re.sub(pattern, repl, text)
    if opts.numbers:
        text = _replace_roman(text, lang)
        text = _replace_currency(text, lang)
        text = _replace_times_dates(text, lang)
        text = _replace_units_percent(text, lang)
        text = _replace_ordinals(text, lang)
        text = _replace_numbers(text, lang)
    text = re.sub(r"\s+([,.])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


# =======================================================================================
# Découpage
# =======================================================================================
_SENT_END = re.compile(r"[.!?…]+[»\"”’)\]]*\s+|(?<=[.!?…])\s*(?=«)")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for m in _SENT_END.finditer(text):
        end = m.end()
        nxt = text[end:end + 1]
        if nxt and not (nxt.isupper() or nxt.isdigit() or nxt in "«\"“—–-([¿¡'"):
            continue
        before = text[start:m.start() + 1].strip()
        # abréviation d'une lettre (« J. Dupont »)
        if re.search(r"(?:^|\s)[A-ZÀ-Ý]\.$", text[max(start, m.start() - 2):m.start() + 1]):
            continue
        if before:
            sentences.append(text[start:end].strip())
            start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts = re.split(r"(?<=[;:,])\s+|\s+(?=[—–]\s)", sentence)
    out: list[str] = []
    buf = ""
    for p in parts:
        if len(p) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            words = p.split(" ")
            cur = ""
            for w in words:
                if cur and len(cur) + 1 + len(w) > max_chars:
                    out.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w) if cur else w
            if cur:
                buf = cur
            continue
        if buf and len(buf) + 1 + len(p) > max_chars:
            out.append(buf)
            buf = p
        else:
            buf = (buf + " " + p) if buf else p
    if buf:
        out.append(buf)
    return out


def chunk_text(text: str, max_chars: int = 250, min_chars: int = 0) -> list[str]:
    """Regroupe les phrases en morceaux ≤ ``max_chars`` sans couper une phrase si possible."""
    chunks: list[str] = []
    buf = ""
    for sent in split_sentences(text):
        for piece in _split_long(sent, max_chars):
            if buf and len(buf) + 1 + len(piece) > max_chars:
                chunks.append(buf)
                buf = piece
            else:
                buf = (buf + " " + piece) if buf else piece
    if buf:
        chunks.append(buf)
    # Évite les tout petits morceaux isolés (« Oui. ») qui sonnent mal
    if min_chars and len(chunks) > 1:
        merged: list[str] = []
        for c in chunks:
            if merged and len(c) < min_chars and len(merged[-1]) + 1 + len(c) <= max_chars * 1.15:
                merged[-1] = merged[-1] + " " + c
            else:
                merged.append(c)
        chunks = merged
    return chunks


def estimate_minutes(text: str, wpm: float = 155.0) -> float:
    return len(text.split()) / max(wpm, 1.0)


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"
