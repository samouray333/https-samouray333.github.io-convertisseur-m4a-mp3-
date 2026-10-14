"""Écriture des contes : âge, durée, ton, morale, prénom de l'enfant, puis texte à plusieurs voix.

L'assistant DeepSeek écrit l'histoire sous forme de paragraphes (narrateur ou personnage, émotion, bruitage,
ambiance). L'application la transforme en texte balisé (« @Nom: », « [son: …] », « [ambiance: …] ») que le
parent relit et modifie librement avant la production.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import sounds
from .ai import AIError, DeepSeekClient, _clean_emotion
from .models import Host, VoiceProfile
from .textproc import EMOTION_ALIASES, split_sentences

# ---------------------------------------------------------------------------------------
# Âges, tons, durées
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AgeProfile:
    key: str
    label: str
    wpm: int  # mots par minute à la lecture (plus lent pour les petits)
    sentence_words: int  # longueur moyenne visée d'une phrase
    rules: str


AGES: dict[str, AgeProfile] = {
    "3-5": AgeProfile("3-5", "3 à 5 ans", 105, 9, """- vocabulaire très simple et concret (mots du quotidien, animaux, couleurs, maison) ;
- phrases très courtes (moins de 10 mots), une idée par phrase ;
- répétitions et formules qui reviennent (« Toc, toc, toc ! », « Et il marcha, marcha, marcha… ») ;
- RIEN d'effrayant : pas de méchant menaçant, pas de danger réel, pas de mort, pas de blessure, pas de cris ;
  une petite inquiétude se règle vite et tendrement ;
- beaucoup de bruitages et d'onomatopées amusantes."""),
    "6-8": AgeProfile("6-8", "6 à 8 ans", 120, 13, """- vocabulaire simple ; un mot nouveau est expliqué par le contexte ;
- phrases courtes (moins de 15 mots), dialogues vivants ;
- une aventure avec un petit suspense, jamais angoissant : pas de violence, pas de mort, pas de peur durable ;
- le héros résout le problème grâce à son courage, son idée ou l'entraide."""),
    "9-12": AgeProfile("9-12", "9 à 12 ans", 135, 17, """- vocabulaire riche mais accessible, quelques images poétiques ;
- phrases variées, dialogues avec de l'humour et du caractère ;
- intrigue avec rebondissements et suspense, sans violence explicite ni horreur ;
- des personnages qui doutent, se trompent et grandissent."""),
}

TONES: dict[str, tuple[str, str]] = {
    "drole": ("Drôle", "drôle et pétillante : situations cocasses, jeux de mots simples, personnages rigolos"),
    "aventure": ("Aventure", "aventure : un voyage, une quête, un défi à relever, du rythme"),
    "douce": ("Douce, pour dormir", "douce et apaisante pour s'endormir : rythme lent, images calmes et chaudes, "
                                     "pas de suspense, la fin se passe au lit ou dans un endroit doux, tout le monde "
                                     "s'endort paisiblement"),
    "educative": ("Éducative", "éducative : l'histoire fait découvrir quelque chose de vrai (nature, sciences, "
                               "émotions, vie quotidienne) de façon ludique et exacte"),
}

MIN_MINUTES, MAX_MINUTES = 5, 20
WORDS_PER_PART = 1300  # au-delà, l'histoire est écrite en plusieurs fois (limite de réponse de DeepSeek)

# Mots à éviter pour les plus petits (vérification après écriture)
SCARY_WORDS = ("mort", "morte", "mourir", "meurt", "tuer", "tué", "tue ", "sang", "cadavre", "squelette", "fantôme",
               "terrifi", "horrible", "horreur", "cauchemar", "épouvant", "monstre effrayant", "dévor", "mordre",
               "blessé", "blessure", "hurle", "hurla", "arme", "fusil", "couteau", "poison", "sorcière méchante",
               "abandonné", "perdu pour toujours", "pleurer de peur", "griffes acérées", "crocs")


def age_profile(age: str) -> AgeProfile:
    return AGES.get(age, AGES["6-8"])


def target_words(minutes: float, age: str, bedtime: bool = False) -> int:
    """Nombre de mots pour une histoire de ``minutes`` lue au rythme de cet âge (plus lent le soir)."""
    minutes = max(MIN_MINUTES, min(MAX_MINUTES, float(minutes)))
    wpm = age_profile(age).wpm * (0.88 if bedtime else 1.0)
    return int(round(minutes * wpm / 10.0)) * 10


def check_for_age(text: str, age: str) -> list[str]:
    """Remarques sur un texte trop difficile ou trop effrayant pour l'âge choisi (liste vide : tout va bien)."""
    notes: list[str] = []
    profile = age_profile(age)
    clean = re.sub(r"\[[^\]\n]*\]|^@[^:\n]{1,40}:", " ", text, flags=re.M)
    low = " " + clean.lower() + " "
    if age in ("3-5", "6-8"):
        found = sorted({w.strip() for w in SCARY_WORDS if w in low})
        if found:
            notes.append(f"Mots peut-être effrayants pour {profile.label} : {', '.join(found)}.")
    sentences = [s for s in split_sentences(" ".join(clean.split())) if any(c.isalpha() for c in s)]
    if sentences:
        avg = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg > profile.sentence_words * 1.4:
            notes.append(f"Phrases longues pour {profile.label} ({avg:.0f} mots en moyenne, "
                         f"{profile.sentence_words} conseillés).")
        long_words = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", clean) if len(w) >= 13]
        if age == "3-5" and len(long_words) > max(3, len(sentences) // 8):
            notes.append("Plusieurs mots longs ou difficiles pour les petits : " + ", ".join(sorted(set(long_words))[:6])
                         + ".")
    return notes


# ---------------------------------------------------------------------------------------
# Demande et réponse
# ---------------------------------------------------------------------------------------
@dataclass
class StoryCharacter:
    name: str
    description: str = ""
    kind: str = "character"  # hero | character | animal | magic | villain | parent
    voice: str = "normale"  # aigue | normale | grave
    gender: str = ""  # F | M | ""


@dataclass
class StoryRequest:
    idea: str
    age: str = "6-8"
    minutes: float = 8
    tone: str = "aventure"
    moral: str = ""
    child_name: str = ""  # l'enfant devient le héros de l'histoire
    bedtime: bool = False
    characters: list[StoryCharacter] = field(default_factory=list)  # personnages de la collection (série)
    previous: list[str] = field(default_factory=list)  # titres des histoires précédentes de la série
    language: str = "fr"


@dataclass
class StoryParagraph:
    speaker: str  # "" = narrateur
    text: str
    emotion: str = ""
    sound: str = ""
    ambiance: str = ""  # "" = inchangée ; "fin" = arrêter l'ambiance


@dataclass
class Story:
    title: str
    summary: str
    characters: list[StoryCharacter]
    paragraphs: list[StoryParagraph]
    moral: str = ""

    @property
    def words(self) -> int:
        return sum(len(p.text.split()) for p in self.paragraphs)


def _sound_names() -> str:
    return ", ".join(k for k in sounds.BUILTIN_LABELS if k not in ("virgule", "generique", "transition", "ding",
                                                                     "applaudissements", "suspense", "roulement"))


def system_prompt(req: StoryRequest, words: int, part: int = 1, parts: int = 1) -> str:
    profile = age_profile(req.age)
    tone = "douce" if req.bedtime else req.tone
    tone_text = TONES.get(tone, TONES["aventure"])[1]
    emotions = ", ".join(sorted(set(EMOTION_ALIASES.values()) - {""}))
    hero = ""
    if req.child_name.strip():
        hero = (f"\n- le héros (ou l'héroïne) s'appelle {req.child_name.strip()} : c'est l'enfant qui écoute, "
                "il ou elle doit pouvoir s'y reconnaître ; il parle avec ce prénom exact comme nom de personnage ;")
    cast = ""
    if req.characters:
        cast = "\nPersonnages de la série (garde leur nom et leur caractère, tu peux en ajouter) :\n" + "\n".join(
            f"- {c.name} : {c.description or c.kind}" for c in req.characters)
    if req.previous:
        cast += "\nHistoires précédentes de la série (n'en répète pas l'intrigue) : " + "; ".join(req.previous[-8:])
    moral = f"\n- la morale de l'histoire, à faire comprendre sans la réciter : « {req.moral.strip()} » ;" \
        if req.moral.strip() else ""
    bedtime = ("\n- histoire du soir : phrases lentes et berçantes, la dernière scène est calme, le héros s'endort ; "
               "termine par une phrase douce qui souhaite bonne nuit ;") if req.bedtime else ""
    lang = "français" if req.language.startswith("fr") else req.language
    split = ""
    if parts > 1:
        split = (f"\nL'histoire est écrite en {parts} parties ; écris maintenant la partie {part} sur {parts} "
                 f"(≈ {words} mots pour cette partie)."
                 + (" Termine cette partie à un moment de suspense léger, sans conclure." if part < parts else
                    " Cette partie conclut l'histoire."))
    first = ('"title": "titre court et joli", "summary": "2 phrases qui donnent envie d\'écouter", '
             '"characters": [{"name": "Nom", "description": "qui il est, son caractère", "kind": "hero|character|'
             'animal|magic|villain|parent", "voice": "aigue|normale|grave", "gender": "F|M"}], ') if part == 1 else ""
    return f"""Tu es un auteur de contes audio pour enfants. Écris en {lang} une histoire originale à écouter, pour
des enfants de {profile.label}, à partir de l'idée du parent. Ton : {tone_text}.
Règles d'écriture pour cet âge :
{profile.rules}
Règles générales :
- environ {words} mots au total{' pour cette partie' if parts > 1 else ''} (texte du narrateur et dialogues) ;
- un narrateur raconte ; les personnages parlent en dialogues vivants (au moins un tiers du texte) ;{hero}{moral}{bedtime}
- jamais de contenu inapproprié pour un enfant ; bienveillance, humour tendre, fin heureuse et rassurante ;
- pas de markdown, pas de titres de chapitres, pas de didascalies entre parenthèses : seulement ce qui est lu ;
- bruitages (« sound ») de temps en temps, quand ils aident à imaginer la scène, parmi : {_sound_names()} ;
- fonds d'ambiance (« ambiance ») pour poser une scène, parmi : {", ".join(sounds.AMBIENCE_LABELS)} ; « fin » pour
  l'arrêter ; laisse vide pour ne rien changer.{cast}{split}
Réponds en JSON : {{{first}"paragraphs": [{{"speaker": "" pour le narrateur ou le nom du personnage,
"text": "texte lu", "emotion": "", "sound": "", "ambiance": ""}}]}}.
« emotion » est vide ou l'une de : {emotions}."""


def _clean_character(raw) -> StoryCharacter | None:
    if not isinstance(raw, dict):
        return None
    name = " ".join(str(raw.get("name") or "").replace(":", " ").split())[:40]
    if not name or name.lower() in ("narrateur", "narratrice"):
        return None
    kind = str(raw.get("kind") or "character").strip().lower()
    voice = str(raw.get("voice") or "normale").strip().lower()
    gender = str(raw.get("gender") or "").strip().upper()[:1]
    return StoryCharacter(name, " ".join(str(raw.get("description") or "").split())[:200],
                          kind if kind in ("hero", "character", "animal", "magic", "villain", "parent") else "character",
                          {"aiguë": "aigue", "aigu": "aigue", "grave": "grave"}.get(voice, voice if voice in
                                                                                   ("aigue", "grave") else "normale"),
                          gender if gender in ("F", "M") else "")


def _clean_paragraph(raw, names: dict[str, str]) -> StoryParagraph | None:
    if not isinstance(raw, dict):
        return None
    text = " ".join(str(raw.get("text") or "").split())
    text = re.sub(r"^[—–-]\s*", "", text)
    if not text:
        return None
    speaker = str(raw.get("speaker") or "").strip()
    if speaker.lower() in ("", "narrateur", "narratrice", "narrator", "conteur"):
        speaker = ""
    else:
        speaker = names.get(speaker.lower(), " ".join(speaker.replace(":", " ").split())[:40])
    sound = str(raw.get("sound") or "").strip()
    sound = sound if sound and sounds.resolve_name(sound) else ""
    amb = str(raw.get("ambiance") or "").strip()
    if amb and amb.lower() not in ("fin", "aucune", "stop") and sounds.ambience_key(amb) is None:
        amb = ""
    return StoryParagraph(speaker, text, _clean_emotion(raw.get("emotion")), sound, amb)


def write_story(req: StoryRequest, client: DeepSeekClient, progress=None) -> Story:
    """Écrit l'histoire (en plusieurs parties si elle est longue)."""
    if not req.idea.strip():
        raise AIError("Écrivez (ou dictez) d'abord l'idée de l'histoire.")
    total = target_words(req.minutes, req.age, req.bedtime)
    parts = max(1, math.ceil(total / WORDS_PER_PART))
    names = {c.name.lower(): c.name for c in req.characters}
    if req.child_name.strip():
        names[req.child_name.strip().lower()] = req.child_name.strip()
    title, summary = "", ""
    characters: list[StoryCharacter] = []
    paragraphs: list[StoryParagraph] = []
    for part in range(1, parts + 1):
        if progress:
            progress(f"DeepSeek écrit l'histoire… (partie {part} sur {parts})" if parts > 1 else
                     "DeepSeek écrit l'histoire…")
        user = f"Idée du parent : {req.idea.strip()[:4000]}"
        if paragraphs:
            so_far = "\n".join((f"{p.speaker}: " if p.speaker else "") + p.text for p in paragraphs[-40:])
            user += f"\n\nTitre : {title}\nPersonnages : " + ", ".join(c.name for c in characters) + \
                f"\n\nL'histoire jusqu'ici (fin) :\n{so_far[-6000:]}\n\nÉcris la suite."
        data = client.chat_json(system_prompt(req, total // parts, part, parts), user, max_tokens=8000,
                                temperature=0.9)
        if part == 1:
            title = " ".join(str(data.get("title") or "").split())[:80]
            summary = " ".join(str(data.get("summary") or "").split())[:400]
            for raw in data.get("characters") or []:
                c = _clean_character(raw)
                if c is not None and c.name.lower() not in {x.name.lower() for x in characters}:
                    characters.append(c)
                    names.setdefault(c.name.lower(), c.name)
        for raw in data.get("paragraphs") or data.get("paragraphes") or []:
            p = _clean_paragraph(raw, names)
            if p is not None:
                paragraphs.append(p)
    if not paragraphs:
        raise AIError("DeepSeek n'a pas renvoyé d'histoire. Réessayez ou précisez l'idée.")
    known = {c.name.lower() for c in characters}
    for p in paragraphs:  # personnage qui parle sans avoir été présenté : ajouté à la liste
        if p.speaker and p.speaker.lower() not in known:
            characters.append(StoryCharacter(p.speaker))
            known.add(p.speaker.lower())
    if req.child_name.strip() and req.child_name.strip().lower() in known:
        for c in characters:
            if c.name.lower() == req.child_name.strip().lower():
                c.kind = "hero"
                c.voice = "aigue"
    return Story(title or "Une nouvelle histoire", summary, characters, paragraphs, req.moral.strip())


def story_to_script(story: Story) -> str:
    """Texte balisé de l'histoire : « [ambiance: …] », « [son: …] », « @Nom: [émotion] réplique »."""
    out: list[str] = []
    current = ""
    for p in story.paragraphs:
        if p.ambiance:
            key = "fin" if p.ambiance.lower() in ("fin", "aucune", "stop") else sounds.ambience_key(p.ambiance) or ""
            if key == "fin" and current:
                out.append("[ambiance: fin]")
                current = ""
            elif key and key != "fin" and key != current:
                out.append(f"[ambiance: {key}]")
                current = key
        tag = f"[{p.emotion}] " if p.emotion else ""
        out.append((f"@{p.speaker}: " if p.speaker else "") + tag + p.text)
        if p.sound:
            out.append(f"[son: {sounds.resolve_name(p.sound)}]")
    if current:
        out.append("[ambiance: fin]")
    return "\n\n".join(out)


# ---------------------------------------------------------------------------------------
# Personnages : façon de parler et voix proposée
# ---------------------------------------------------------------------------------------
_GIANT_WORDS = ("dragon", "ogre", "géant", "geant", "ours", "loup", "lion", "éléphant", "elephant", "baleine", "troll",
                "roi", "taureau", "gorille")
_TINY_WORDS = ("souris", "oiseau", "poussin", "fourmi", "coccinelle", "abeille", "papillon", "lapin", "écureuil",
               "ecureuil", "grillon", "escargot", "hérisson", "herisson", "chaton")
_SMALL_WORDS = {"petit", "petite", "bébé", "bebe", "jeune", "minuscule", "tout-petit"}
_FAIRY_WORDS = ("fée", "fee", "lutin", "elfe", "étoile", "etoile", "luciole")
_OLD_WORDS = ("grand-mère", "grand-père", "mamie", "papi", "vieux", "vieille", "sage", "hibou", "chouette", "tortue")


def style_for(character: StoryCharacter) -> str:
    """Façon de parler proposée (voir ``models.VOICE_STYLES``) d'après le type et la description du personnage.

    Un « petit » personnage parle comme un enfant, même si c'est un dragon."""
    text = f"{character.name} {character.description}".lower()
    words = set(re.findall(r"[\wà-ÿ-]+", text))
    tiny_animal = any(w in text for w in _TINY_WORDS)
    if "robot" in text:
        return "robot"
    if any(w in text for w in _FAIRY_WORDS) or (character.kind == "magic" and character.voice != "grave"):
        return "fee"
    if words & _SMALL_WORDS or character.voice == "aigue":
        return "petit" if tiny_animal else "enfant"
    if "dragon" in text:
        return "dragon"
    if any(w in text for w in _OLD_WORDS):
        return "ancien"
    if any(w in text for w in _GIANT_WORDS):
        return "geant"
    if tiny_animal:
        return "petit"
    if character.kind == "hero":
        return "enfant"
    if character.voice == "grave" or character.kind == "villain":
        return "grand"
    return "normal"


ROLE_FOR_KIND = {"hero": "hero", "character": "character", "animal": "animal", "magic": "magic",
                 "villain": "villain", "parent": "parent"}

# Voix Microsoft (gratuites, en ligne) adaptées aux contes : (identifiant, nom affiché, genre)
STORY_VOICES = {
    "enfant": [("fr-FR-EloiseNeural", "Eloise", "F")],
    "F": [("fr-FR-DeniseNeural", "Denise", "F"), ("fr-FR-VivienneMultilingualNeural", "Vivienne", "F"),
          ("fr-CA-SylvieNeural", "Sylvie", "F"), ("fr-BE-CharlineNeural", "Charline", "F"),
          ("fr-CH-ArianeNeural", "Ariane", "F")],
    "M": [("fr-FR-HenriNeural", "Henri", "M"), ("fr-FR-RemyMultilingualNeural", "Rémy", "M"),
          ("fr-CA-AntoineNeural", "Antoine", "M"), ("fr-BE-GerardNeural", "Gérard", "M"),
          ("fr-CH-FabriceNeural", "Fabrice", "M"), ("fr-CA-JeanNeural", "Jean", "M")],
}


def voice_for(character: StoryCharacter, used: set[str], toggle: int = 0) -> VoiceProfile:
    """Voix Microsoft proposée pour un personnage, en évitant celles déjà prises."""
    style = style_for(character)
    gender = character.gender or ("F" if toggle % 2 == 0 else "M")
    pools = []
    if style in ("enfant", "petit", "fee") or character.kind == "hero":
        pools.append(STORY_VOICES["enfant"])
    pools.append(STORY_VOICES[gender])
    pools.append(STORY_VOICES["M" if gender == "F" else "F"])
    choice = None
    for pool in pools:
        choice = next((c for c in pool if c[0] not in used), None)
        if choice:
            break
    choice = choice or STORY_VOICES[gender][len(used) % len(STORY_VOICES[gender])]
    used.add(choice[0])
    vid, label, g = choice
    return VoiceProfile(name=f"{label} ({'enfant' if vid == 'fr-FR-EloiseNeural' else 'Microsoft'})", engine="edge",
                        engine_voice=vid, language="fr", gender=g,
                        description="Voix neuronale Microsoft proposée pour les personnages des contes. "
                                    "Nécessite Internet.")


def characters_to_hosts(characters: list[StoryCharacter], existing: list[Host], taken_voices: list[VoiceProfile],
                        library=None) -> list[Host]:
    """Nouveaux personnages de l'histoire → personnages de la collection, chacun avec sa voix et sa façon de parler.

    Les personnages déjà présents dans la collection gardent leur voix. Avec ``library``, les voix proposées y sont
    enregistrées."""
    known = {h.name.strip().lower() for h in existing}
    used = {v.engine_voice for v in taken_voices if v.engine == "edge"}
    out: list[Host] = []
    for i, c in enumerate(characters):
        if c.name.strip().lower() in known:
            continue
        voice = voice_for(c, used, i)
        if library is not None:  # une voix Microsoft déjà dans la bibliothèque est réutilisée telle quelle
            same = next((v for v in library.all() if v.engine == "edge" and v.engine_voice == voice.engine_voice
                         and not v.params), None)
            voice = same or library.save(voice)
        out.append(Host(c.name, ROLE_FOR_KIND.get(c.kind, "character"), voice.id if library is not None else "",
                        c.description, style=style_for(c)))
        known.add(c.name.strip().lower())
    return out
