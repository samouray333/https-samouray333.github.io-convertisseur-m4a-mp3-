"""Catalogue des langues et choix automatique des voix natives.

- ``LANGUAGES`` : environ 80 langues avec leur nom en français, leur nom natif, leurs accents régionaux
  (variantes « es-MX », « en-GB »…), leur écriture et le système de translittération utilisé.
- ``EDGE_CATALOG`` : voix neuronales Microsoft gratuites, par variante régionale (liste de secours ; la liste
  en ligne, mise en cache par le moteur, fait foi quand elle est disponible).
- voix hors ligne de secours : Kokoro (voix intégrées par langue) et XTTS-v2 (voix intégrées multilingues).

Les voix natives ne sont pas enregistrées dans la bibliothèque : ce sont des profils « virtuels » dont
l'identifiant décrit la voix (``native:edge:es-MX-DaliaNeural``, ``native:kokoro:ef_dora``,
``native:xtts:Ana Florence``), reconstruits à la demande par :func:`native_profile`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .models import VoiceProfile


@dataclass(frozen=True)
class Language:
    code: str  # code court (ISO 639-1, ou 639-3 quand il n'existe pas) : « es », « fil », « yue »
    name: str  # nom en français
    native: str  # nom dans la langue elle-même
    locales: tuple[tuple[str, str], ...]  # variantes régionales (code de la voix Microsoft, libellé)
    script: str = "latin"  # latin | cyrillic | arabic | hebrew | greek | devanagari | han | kana | hangul | thai…
    translit: str = ""  # translittération proposée sous le texte (« pinyin », « romaji »…)
    rtl: bool = False
    family: str = ""

    @property
    def default_locale(self) -> str:
        return self.locales[0][0] if self.locales else self.code

    @property
    def non_latin(self) -> bool:
        return self.script != "latin"

    def locale_label(self, locale: str) -> str:
        return next((lbl for loc, lbl in self.locales if loc.lower() == locale.lower()), "")


def _L(code, name, native, locales, script="latin", translit="", rtl=False, family=""):
    return Language(code, name, native, tuple(locales), script, translit, rtl, family)


# Variantes : la première est l'accent proposé par défaut.
_LANGS = [
    _L("en", "Anglais", "English", [("en-GB", "Royaume-Uni"), ("en-US", "États-Unis"), ("en-AU", "Australie"),
                                    ("en-IN", "Inde"), ("en-CA", "Canada"), ("en-IE", "Irlande"),
                                    ("en-NZ", "Nouvelle-Zélande"), ("en-ZA", "Afrique du Sud"), ("en-SG", "Singapour"),
                                    ("en-PH", "Philippines"), ("en-KE", "Kenya"), ("en-NG", "Nigeria"),
                                    ("en-TZ", "Tanzanie"), ("en-HK", "Hong Kong")]),
    _L("es", "Espagnol", "Español", [("es-ES", "Espagne"), ("es-MX", "Mexique"), ("es-AR", "Argentine"),
                                     ("es-CO", "Colombie"), ("es-CL", "Chili"), ("es-PE", "Pérou"),
                                     ("es-VE", "Venezuela"), ("es-CU", "Cuba"), ("es-US", "États-Unis"),
                                     ("es-UY", "Uruguay"), ("es-BO", "Bolivie"), ("es-EC", "Équateur"),
                                     ("es-CR", "Costa Rica"), ("es-DO", "Rép. dominicaine"), ("es-GT", "Guatemala"),
                                     ("es-HN", "Honduras"), ("es-NI", "Nicaragua"), ("es-PA", "Panama"),
                                     ("es-PR", "Porto Rico"), ("es-PY", "Paraguay"), ("es-SV", "Salvador"),
                                     ("es-GQ", "Guinée équatoriale")]),
    _L("pt", "Portugais", "Português", [("pt-PT", "Portugal"), ("pt-BR", "Brésil")]),
    _L("de", "Allemand", "Deutsch", [("de-DE", "Allemagne"), ("de-AT", "Autriche"), ("de-CH", "Suisse")]),
    _L("it", "Italien", "Italiano", [("it-IT", "Italie")]),
    _L("fr", "Français", "Français", [("fr-FR", "France"), ("fr-CA", "Canada"), ("fr-BE", "Belgique"),
                                      ("fr-CH", "Suisse")]),
    _L("nl", "Néerlandais", "Nederlands", [("nl-NL", "Pays-Bas"), ("nl-BE", "Belgique (flamand)")]),
    _L("sv", "Suédois", "Svenska", [("sv-SE", "Suède")]),
    _L("nb", "Norvégien", "Norsk bokmål", [("nb-NO", "Norvège")]),
    _L("da", "Danois", "Dansk", [("da-DK", "Danemark")]),
    _L("fi", "Finnois", "Suomi", [("fi-FI", "Finlande")]),
    _L("is", "Islandais", "Íslenska", [("is-IS", "Islande")]),
    _L("pl", "Polonais", "Polski", [("pl-PL", "Pologne")]),
    _L("cs", "Tchèque", "Čeština", [("cs-CZ", "Tchéquie")]),
    _L("sk", "Slovaque", "Slovenčina", [("sk-SK", "Slovaquie")]),
    _L("hu", "Hongrois", "Magyar", [("hu-HU", "Hongrie")]),
    _L("ro", "Roumain", "Română", [("ro-RO", "Roumanie")]),
    _L("bg", "Bulgare", "Български", [("bg-BG", "Bulgarie")], "cyrillic", "translittération latine"),
    _L("el", "Grec", "Ελληνικά", [("el-GR", "Grèce")], "greek", "translittération latine"),
    _L("hr", "Croate", "Hrvatski", [("hr-HR", "Croatie")]),
    _L("sr", "Serbe", "Српски", [("sr-RS", "Serbie")], "cyrillic", "latinica"),
    _L("bs", "Bosnien", "Bosanski", [("bs-BA", "Bosnie-Herzégovine")]),
    _L("sl", "Slovène", "Slovenščina", [("sl-SI", "Slovénie")]),
    _L("mk", "Macédonien", "Македонски", [("mk-MK", "Macédoine du Nord")], "cyrillic", "translittération latine"),
    _L("sq", "Albanais", "Shqip", [("sq-AL", "Albanie")]),
    _L("uk", "Ukrainien", "Українська", [("uk-UA", "Ukraine")], "cyrillic", "translittération latine"),
    _L("ru", "Russe", "Русский", [("ru-RU", "Russie")], "cyrillic", "translittération latine"),
    _L("et", "Estonien", "Eesti", [("et-EE", "Estonie")]),
    _L("lv", "Letton", "Latviešu", [("lv-LV", "Lettonie")]),
    _L("lt", "Lituanien", "Lietuvių", [("lt-LT", "Lituanie")]),
    _L("ca", "Catalan", "Català", [("ca-ES", "Catalogne")]),
    _L("eu", "Basque", "Euskara", [("eu-ES", "Pays basque")]),
    _L("gl", "Galicien", "Galego", [("gl-ES", "Galice")]),
    _L("cy", "Gallois", "Cymraeg", [("cy-GB", "Pays de Galles")]),
    _L("ga", "Irlandais", "Gaeilge", [("ga-IE", "Irlande")]),
    _L("mt", "Maltais", "Malti", [("mt-MT", "Malte")]),
    _L("tr", "Turc", "Türkçe", [("tr-TR", "Turquie")]),
    _L("az", "Azéri", "Azərbaycanca", [("az-AZ", "Azerbaïdjan")]),
    _L("kk", "Kazakh", "Қазақша", [("kk-KZ", "Kazakhstan")], "cyrillic", "translittération latine"),
    _L("uz", "Ouzbek", "Oʻzbekcha", [("uz-UZ", "Ouzbékistan")]),
    _L("mn", "Mongol", "Монгол", [("mn-MN", "Mongolie")], "cyrillic", "translittération latine"),
    _L("ka", "Géorgien", "ქართული", [("ka-GE", "Géorgie")], "georgian", "translittération latine"),
    _L("hy", "Arménien", "Հայերեն", [("hy-AM", "Arménie")], "armenian", "translittération latine"),
    _L("ar", "Arabe", "العربية", [("ar-SA", "Arabie saoudite"), ("ar-EG", "Égypte"), ("ar-MA", "Maroc"),
                                  ("ar-DZ", "Algérie"), ("ar-TN", "Tunisie"), ("ar-LB", "Liban"), ("ar-SY", "Syrie"),
                                  ("ar-JO", "Jordanie"), ("ar-IQ", "Irak"), ("ar-AE", "Émirats arabes unis"),
                                  ("ar-KW", "Koweït"), ("ar-QA", "Qatar"), ("ar-BH", "Bahreïn"), ("ar-OM", "Oman"),
                                  ("ar-YE", "Yémen"), ("ar-LY", "Libye")], "arabic", "translittération latine",
       rtl=True),
    _L("he", "Hébreu", "עברית", [("he-IL", "Israël")], "hebrew", "translittération latine", rtl=True),
    _L("fa", "Persan", "فارسی", [("fa-IR", "Iran")], "arabic", "translittération latine", rtl=True),
    _L("ps", "Pachto", "پښتو", [("ps-AF", "Afghanistan")], "arabic", "translittération latine", rtl=True),
    _L("ur", "Ourdou", "اردو", [("ur-PK", "Pakistan"), ("ur-IN", "Inde")], "arabic", "translittération latine",
       rtl=True),
    _L("hi", "Hindi", "हिन्दी", [("hi-IN", "Inde")], "devanagari", "translittération latine (IAST simplifiée)"),
    _L("bn", "Bengali", "বাংলা", [("bn-BD", "Bangladesh"), ("bn-IN", "Inde")], "bengali", "translittération latine"),
    _L("ta", "Tamoul", "தமிழ்", [("ta-IN", "Inde"), ("ta-LK", "Sri Lanka"), ("ta-SG", "Singapour"),
                                 ("ta-MY", "Malaisie")], "tamil", "translittération latine"),
    _L("te", "Télougou", "తెలుగు", [("te-IN", "Inde")], "telugu", "translittération latine"),
    _L("mr", "Marathi", "मराठी", [("mr-IN", "Inde")], "devanagari", "translittération latine"),
    _L("gu", "Gujarati", "ગુજરાતી", [("gu-IN", "Inde")], "gujarati", "translittération latine"),
    _L("pa", "Pendjabi", "ਪੰਜਾਬੀ", [("pa-IN", "Inde")], "gurmukhi", "translittération latine"),
    _L("kn", "Kannada", "ಕನ್ನಡ", [("kn-IN", "Inde")], "kannada", "translittération latine"),
    _L("ml", "Malayalam", "മലയാളം", [("ml-IN", "Inde")], "malayalam", "translittération latine"),
    _L("si", "Cingalais", "සිංහල", [("si-LK", "Sri Lanka")], "sinhala", "translittération latine"),
    _L("ne", "Népalais", "नेपाली", [("ne-NP", "Népal")], "devanagari", "translittération latine"),
    _L("th", "Thaï", "ไทย", [("th-TH", "Thaïlande")], "thai", "translittération latine (RTGS)"),
    _L("lo", "Lao", "ລາວ", [("lo-LA", "Laos")], "lao", "translittération latine"),
    _L("km", "Khmer", "ខ្មែរ", [("km-KH", "Cambodge")], "khmer", "translittération latine"),
    _L("my", "Birman", "မြန်မာ", [("my-MM", "Birmanie")], "myanmar", "translittération latine"),
    _L("vi", "Vietnamien", "Tiếng Việt", [("vi-VN", "Viêt Nam")]),
    _L("id", "Indonésien", "Bahasa Indonesia", [("id-ID", "Indonésie")]),
    _L("ms", "Malais", "Bahasa Melayu", [("ms-MY", "Malaisie")]),
    _L("fil", "Filipino", "Filipino", [("fil-PH", "Philippines")]),
    _L("jv", "Javanais", "Basa Jawa", [("jv-ID", "Indonésie")]),
    _L("su", "Soundanais", "Basa Sunda", [("su-ID", "Indonésie")]),
    _L("zh", "Chinois mandarin", "中文（普通话）", [("zh-CN", "Chine (mandarin)"), ("zh-TW", "Taïwan (mandarin)"),
                                                ("zh-CN-liaoning", "Chine (dialecte du Liaoning)"),
                                                ("zh-CN-shaanxi", "Chine (dialecte du Shaanxi)")],
       "han", "pinyin"),
    _L("yue", "Chinois cantonais", "粵語", [("zh-HK", "Hong Kong")], "han", "jyutping"),
    _L("ja", "Japonais", "日本語", [("ja-JP", "Japon")], "kana", "romaji"),
    _L("ko", "Coréen", "한국어", [("ko-KR", "Corée du Sud")], "hangul", "romanisation révisée"),
    _L("sw", "Swahili", "Kiswahili", [("sw-KE", "Kenya"), ("sw-TZ", "Tanzanie")]),
    _L("am", "Amharique", "አማርኛ", [("am-ET", "Éthiopie")], "ethiopic", "translittération latine"),
    _L("so", "Somali", "Soomaali", [("so-SO", "Somalie")]),
    _L("zu", "Zoulou", "isiZulu", [("zu-ZA", "Afrique du Sud")]),
    _L("af", "Afrikaans", "Afrikaans", [("af-ZA", "Afrique du Sud")]),
]
LANGUAGES: dict[str, Language] = {lang.code: lang for lang in _LANGS}

# Autres façons d'écrire une langue dans une balise : [cn], [jp], [kr], [no], [tl], [gr]…
ALIASES = {
    "no": "nb", "nn": "nb", "tl": "fil", "jp": "ja", "kr": "ko", "cn": "zh", "gr": "el", "ua": "uk", "dk": "da",
    "se": "sv", "cz": "cs", "iw": "he", "in": "id", "zh-hk": "yue", "zh-yue": "yue", "cantonese": "yue",
    "mandarin": "zh",
}

# Systèmes d'écriture dont les mots ne sont pas séparés par des espaces (découpage et durées différents)
NO_SPACE_SCRIPTS = {"han", "kana", "thai", "lao", "khmer", "myanmar"}


def get(code: str | None) -> Language | None:
    """Langue d'après un code ou une variante : « es », « es-MX », « ES_mx », « jp », « zh-HK »…"""
    if not code:
        return None
    c = code.strip().replace("_", "-").lower()
    if c in ALIASES:
        c = ALIASES[c]
    if c in LANGUAGES:
        return LANGUAGES[c]
    for lang in _LANGS:  # variante régionale complète (« zh-hk » → cantonais, « en-gb » → anglais)
        if any(loc.lower() == c for loc, _ in lang.locales):
            return lang
    base = c.split("-")[0]
    base = ALIASES.get(base, base)
    return LANGUAGES.get(base)


def normalize_tag(tag: str) -> tuple[str, str] | None:
    """Balise de langue → (code de la langue, variante régionale ou « »). None si ce n'est pas une langue."""
    lang = get(tag)
    if lang is None:
        return None
    t = tag.strip().replace("_", "-")
    locale = next((loc for loc, _ in lang.locales if loc.lower() == t.lower()), "")
    if not locale and "-" in t:
        # « en-gb » écrit en minuscules, « es-mx »… : on retrouve la variante
        region = t.split("-", 1)[1].lower()
        locale = next((loc for loc, _ in lang.locales if loc.split("-", 1)[-1].lower() == region), "")
    return lang.code, locale


def is_language_tag(tag: str) -> bool:
    return normalize_tag(tag) is not None


def language_name(code: str | None, with_native: bool = False) -> str:
    lang = get(code)
    if lang is None:
        return code or ""
    if with_native and lang.native != lang.name:
        return f"{lang.name} ({lang.native})"
    return lang.name


def locale_name(locale: str) -> str:
    """« es-MX » → « Espagnol (Mexique) »."""
    lang = get(locale)
    if lang is None:
        return locale
    lbl = lang.locale_label(locale)
    return f"{lang.name} ({lbl})" if lbl and len(lang.locales) > 1 else lang.name


def sorted_languages() -> list[Language]:
    import locale as _locale

    try:
        return sorted(_LANGS, key=lambda lang: _locale.strxfrm(lang.name))
    except Exception:
        return sorted(_LANGS, key=lambda lang: lang.name)


def all_locales() -> list[str]:
    return [loc for lang in _LANGS for loc, _ in lang.locales]


# =======================================================================================
# Voix Microsoft (liste de secours) : variante → [(nom court, sexe)]
# =======================================================================================
_EDGE = """
af-ZA Adri F, Willem M | am-ET Mekdes F, Ameha M
ar-AE Fatima F, Hamdan M | ar-BH Laila F, Ali M | ar-DZ Amina F, Ismael M | ar-EG Salma F, Shakir M
ar-IQ Rana F, Bassel M | ar-JO Sana F, Taim M | ar-KW Noura F, Fahed M | ar-LB Layla F, Rami M
ar-LY Iman F, Omar M | ar-MA Mouna F, Jamal M | ar-OM Aysha F, Abdullah M | ar-QA Amal F, Moaz M
ar-SA Zariyah F, Hamed M | ar-SY Amany F, Laith M | ar-TN Reem F, Hedi M | ar-YE Maryam F, Saleh M
az-AZ Banu F, Babek M | bg-BG Kalina F, Borislav M | bn-BD Nabanita F, Pradeep M | bn-IN Tanishaa F, Bashkar M
bs-BA Vesna F, Goran M | ca-ES Joana F, Enric M | cs-CZ Vlasta F, Antonin M | cy-GB Nia F, Aled M
da-DK Christel F, Jeppe M | de-AT Ingrid F, Jonas M | de-CH Leni F, Jan M
de-DE Katja F, Conrad M, Amala F, Killian M, SeraphinaMultilingual F, FlorianMultilingual M
el-GR Athina F, Nestoras M | en-AU Natasha F, William M | en-CA Clara F, Liam M
en-GB Sonia F, Ryan M, Libby F, Thomas M, Maisie F | en-HK Yan F, Sam M | en-IE Emily F, Connor M
en-IN Neerja F, Prabhat M, NeerjaExpressive F | en-KE Asilia F, Chilemba M | en-NG Ezinne F, Abeo M
en-NZ Molly F, Mitchell M | en-PH Rosa F, James M | en-SG Luna F, Wayne M | en-TZ Imani F, Elimu M
en-US Jenny F, Guy M, Aria F, Christopher M, Ava F, Andrew M, Emma F, Brian M, Michelle F, Eric M, Ana F, Roger M,
 Steffan M, AvaMultilingual F, AndrewMultilingual M, EmmaMultilingual F, BrianMultilingual M
en-ZA Leah F, Luke M | es-AR Elena F, Tomas M | es-BO Sofia F, Marcelo M | es-CL Catalina F, Lorenzo M
es-CO Salome F, Gonzalo M | es-CR Maria F, Juan M | es-CU Belkys F, Manuel M | es-DO Ramona F, Emilio M
es-EC Andrea F, Luis M | es-ES Elvira F, Alvaro M, Ximena F | es-GQ Teresa F, Javier M | es-GT Marta F, Andres M
es-HN Karla F, Carlos M | es-MX Dalia F, Jorge M | es-NI Yolanda F, Federico M | es-PA Margarita F, Roberto M
es-PE Camila F, Alex M | es-PR Karina F, Victor M | es-PY Tania F, Mario M | es-SV Lorena F, Rodrigo M
es-US Paloma F, Alonso M | es-UY Valentina F, Mateo M | es-VE Paola F, Sebastian M
et-EE Anu F, Kert M | eu-ES Ainhoa F, Ander M | fa-IR Dilara F, Farid M | fi-FI Noora F, Harri M
fil-PH Blessica F, Angelo M | fr-BE Charline F, Gerard M | fr-CA Sylvie F, Jean M, Antoine M, Thierry M
fr-CH Ariane F, Fabrice M | fr-FR Denise F, Henri M, Eloise F, VivienneMultilingual F, RemyMultilingual M
ga-IE Orla F, Colm M | gl-ES Sabela F, Roi M | gu-IN Dhwani F, Niranjan M | he-IL Hila F, Avri M
hi-IN Swara F, Madhur M | hr-HR Gabrijela F, Srecko M | hu-HU Noemi F, Tamas M | hy-AM Anahit F, Hayk M
id-ID Gadis F, Ardi M | is-IS Gudrun F, Gunnar M | it-IT Elsa F, Diego M, Isabella F, GiuseppeMultilingual M
ja-JP Nanami F, Keita M | jv-ID Siti F, Dimas M | ka-GE Eka F, Giorgi M | kk-KZ Aigul F, Daulet M
km-KH Sreymom F, Piseth M | kn-IN Sapna F, Gagan M | ko-KR SunHi F, InJoon M, HyunsuMultilingual M
lo-LA Keomany F, Chanthavong M | lt-LT Ona F, Leonas M | lv-LV Everita F, Nils M | mk-MK Marija F, Aleksandar M
ml-IN Sobhana F, Midhun M | mn-MN Yesui F, Bataa M | mr-IN Aarohi F, Manohar M | ms-MY Yasmin F, Osman M
mt-MT Grace F, Joseph M | my-MM Nilar F, Thiha M | nb-NO Pernille F, Finn M | ne-NP Hemkala F, Sagar M
nl-BE Dena F, Arnaud M | nl-NL Colette F, Maarten M, Fenna F | pa-IN Vaani F, Ojas M | pl-PL Zofia F, Marek M
ps-AF Latifa F, GulNawaz M | pt-BR Francisca F, Antonio M, ThalitaMultilingual F | pt-PT Raquel F, Duarte M
ro-RO Alina F, Emil M | ru-RU Svetlana F, Dmitry M | si-LK Thilini F, Sameera M | sk-SK Viktoria F, Lukas M
sl-SI Petra F, Rok M | so-SO Ubax F, Muuse M | sq-AL Anila F, Ilir M | sr-RS Sophie F, Nicholas M
su-ID Tuti F, Jajang M | sv-SE Sofie F, Mattias M | sw-KE Zuri F, Rafiki M | sw-TZ Rehema F, Daudi M
ta-IN Pallavi F, Valluvar M | ta-LK Saranya F, Kumar M | ta-MY Kani F, Surya M | ta-SG Venba F, Anbu M
te-IN Shruti F, Mohan M | th-TH Premwadee F, Niwat M | tr-TR Emel F, Ahmet M | uk-UA Polina F, Ostap M
ur-IN Gul F, Salman M | ur-PK Uzma F, Asad M | uz-UZ Madina F, Sardor M | vi-VN HoaiMy F, NamMinh M
zh-CN Xiaoxiao F, Yunxi M, Xiaoyi F, Yunjian M, Yunyang M, Yunxia M | zh-CN-liaoning Xiaobei F
zh-CN-shaanxi Xiaoni F | zh-HK HiuGaai F, WanLung M, HiuMaan F | zh-TW HsiaoChen F, YunJhe M, HsiaoYu F
zu-ZA Thando F, Themba M
"""


def _parse_edge(src: str) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for chunk in " ".join(src.split("\n")).split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        locale, rest = chunk.split(" ", 1)
        for entry in rest.split(","):
            name, gender = entry.strip().rsplit(" ", 1)
            out.setdefault(locale, []).append((f"{locale}-{name}Neural", gender))
    return out


EDGE_CATALOG: dict[str, list[tuple[str, str]]] = _parse_edge(_EDGE)

# Voix « multilingues » de Microsoft : dernier recours pour une langue sans voix native disponible
MULTILINGUAL_FALLBACK = [("en-US-AvaMultilingualNeural", "F"), ("en-US-AndrewMultilingualNeural", "M"),
                         ("en-US-EmmaMultilingualNeural", "F"), ("en-US-BrianMultilingualNeural", "M")]

# =======================================================================================
# Voix hors ligne de secours
# =======================================================================================
# Kokoro : préfixe de la voix → langue (a/b : anglais US/UK, e : espagnol, f : français, h : hindi, i : italien,
# j : japonais, p : portugais du Brésil, z : chinois mandarin)
KOKORO_VOICES: dict[str, list[tuple[str, str]]] = {
    "en-US": [("af_heart", "F"), ("am_michael", "M"), ("af_bella", "F"), ("am_adam", "M"), ("af_nicole", "F"),
              ("am_fenrir", "M"), ("af_sarah", "F"), ("am_puck", "M")],
    "en-GB": [("bf_emma", "F"), ("bm_george", "M"), ("bf_isabella", "F"), ("bm_lewis", "M")],
    "es": [("ef_dora", "F"), ("em_alex", "M"), ("em_santa", "M")],
    "fr": [("ff_siwis", "F")],
    "hi": [("hf_alpha", "F"), ("hm_omega", "M"), ("hf_beta", "F"), ("hm_psi", "M")],
    "it": [("if_sara", "F"), ("im_nicola", "M")],
    "ja": [("jf_alpha", "F"), ("jm_kumo", "M"), ("jf_gongitsune", "F"), ("jf_nezumi", "F")],
    "pt": [("pf_dora", "F"), ("pm_alex", "M"), ("pm_santa", "M")],
    "zh": [("zf_xiaoxiao", "F"), ("zm_yunxi", "M"), ("zf_xiaoyi", "F"), ("zm_yunjian", "M"), ("zf_xiaobei", "F"),
           ("zm_yunyang", "M")],
}
# XTTS-v2 : voix intégrées multilingues (sans enregistrement de référence)
XTTS_LANGS = {"fr", "en", "es", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "ja", "hu", "ko", "hi"}
XTTS_NATIVE_SPEAKERS = [("Ana Florence", "F"), ("Viktor Eka", "M"), ("Claribel Dervla", "F"), ("Damien Black", "M"),
                        ("Sofia Hellen", "F"), ("Craig Gutsy", "M")]


def kokoro_voices_for(code: str, locale: str = "") -> list[tuple[str, str]]:
    lang = get(code)
    if lang is None:
        return []
    if lang.code == "en":
        first = "en-GB" if locale.lower() in ("en-gb", "en-ie", "en-au", "en-nz", "en-za", "en-in") else "en-US"
        other = "en-US" if first == "en-GB" else "en-GB"
        return KOKORO_VOICES[first] + KOKORO_VOICES[other]
    return list(KOKORO_VOICES.get(lang.code, []))


# =======================================================================================
# Voix natives : profils virtuels
# =======================================================================================
NATIVE_PREFIX = "native:"
_VOICE_COLORS = ["#1E88E5", "#FFC107", "#26C6DA", "#FF7043", "#AB47BC", "#66BB6A", "#EC407A", "#8D6E63"]


@dataclass
class NativeVoice:
    id: str  # identifiant de profil virtuel « native:<moteur>:<voix>[:<langue>] »
    engine: str  # edge | kokoro | xtts
    voice: str  # nom de la voix pour le moteur
    language: str  # code de la langue
    locale: str  # variante régionale (« es-MX ») ou « »
    gender: str  # F | M | ""
    label: str = ""
    offline: bool = False
    multilingual: bool = False
    extra: dict = field(default_factory=dict)


def native_id(engine: str, voice: str, language: str = "") -> str:
    return f"{NATIVE_PREFIX}{engine}:{voice}" + (f":{language}" if language and engine != "edge" else "")


def is_native_id(voice_id: str | None) -> bool:
    return bool(voice_id) and str(voice_id).startswith(NATIVE_PREFIX)


def _edge_friendly(short: str) -> str:
    name = short.split("-")[-1].replace("Neural", "")
    return name.replace("Multilingual", " (multilingue)").replace("Expressive", " (expressive)")


def parse_native_id(voice_id: str) -> NativeVoice | None:
    if not is_native_id(voice_id):
        return None
    rest = voice_id[len(NATIVE_PREFIX):]
    engine, _, tail = rest.partition(":")
    if engine == "edge":
        voice = tail
        locale = voice.rsplit("-", 1)[0] if voice.count("-") >= 2 else ""
        lang = get(locale)
        gender = next((g for v, g in EDGE_CATALOG.get(locale, []) if v == voice), "")
        return NativeVoice(voice_id, "edge", voice, lang.code if lang else locale.split("-")[0], locale, gender,
                           _edge_friendly(voice), multilingual="Multilingual" in voice)
    if engine in ("kokoro", "xtts"):
        voice, _, language = tail.rpartition(":") if tail.count(":") else (tail, "", "")
        if not voice:
            voice, language = language, ""
        if engine == "kokoro":
            gender = "F" if voice[1:2] == "f" else "M"
            label = voice.split("_", 1)[-1].capitalize()
        else:
            gender = next((g for n, g in XTTS_NATIVE_SPEAKERS if n == voice), "")
            label = voice
        return NativeVoice(voice_id, engine, voice, language or "", "", gender, label, offline=True)
    return None


def native_profile(voice_id: str) -> VoiceProfile | None:
    """Profil de voix (non enregistré) correspondant à un identifiant de voix native."""
    nv = parse_native_id(voice_id)
    if nv is None:
        return None
    color = _VOICE_COLORS[int(hashlib.sha1(voice_id.encode()).hexdigest()[:4], 16) % len(_VOICE_COLORS)]
    lang_name = language_name(nv.language) if nv.language else ""
    region = locale_name(nv.locale) if nv.locale else lang_name
    if nv.engine == "edge":
        desc = f"Voix native Microsoft · {region}"
        name = f"{nv.label} — {region}"
    elif nv.engine == "kokoro":
        desc = f"Voix hors ligne Kokoro · {lang_name}"
        name = f"{nv.label} (Kokoro) — {lang_name}"
    else:
        desc = f"Voix hors ligne XTTS-v2 · {lang_name}"
        name = f"{nv.label} (XTTS) — {lang_name}"
    v = VoiceProfile(name=name, engine=nv.engine, engine_voice=nv.voice, language=nv.language or "multi",
                     gender=nv.gender, description=desc, color=color, id=voice_id)
    return v


def _live_edge(available: list | None) -> dict[str, list[tuple[str, str]]] | None:
    """Voix Microsoft réellement proposées par le service (liste mise en cache par le moteur), par variante."""
    if available is None:
        return None
    out: dict[str, list[tuple[str, str]]] = {}
    for v in available:
        vid = getattr(v, "id", None) or (v.get("ShortName") if isinstance(v, dict) else None)
        if not vid:
            continue
        loc = getattr(v, "locale", None) or (v.get("Locale") if isinstance(v, dict) else "") or vid.rsplit("-", 1)[0]
        g = getattr(v, "gender", None) or ("F" if isinstance(v, dict) and v.get("Gender") == "Female" else "M")
        out.setdefault(loc, []).append((vid, g))
    return out or None


def edge_voices_for(code: str, locale: str = "", available: list | None = None) -> list[tuple[str, str, str]]:
    """Voix Microsoft natives d'une langue : [(nom court, sexe, variante)], la variante choisie en premier."""
    lang = get(code)
    if lang is None:
        return []
    catalog = _live_edge(available) or EDGE_CATALOG
    locales = [loc for loc, _ in lang.locales]
    if locale:
        wanted = next((loc for loc in locales if loc.lower() == locale.lower()), locale)
        locales = [wanted] + [loc for loc in locales if loc != wanted]
    out = []
    for loc in locales:
        for vid, g in catalog.get(loc, []):
            # les voix multilingues d'une autre langue n'en font pas partie ; celles de la langue, si
            if (vid, g, loc) not in out:
                out.append((vid, g, loc))
    return out


def _alternate(voices: list, gender: str = "") -> list:
    """Ordonne les voix en alternant femme / homme (en commençant par ``gender`` s'il est donné)."""
    fem = [v for v in voices if v[1] == "F"]
    mal = [v for v in voices if v[1] == "M"]
    other = [v for v in voices if v[1] not in ("F", "M")]
    first, second = (mal, fem) if gender == "M" else (fem, mal)
    out = []
    for i in range(max(len(first), len(second))):
        if i < len(first):
            out.append(first[i])
        if i < len(second):
            out.append(second[i])
    return out + other


def native_voices(code: str, locale: str = "", gender: str = "", available: list | None = None,
                  offline: str = "fallback", installed: set[str] | None = None) -> list[NativeVoice]:
    """Voix natives proposées pour une langue, dans l'ordre de préférence.

    - ``locale`` : accent voulu (ses voix viennent en premier, puis les autres accents) ;
    - ``gender`` : « F » ou « M » pour commencer par une voix de femme ou d'homme (alternance ensuite) ;
    - ``available`` : liste des voix Microsoft en ligne (sinon catalogue intégré) ;
    - ``offline`` : « fallback » (voix hors ligne après les voix Microsoft), « prefer » (avant) ou « none » ;
    - ``installed`` : moteurs hors ligne installés (« kokoro », « xtts ») ; None = tous proposés.
    """
    lang = get(code)
    if lang is None:
        return []
    edge = []
    region_first = locale or lang.default_locale
    voices = edge_voices_for(lang.code, region_first, available)
    # voix de la variante choisie, alternées F/M, puis celles des autres variantes
    main = [v for v in voices if v[2].lower() == region_first.lower()]
    rest = [v for v in voices if v[2].lower() != region_first.lower()]
    # les voix « Multilingual » d'une langue passent après ses voix natives classiques
    main.sort(key=lambda v: "Multilingual" in v[0])
    for vid, g, loc in _alternate(main, gender) + _alternate(rest, gender):
        edge.append(NativeVoice(native_id("edge", vid), "edge", vid, lang.code, loc, g, _edge_friendly(vid),
                                multilingual="Multilingual" in vid))
    off: list[NativeVoice] = []
    if offline != "none":
        if installed is None or "kokoro" in installed:
            for vid, g in _alternate(kokoro_voices_for(lang.code, locale), gender):
                off.append(NativeVoice(native_id("kokoro", vid, lang.code), "kokoro", vid, lang.code, "", g,
                                       vid.split("_", 1)[-1].capitalize(), offline=True))
        if lang.code in XTTS_LANGS and (installed is None or "xtts" in installed):
            for name, g in _alternate(XTTS_NATIVE_SPEAKERS, gender):
                off.append(NativeVoice(native_id("xtts", name, lang.code), "xtts", name, lang.code, "", g, name,
                                       offline=True))
    if not edge and offline != "none":  # aucune voix Microsoft : voix multilingues en dernier recours
        for vid, g in _alternate(MULTILINGUAL_FALLBACK, gender):
            off.append(NativeVoice(native_id("edge", vid), "edge", vid, lang.code, "", g, _edge_friendly(vid),
                                   multilingual=True))
    return off + edge if offline == "prefer" and off else edge + off


def offline_alternative(voice_id: str, installed: set[str] | None = None) -> str:
    """Voix hors ligne de même langue et de même sexe pour remplacer une voix Microsoft injoignable."""
    nv = parse_native_id(voice_id)
    if nv is None or nv.engine != "edge" or not nv.language:
        return ""
    for cand in native_voices(nv.language, nv.locale, nv.gender, offline="prefer", installed=installed):
        if cand.offline and (not nv.gender or cand.gender == nv.gender):
            return cand.id
    for cand in native_voices(nv.language, nv.locale, offline="prefer", installed=installed):
        if cand.offline:
            return cand.id
    return ""


def pick_voice(code: str, locale: str = "", gender: str = "", index: int = 0, available: list | None = None,
               offline: str = "fallback", installed: set[str] | None = None) -> str:
    """Identifiant de la ``index``-ième voix native (pour donner des voix différentes à chaque personnage)."""
    voices = native_voices(code, locale, gender, available, offline, installed)
    if gender:
        same = [v for v in voices if v.gender == gender] or voices
        voices = same
    if not voices:
        return ""
    return voices[index % len(voices)].id


# =======================================================================================
# Utilitaires de texte selon la langue
# =======================================================================================
def uses_spaces(code: str | None) -> bool:
    lang = get(code)
    return lang is None or lang.script not in NO_SPACE_SCRIPTS


def speech_units(text: str, code: str | None = None) -> float:
    """Longueur « parlée » approximative d'un texte (en mots), y compris pour le chinois ou le japonais."""
    if uses_spaces(code):
        return float(len(re.findall(r"\w+", text)) or 1)
    chars = len(re.findall(r"\w", text))
    return max(1.0, chars / 2.2)


def repeat_pause_ms(text: str, code: str | None = None, factor: float = 1.6, minimum: int = 1500) -> int:
    """Silence laissé pour répéter : environ 1,6 fois le temps de prononciation du passage (au moins 1,5 s)."""
    seconds = speech_units(text, code) * 0.45 + 0.6
    return max(minimum, int(seconds * factor * 1000))


def describe(code: str | None) -> dict:
    """Résumé d'une langue pour l'assistant IA et l'interface."""
    lang = get(code)
    if lang is None:
        return {}
    return {"code": lang.code, "name": lang.name, "native": lang.native, "script": lang.script,
            "translit": lang.translit, "rtl": lang.rtl, "locales": [loc for loc, _ in lang.locales]}


def catalog_json() -> str:
    return json.dumps([describe(lang.code) for lang in _LANGS], ensure_ascii=False)


# Bonjour dans chaque langue (aperçu des voix natives)
HELLO = {
    "en": "Hello! Nice to meet you.", "es": "¡Hola! Encantado de conocerte.", "pt": "Olá! Muito prazer.",
    "de": "Hallo! Schön, dich kennenzulernen.", "it": "Ciao! Piacere di conoscerti.", "fr": "Bonjour ! Enchanté.",
    "nl": "Hallo! Leuk je te ontmoeten.", "sv": "Hej! Trevligt att träffas.", "nb": "Hei! Hyggelig å møte deg.",
    "da": "Hej! Rart at møde dig.", "fi": "Hei! Hauska tavata.", "is": "Halló! Gaman að kynnast þér.",
    "pl": "Cześć! Miło cię poznać.", "cs": "Ahoj! Rád tě poznávám.", "sk": "Ahoj! Teší ma.",
    "hu": "Szia! Örülök, hogy megismerhetlek.", "ro": "Bună! Încântat de cunoștință.", "bg": "Здравей! Приятно ми е.",
    "el": "Γεια σου! Χαίρω πολύ.", "hr": "Bok! Drago mi je.", "sr": "Здраво! Драго ми је.", "bs": "Zdravo! Drago mi je.",
    "sl": "Živjo! Me veseli.", "mk": "Здраво! Мило ми е.", "sq": "Përshëndetje! Gëzohem që u njohëm.",
    "uk": "Привіт! Радий познайомитися.", "ru": "Привет! Приятно познакомиться.", "et": "Tere! Meeldiv tutvuda.",
    "lv": "Sveiki! Prieks iepazīties.", "lt": "Labas! Malonu susipažinti.", "ca": "Hola! Encantat de conèixer-te.",
    "eu": "Kaixo! Pozten naiz zu ezagutzeaz.", "gl": "Ola! Encantado de coñecerte.", "cy": "Helo! Braf cwrdd â chi.",
    "ga": "Dia duit! Is deas bualadh leat.", "mt": "Bonġu! Għandi pjaċir.", "tr": "Merhaba! Tanıştığıma memnun oldum.",
    "az": "Salam! Tanış olmağıma şadam.", "kk": "Сәлем! Танысқаныма қуаныштымын.", "uz": "Salom! Tanishganimdan xursandman.",
    "mn": "Сайн байна уу! Танилцсандаа баяртай байна.", "ka": "გამარჯობა! სასიამოვნოა.", "hy": "Բարեւ։ Ուրախ եմ ծանոթանալ։",
    "ar": "مرحبا! تشرفت بمعرفتك.", "he": "שלום! נעים מאוד.", "fa": "سلام! از آشنایی با شما خوشوقتم.",
    "ps": "سلام! ستاسو په لیدو خوښ شوم.", "ur": "السلام علیکم! آپ سے مل کر خوشی ہوئی۔", "hi": "नमस्ते! आपसे मिलकर खुशी हुई।",
    "bn": "নমস্কার! আপনার সাথে দেখা হয়ে ভালো লাগলো।", "ta": "வணக்கம்! உங்களை சந்தித்ததில் மகிழ்ச்சி.",
    "te": "నమస్కారం! మిమ్మల్ని కలవడం ఆనందంగా ఉంది.", "mr": "नमस्कार! तुम्हाला भेटून आनंद झाला.",
    "gu": "નમસ્તે! તમને મળીને આનંદ થયો.", "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਤੁਹਾਨੂੰ ਮਿਲ ਕੇ ਖੁਸ਼ੀ ਹੋਈ।",
    "kn": "ನಮಸ್ಕಾರ! ನಿಮ್ಮನ್ನು ಭೇಟಿಯಾಗಿ ಸಂತೋಷವಾಯಿತು.", "ml": "നമസ്കാരം! കണ്ടതിൽ സന്തോഷം.",
    "si": "ආයුබෝවන්! ඔබව හමුවීම සතුටක්.", "ne": "नमस्ते! तपाईंलाई भेटेर खुसी लाग्यो।", "th": "สวัสดีครับ ยินดีที่ได้รู้จัก",
    "lo": "ສະບາຍດີ! ຍິນດີທີ່ໄດ້ຮູ້ຈັກ.", "km": "សួស្តី! រីករាយដែលបានស្គាល់។", "my": "မင်္ဂလာပါ။ တွေ့ရတာ ဝမ်းသာပါတယ်။",
    "vi": "Xin chào! Rất vui được gặp bạn.", "id": "Halo! Senang bertemu denganmu.", "ms": "Helo! Selamat berkenalan.",
    "fil": "Kumusta! Ikinagagalak kitang makilala.", "jv": "Sugeng enjing! Seneng ketemu sampeyan.",
    "su": "Wilujeng enjing! Bungah tepang sareng anjeun.", "zh": "你好！很高兴认识你。", "yue": "你好！好高興識到你。",
    "ja": "こんにちは！はじめまして。", "ko": "안녕하세요! 만나서 반갑습니다.", "sw": "Habari! Nafurahi kukutana nawe.",
    "am": "ሰላም! ስለተዋወቅን ደስ ብሎኛል።", "so": "Salaan! Waan ku faraxsanahay inaan ku barto.",
    "zu": "Sawubona! Ngiyajabula ukukwazi.", "af": "Hallo! Aangename kennis.",
}


def sample_sentence(code: str | None) -> str:
    lang = get(code)
    return HELLO.get(lang.code, "") if lang else ""
