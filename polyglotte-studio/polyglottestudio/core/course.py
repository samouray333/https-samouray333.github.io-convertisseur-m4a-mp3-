"""Cours de langue : modules, script lu d'une leçon (vocabulaire, exercices audio, réflexion, résumé, quiz).

Le texte d'une leçon (dialogue, petite histoire, point de grammaire…) est écrit avec les balises habituelles ;
les sections d'exercices sont générées à partir du vocabulaire et des phrases de la leçon :

- « écoutez puis répétez » : le mot, un silence pour le répéter, puis la bonne prononciation ;
- lecture lente puis normale des phrases utiles ;
- traduction différée : le mot dans la langue d'explication, un silence, puis la réponse ;
- dictée : chaque phrase lue lentement deux fois, avec le temps d'écrire ;
- questions de compréhension après le texte, résumé et quiz en fin de leçon.

Les consignes sont lues dans la langue d'explication (français, anglais, espagnol, allemand, italien, portugais,
néerlandais intégrés ; pour les autres, l'assistant IA les traduit une fois pour toutes dans le projet).
"""

from __future__ import annotations

import re

from . import languages
from .models import Chapter, Project, QuizQuestion, VocabItem

# « [réflexion] » (durée réglée dans la production) ou « [réflexion 10s] »
REFLECTION_RE = re.compile(r"\[\s*r[ée]flexion(?:\s*[:= ]?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)?)?\s*\]", re.IGNORECASE)
DEFAULT_REFLECTION_MS = 6000
LETTERS = "ABCDEFGH"
# Titre de partie importé qui annonce un module : « Module 2 », « Partie I : … », « Unité 3 », « Séquence 1 »
MODULE_TITLE_RE = re.compile(r"^\s*(module|partie|unit[ée]|unit|s[ée]quence|bloc|semaine|th[èe]me)\s+([\w]+)\b",
                             re.IGNORECASE)

# =======================================================================================
# Consignes lues, dans la langue d'explication
# =======================================================================================
INSTRUCTION_KEYS = [
    "vocab_title", "vocab_intro", "phrases_title", "phrases_intro", "phrases_intro_slow", "comprehension_title",
    "comprehension_intro", "question_n", "answer", "translation_title", "translation_intro", "how_say",
    "dictation_title", "dictation_intro", "sentence_n", "summary_title", "quiz_title", "quiz_intro_one",
    "quiz_intro_many", "good_answer", "module_n", "lesson_n", "review_title", "review_intro", "review_end",
    "example",
]
INSTRUCTIONS: dict[str, dict[str, str]] = {
    "fr": {
        "vocab_title": "Vocabulaire",
        "vocab_intro": "Voici les mots de cette leçon. Écoutez chaque mot, répétez-le dans le silence, puis "
                       "écoutez-le encore une fois.",
        "phrases_title": "Phrases utiles",
        "phrases_intro": "Voici quelques phrases utiles. Répétez chacune d'elles dans le silence.",
        "phrases_intro_slow": "Voici quelques phrases utiles. Chaque phrase est lue lentement, puis au débit normal. "
                              "Répétez après chaque lecture.",
        "comprehension_title": "Avez-vous bien compris ?",
        "comprehension_intro": "Écoutez la question, réfléchissez, puis écoutez la réponse.",
        "question_n": "Question {n}.",
        "answer": "Réponse : {answer}",
        "translation_title": "À vous de traduire",
        "translation_intro": "Je dis un mot en français. Dites-le en {language} pendant le silence, puis écoutez la "
                             "bonne réponse.",
        "how_say": "Comment dit-on : {text} ?",
        "dictation_title": "Dictée",
        "dictation_intro": "Prenez de quoi écrire. Chaque phrase est lue lentement deux fois : écrivez-la pendant le "
                           "silence.",
        "sentence_n": "Phrase {n}.",
        "summary_title": "Ce qu'il faut retenir",
        "quiz_title": "Quiz",
        "quiz_intro_one": "Pour terminer, une petite question pour vérifier ce que vous avez retenu.",
        "quiz_intro_many": "Pour terminer, {n} questions pour vérifier ce que vous avez retenu. Mettez l'écoute en "
                           "pause si vous avez besoin de plus de temps.",
        "good_answer": "La bonne réponse est {answer}",
        "module_n": "Module {n}.",
        "lesson_n": "Leçon {n}.",
        "review_title": "Révision",
        "review_intro": "C'est l'heure de la révision : {n} mots et phrases déjà vus. Je dis le mot en français ; "
                        "dites-le en {language} pendant le silence, puis répétez après la bonne réponse.",
        "review_end": "Bravo, la révision est terminée. À la prochaine séance !",
        "example": "Par exemple :",
    },
    "en": {
        "vocab_title": "Vocabulary",
        "vocab_intro": "Here are the words of this lesson. Listen to each word, repeat it in the silence, then "
                       "listen to it once more.",
        "phrases_title": "Useful phrases",
        "phrases_intro": "Here are some useful phrases. Repeat each one in the silence.",
        "phrases_intro_slow": "Here are some useful phrases. Each one is read slowly, then at normal speed. Repeat "
                              "after each reading.",
        "comprehension_title": "Did you understand?",
        "comprehension_intro": "Listen to the question, think about it, then listen to the answer.",
        "question_n": "Question {n}.",
        "answer": "Answer: {answer}",
        "translation_title": "Your turn to translate",
        "translation_intro": "I say a word in English. Say it in {language} during the silence, then listen to the "
                             "right answer.",
        "how_say": "How do you say: {text}?",
        "dictation_title": "Dictation",
        "dictation_intro": "Get something to write with. Each sentence is read slowly twice: write it down during "
                           "the silence.",
        "sentence_n": "Sentence {n}.",
        "summary_title": "Key points",
        "quiz_title": "Quiz",
        "quiz_intro_one": "To finish, a short question to check what you remember.",
        "quiz_intro_many": "To finish, {n} questions to check what you remember. Pause the audio if you need more "
                           "time.",
        "good_answer": "The right answer is {answer}",
        "module_n": "Module {n}.",
        "lesson_n": "Lesson {n}.",
        "review_title": "Review",
        "review_intro": "Time for your review: {n} words and phrases you have already seen. I say the word in "
                        "English; say it in {language} during the silence, then repeat after the right answer.",
        "review_end": "Well done, the review is over. See you at the next session!",
        "example": "For example:",
    },
    "es": {
        "vocab_title": "Vocabulario",
        "vocab_intro": "Estas son las palabras de esta lección. Escucha cada palabra, repítela en el silencio y "
                       "escúchala otra vez.",
        "phrases_title": "Frases útiles",
        "phrases_intro": "Estas son algunas frases útiles. Repite cada una en el silencio.",
        "phrases_intro_slow": "Estas son algunas frases útiles. Cada frase se lee despacio y luego a velocidad "
                              "normal. Repite después de cada lectura.",
        "comprehension_title": "¿Has entendido?",
        "comprehension_intro": "Escucha la pregunta, piensa y luego escucha la respuesta.",
        "question_n": "Pregunta {n}.",
        "answer": "Respuesta: {answer}",
        "translation_title": "Ahora traduce tú",
        "translation_intro": "Digo una palabra en español. Dila en la lengua que estudias durante el silencio y "
                             "luego escucha la respuesta correcta.",
        "how_say": "¿Cómo se dice: {text}?",
        "dictation_title": "Dictado",
        "dictation_intro": "Toma algo para escribir. Cada frase se lee despacio dos veces: escríbela durante el "
                           "silencio.",
        "sentence_n": "Frase {n}.",
        "summary_title": "Lo esencial",
        "quiz_title": "Cuestionario",
        "quiz_intro_one": "Para terminar, una pregunta para comprobar lo que recuerdas.",
        "quiz_intro_many": "Para terminar, {n} preguntas para comprobar lo que recuerdas. Pausa el audio si "
                           "necesitas más tiempo.",
        "good_answer": "La respuesta correcta es {answer}",
        "module_n": "Módulo {n}.",
        "lesson_n": "Lección {n}.",
        "review_title": "Repaso",
        "review_intro": "Es la hora del repaso: {n} palabras y frases que ya has visto. Digo la palabra en español; "
                        "dila en la lengua que estudias durante el silencio y repite después de la respuesta.",
        "review_end": "¡Muy bien, el repaso ha terminado! Hasta la próxima sesión.",
        "example": "Por ejemplo:",
    },
    "de": {
        "vocab_title": "Wortschatz",
        "vocab_intro": "Hier sind die Wörter dieser Lektion. Hören Sie jedes Wort, sprechen Sie es in der Pause "
                       "nach und hören Sie es dann noch einmal.",
        "phrases_title": "Nützliche Sätze",
        "phrases_intro": "Hier sind einige nützliche Sätze. Sprechen Sie jeden Satz in der Pause nach.",
        "phrases_intro_slow": "Hier sind einige nützliche Sätze. Jeder Satz wird zuerst langsam, dann in normalem "
                              "Tempo gelesen. Sprechen Sie nach jedem Lesen nach.",
        "comprehension_title": "Haben Sie alles verstanden?",
        "comprehension_intro": "Hören Sie die Frage, denken Sie nach und hören Sie dann die Antwort.",
        "question_n": "Frage {n}.",
        "answer": "Antwort: {answer}",
        "translation_title": "Jetzt übersetzen Sie",
        "translation_intro": "Ich sage ein Wort auf Deutsch. Sagen Sie es in der Pause in der Lernsprache und hören "
                             "Sie dann die richtige Antwort.",
        "how_say": "Wie sagt man: {text}?",
        "dictation_title": "Diktat",
        "dictation_intro": "Nehmen Sie etwas zum Schreiben. Jeder Satz wird zweimal langsam gelesen: Schreiben Sie "
                           "ihn in der Pause auf.",
        "sentence_n": "Satz {n}.",
        "summary_title": "Das Wichtigste",
        "quiz_title": "Quiz",
        "quiz_intro_one": "Zum Schluss eine kurze Frage zur Kontrolle.",
        "quiz_intro_many": "Zum Schluss {n} Fragen zur Kontrolle. Halten Sie die Wiedergabe an, wenn Sie mehr Zeit "
                           "brauchen.",
        "good_answer": "Die richtige Antwort ist {answer}",
        "module_n": "Modul {n}.",
        "lesson_n": "Lektion {n}.",
        "review_title": "Wiederholung",
        "review_intro": "Zeit für die Wiederholung: {n} Wörter und Sätze, die Sie schon kennen. Ich sage das Wort "
                        "auf Deutsch; sagen Sie es in der Pause in der Lernsprache und sprechen Sie die Antwort nach.",
        "review_end": "Sehr gut, die Wiederholung ist beendet. Bis zum nächsten Mal!",
        "example": "Zum Beispiel:",
    },
    "it": {
        "vocab_title": "Vocabolario",
        "vocab_intro": "Ecco le parole di questa lezione. Ascolta ogni parola, ripetila nel silenzio e poi "
                       "ascoltala ancora una volta.",
        "phrases_title": "Frasi utili",
        "phrases_intro": "Ecco alcune frasi utili. Ripeti ciascuna nel silenzio.",
        "phrases_intro_slow": "Ecco alcune frasi utili. Ogni frase viene letta lentamente, poi a velocità normale. "
                              "Ripeti dopo ogni lettura.",
        "comprehension_title": "Hai capito bene?",
        "comprehension_intro": "Ascolta la domanda, rifletti e poi ascolta la risposta.",
        "question_n": "Domanda {n}.",
        "answer": "Risposta: {answer}",
        "translation_title": "Ora traduci tu",
        "translation_intro": "Dico una parola in italiano. Dilla nella lingua che studi durante il silenzio, poi "
                             "ascolta la risposta giusta.",
        "how_say": "Come si dice: {text}?",
        "dictation_title": "Dettato",
        "dictation_intro": "Prendi qualcosa per scrivere. Ogni frase viene letta lentamente due volte: scrivila "
                           "durante il silenzio.",
        "sentence_n": "Frase {n}.",
        "summary_title": "Da ricordare",
        "quiz_title": "Quiz",
        "quiz_intro_one": "Per finire, una domanda per verificare cosa ricordi.",
        "quiz_intro_many": "Per finire, {n} domande per verificare cosa ricordi. Metti in pausa se ti serve più "
                           "tempo.",
        "good_answer": "La risposta giusta è {answer}",
        "module_n": "Modulo {n}.",
        "lesson_n": "Lezione {n}.",
        "review_title": "Ripasso",
        "review_intro": "È l'ora del ripasso: {n} parole e frasi già viste. Dico la parola in italiano; dilla nella "
                        "lingua che studi durante il silenzio, poi ripeti dopo la risposta giusta.",
        "review_end": "Bravo, il ripasso è finito. Alla prossima sessione!",
        "example": "Per esempio:",
    },
    "pt": {
        "vocab_title": "Vocabulário",
        "vocab_intro": "Estas são as palavras desta lição. Ouça cada palavra, repita-a no silêncio e ouça-a mais "
                       "uma vez.",
        "phrases_title": "Frases úteis",
        "phrases_intro": "Estas são algumas frases úteis. Repita cada uma no silêncio.",
        "phrases_intro_slow": "Estas são algumas frases úteis. Cada frase é lida devagar e depois em velocidade "
                              "normal. Repita depois de cada leitura.",
        "comprehension_title": "Você entendeu?",
        "comprehension_intro": "Ouça a pergunta, pense e depois ouça a resposta.",
        "question_n": "Pergunta {n}.",
        "answer": "Resposta: {answer}",
        "translation_title": "Agora traduza você",
        "translation_intro": "Digo uma palavra em português. Diga-a na língua que estuda durante o silêncio e depois "
                             "ouça a resposta certa.",
        "how_say": "Como se diz: {text}?",
        "dictation_title": "Ditado",
        "dictation_intro": "Pegue algo para escrever. Cada frase é lida devagar duas vezes: escreva-a durante o "
                           "silêncio.",
        "sentence_n": "Frase {n}.",
        "summary_title": "O essencial",
        "quiz_title": "Questionário",
        "quiz_intro_one": "Para terminar, uma pergunta para verificar o que você lembra.",
        "quiz_intro_many": "Para terminar, {n} perguntas para verificar o que você lembra. Pause o áudio se precisar "
                           "de mais tempo.",
        "good_answer": "A resposta certa é {answer}",
        "module_n": "Módulo {n}.",
        "lesson_n": "Lição {n}.",
        "review_title": "Revisão",
        "review_intro": "Hora da revisão: {n} palavras e frases já vistas. Digo a palavra em português; diga-a na "
                        "língua que estuda durante o silêncio e repita depois da resposta.",
        "review_end": "Muito bem, a revisão terminou. Até a próxima sessão!",
        "example": "Por exemplo:",
    },
    "nl": {
        "vocab_title": "Woordenschat",
        "vocab_intro": "Dit zijn de woorden van deze les. Luister naar elk woord, herhaal het in de stilte en "
                       "luister er nog een keer naar.",
        "phrases_title": "Handige zinnen",
        "phrases_intro": "Dit zijn enkele handige zinnen. Herhaal elke zin in de stilte.",
        "phrases_intro_slow": "Dit zijn enkele handige zinnen. Elke zin wordt eerst langzaam, daarna op normaal "
                              "tempo voorgelezen. Herhaal na elke keer.",
        "comprehension_title": "Heb je het begrepen?",
        "comprehension_intro": "Luister naar de vraag, denk na en luister dan naar het antwoord.",
        "question_n": "Vraag {n}.",
        "answer": "Antwoord: {answer}",
        "translation_title": "Nu vertaal jij",
        "translation_intro": "Ik zeg een woord in het Nederlands. Zeg het in de stilte in de taal die je leert en "
                             "luister dan naar het juiste antwoord.",
        "how_say": "Hoe zeg je: {text}?",
        "dictation_title": "Dictee",
        "dictation_intro": "Pak iets om te schrijven. Elke zin wordt twee keer langzaam voorgelezen: schrijf hem op "
                           "in de stilte.",
        "sentence_n": "Zin {n}.",
        "summary_title": "Om te onthouden",
        "quiz_title": "Quiz",
        "quiz_intro_one": "Tot slot een korte vraag om te controleren wat je onthouden hebt.",
        "quiz_intro_many": "Tot slot {n} vragen om te controleren wat je onthouden hebt. Pauzeer als je meer tijd "
                           "nodig hebt.",
        "good_answer": "Het juiste antwoord is {answer}",
        "module_n": "Module {n}.",
        "lesson_n": "Les {n}.",
        "review_title": "Herhaling",
        "review_intro": "Tijd voor herhaling: {n} woorden en zinnen die je al kent. Ik zeg het woord in het "
                        "Nederlands; zeg het in de stilte in de taal die je leert en herhaal na het antwoord.",
        "review_end": "Goed gedaan, de herhaling is klaar. Tot de volgende keer!",
        "example": "Bijvoorbeeld:",
    },
}
# Nom des langues en anglais (consignes en anglais)
_EN_NAMES = {
    "zh": "Mandarin Chinese", "yue": "Cantonese", "ja": "Japanese", "ko": "Korean", "fil": "Filipino",
    "nb": "Norwegian", "fa": "Persian", "el": "Greek", "de": "German", "nl": "Dutch", "es": "Spanish",
    "fr": "French", "it": "Italian", "pt": "Portuguese", "ru": "Russian", "uk": "Ukrainian", "pl": "Polish",
    "cs": "Czech", "sk": "Slovak", "hu": "Hungarian", "ro": "Romanian", "bg": "Bulgarian", "hr": "Croatian",
    "sr": "Serbian", "sl": "Slovenian", "sv": "Swedish", "da": "Danish", "fi": "Finnish", "tr": "Turkish",
    "ar": "Arabic", "he": "Hebrew", "hi": "Hindi", "ur": "Urdu", "bn": "Bengali", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "sw": "Swahili", "ca": "Catalan", "eu": "Basque",
    "gl": "Galician", "cy": "Welsh", "ga": "Irish", "is": "Icelandic", "en": "English", "ta": "Tamil",
    "te": "Telugu", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "et": "Estonian", "lv": "Latvian",
    "lt": "Lithuanian", "sq": "Albanian", "mk": "Macedonian", "ka": "Georgian", "hy": "Armenian",
    "az": "Azerbaijani", "kk": "Kazakh", "uz": "Uzbek", "mn": "Mongolian", "ne": "Nepali", "km": "Khmer",
    "lo": "Lao", "my": "Burmese", "so": "Somali", "ps": "Pashto", "mt": "Maltese", "am": "Amharic",
    "zu": "Zulu", "af": "Afrikaans", "bs": "Bosnian", "kn": "Kannada", "ml": "Malayalam", "si": "Sinhala",
    "jv": "Javanese", "su": "Sundanese",
}


def explain_code(project: Project) -> str:
    lang = languages.get(project.metadata.language or "fr")
    return lang.code if lang else "fr"


def has_builtin_instructions(code: str) -> bool:
    lang = languages.get(code)
    return bool(lang) and lang.code in INSTRUCTIONS


def target_name_for(project: Project, target_code: str) -> str:
    """Nom de la langue apprise, dit dans la langue d'explication."""
    explain = explain_code(project)
    lang = languages.get(target_code)
    if lang is None:
        return target_code
    if explain == "fr":
        return lang.name.lower() if lang.code not in ("yue",) else lang.name
    if explain == "en":
        return _EN_NAMES.get(lang.code, lang.native)
    return lang.native


def t(project: Project, key: str, **values) -> str:
    """Consigne ``key`` dans la langue d'explication : celle du projet (traduite par l'IA), sinon intégrée,
    sinon en anglais."""
    explain = explain_code(project)
    template = (project.instructions or {}).get(key) or INSTRUCTIONS.get(explain, {}).get(key) \
        or INSTRUCTIONS["en"].get(key, key)
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


# =======================================================================================
# Réflexion et quiz (repris de Leçon Studio)
# =======================================================================================
def expand_reflections(text: str, default_ms: int = DEFAULT_REFLECTION_MS) -> str:
    """Remplace les balises de réflexion par des pauses ordinaires."""
    def repl(m: re.Match) -> str:
        if m.group(1):
            v = float(m.group(1).replace(",", "."))
            ms = int(v if (m.group(2) or "s").lower() == "ms" else v * 1000)
        else:
            ms = default_ms
        return f"[pause {max(0, ms)}ms]"

    return REFLECTION_RE.sub(repl, text)


def _sentence(text: str) -> str:
    s = " ".join(text.split()).strip()
    return s if not s or s[-1] in ".!?…。！？" else s + "."


def _letter_answer(q: QuizQuestion) -> tuple[str, str]:
    answer = q.answer.strip()
    letter = ""
    if q.choices and answer:
        lowered = [c.strip().lower() for c in q.choices]
        if answer.lower() in lowered:
            letter = LETTERS[lowered.index(answer.lower())]
            answer = q.choices[lowered.index(answer.lower())].strip()
        elif len(answer) == 1 and answer.upper() in LETTERS[:len(q.choices)]:
            letter = answer.upper()
            answer = q.choices[LETTERS.index(letter)]
    return letter, answer


def quiz_script(quiz: list[QuizQuestion], think_ms: int, project: Project | None = None) -> str:
    """Texte lu du quiz : chaque question, ses choix, un temps de réponse, puis la correction."""
    project = project or Project()
    questions = [q for q in quiz if q.question.strip()]
    if not questions:
        return ""
    n = len(questions)
    intro = t(project, "quiz_intro_one") if n == 1 else t(project, "quiz_intro_many", n=n)
    out = ["# " + t(project, "quiz_title"), intro]
    for i, q in enumerate(questions, 1):
        out.append(f"{t(project, 'question_n', n=i)} {_sentence(q.question)}")
        if q.choices:
            out.append(" ".join(f"{LETTERS[j]} : {_sentence(c)}" for j, c in enumerate(q.choices[:len(LETTERS)])))
        out.append(f"[pause {max(0, think_ms)}ms]")
        letter, answer = _letter_answer(q)
        if answer:
            out.append(t(project, "good_answer", answer=(letter + " : " if letter else "") + _sentence(answer))
                       + " " + _sentence(q.explanation))
    return "\n\n".join(p.strip() for p in out if p.strip())


# =======================================================================================
# Exercices de langue
# =======================================================================================
def _clean(text: str) -> str:
    """Texte d'un mot ou d'une phrase sûr à placer dans un script (pas de balises ni de marqueurs de ligne)."""
    s = " ".join(str(text).split()).replace("[", "(").replace("]", ")")
    return re.sub(r"^(?:[@#]+|%%)\s*", "", s).strip()


def _native(lang: str, text: str, slow: bool = False) -> str:
    return f"[{lang}] " + ("[ralenti] " if slow else "") + _clean(text)


def target_spec(project: Project, chapter: Chapter) -> str:
    """Balise de la langue apprise d'une leçon (« es » ou, si un accent est choisi, « es-MX »)."""
    code, locale = project.target_of(chapter)
    return locale or code


def vocab_section(project: Project, chapter: Chapter, items: list[VocabItem], kind: str) -> str:
    """Section « Vocabulaire » (kind « word ») ou « Phrases utiles » (kind « phrase »)."""
    if not items:
        return ""
    prod = project.production
    ex = project.exercises_of(chapter)
    spec = target_spec(project, chapter)
    code = languages.get(spec).code if languages.get(spec) else spec
    repeat = "repeat" in ex
    slow_normal = "slow_normal" in ex and kind == "phrase"
    if kind == "word":
        out = ["# " + t(project, "vocab_title"), t(project, "vocab_intro") if repeat else ""]
    else:
        out = ["# " + t(project, "phrases_title"),
               t(project, "phrases_intro_slow") if slow_normal else t(project, "phrases_intro") if repeat else ""]
    for it in items:
        pause = languages.repeat_pause_ms(it.term, code, prod.repeat_factor)
        if slow_normal:
            out += [_native(spec, it.term, slow=True), f"[pause {pause}ms]", _native(spec, it.term)]
            if repeat:
                out.append(f"[pause {pause}ms]")
        else:
            out.append(_native(spec, it.term))
            if repeat:
                out += [f"[pause {pause}ms]", _native(spec, it.term)]
        if it.translation.strip():
            out.append(_sentence(_clean(it.translation)))
        if it.example.strip() and kind == "word":
            out.append(_native(spec, it.example))
            if it.example_translation.strip():
                out.append(_sentence(_clean(it.example_translation)))
        out.append("[pause 600ms]")
    return "\n\n".join(p for p in out if p)


def translation_section(project: Project, chapter: Chapter, items: list[VocabItem], limit: int = 15) -> str:
    """Traduction différée : « Comment dit-on : chat ? », silence, puis « gato » dans la langue apprise."""
    items = [it for it in items if it.term.strip() and it.translation.strip()][:limit]
    if not items:
        return ""
    prod = project.production
    spec = target_spec(project, chapter)
    code = languages.get(spec).code if languages.get(spec) else spec
    out = ["# " + t(project, "translation_title"),
           t(project, "translation_intro", language=target_name_for(project, code))]
    for it in items:
        think = max(prod.translation_think_ms, languages.repeat_pause_ms(it.term, code, 1.0))
        out += [t(project, "how_say", text=_clean(it.translation).rstrip(".?!")), f"[pause {think}ms]",
                _native(spec, it.term), "[pause 900ms]"]
    return "\n\n".join(out)


def dictation_section(project: Project, chapter: Chapter, limit: int = 5) -> str:
    """Dictée : phrases utiles (ou exemples) lues lentement deux fois, avec le temps d'écrire."""
    sentences = [p.term for p in chapter.phrases()] or [w.example for w in chapter.words() if w.example.strip()]
    sentences = [s for s in sentences if s.strip()][:limit]
    if not sentences:
        return ""
    prod = project.production
    spec = target_spec(project, chapter)
    out = ["# " + t(project, "dictation_title"), t(project, "dictation_intro")]
    for i, s in enumerate(sentences, 1):
        out += [t(project, "sentence_n", n=i), _native(spec, s, slow=True), f"[pause {prod.dictation_pause_ms}ms]",
                _native(spec, s, slow=True), "[pause 2500ms]", _native(spec, s), "[pause 1200ms]"]
    return "\n\n".join(out)


def comprehension_section(project: Project, chapter: Chapter) -> str:
    questions = [q for q in chapter.questions if q.question.strip()]
    if not questions:
        return ""
    prod = project.production
    out = ["# " + t(project, "comprehension_title"), t(project, "comprehension_intro")]
    for i, q in enumerate(questions, 1):
        out += [f"{t(project, 'question_n', n=i)} {_sentence(q.question)}", f"[pause {prod.reflection_pause_ms}ms]"]
        letter, answer = _letter_answer(q)
        if answer:
            out.append(t(project, "answer", answer=_sentence(answer)) + (" " + _sentence(q.explanation)
                                                                         if q.explanation.strip() else ""))
    return "\n\n".join(out)


SECTION_ORDER = ["vocabulary", "phrases", "text", "comprehension", "translation", "dictation", "summary", "quiz"]


def lesson_sections(project: Project, chapter: Chapter) -> list[tuple[str, str]]:
    """Sections lues d'une leçon, dans l'ordre : [(nom, script)]."""
    prod = project.production
    ex = project.exercises_of(chapter)
    out: list[tuple[str, str]] = []
    for name in SECTION_ORDER:
        text = ""
        if name == "vocabulary" and prod.include_vocabulary:
            text = vocab_section(project, chapter, chapter.words(), "word")
        elif name == "phrases" and prod.include_phrases:
            text = vocab_section(project, chapter, chapter.phrases(), "phrase")
        elif name == "text":
            text = expand_reflections(chapter.text, prod.reflection_pause_ms)
        elif name == "comprehension" and "comprehension" in ex:
            text = comprehension_section(project, chapter)
        elif name == "translation" and "translation" in ex:
            text = translation_section(project, chapter, chapter.words() + chapter.phrases())
        elif name == "dictation" and "dictation" in ex:
            text = dictation_section(project, chapter)
        elif name == "summary" and prod.include_summary and chapter.summary.strip():
            text = "# " + t(project, "summary_title") + "\n\n" + expand_reflections(chapter.summary.strip(),
                                                                                    prod.reflection_pause_ms)
        elif name == "quiz" and prod.include_quiz and chapter.quiz:
            text = quiz_script(chapter.quiz, prod.quiz_think_ms, project)
        if text.strip():
            out.append((name, text))
    return out


def lesson_script(project: Project, chapter: Chapter) -> str:
    """Texte complet lu pour une leçon : vocabulaire, phrases, texte, exercices, résumé et quiz."""
    return "\n\n".join(text for _name, text in lesson_sections(project, chapter))


# ---------------------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------------------
def infer_modules(chapters: list[Chapter]) -> list[Chapter]:
    """Après un import : les parties titrées « Module 2 », « Partie I »… deviennent des modules.

    Une telle partie presque vide (introduction de moins de 120 mots) disparaît et son texte passe en tête de
    la leçon suivante ; une partie longue reste une leçon, rattachée à son propre module."""
    if not any(MODULE_TITLE_RE.match(c.title) for c in chapters):
        return chapters
    out: list[Chapter] = []
    current = ""
    carry = ""
    for c in chapters:
        if MODULE_TITLE_RE.match(c.title):
            current = c.title.strip()
            if c.word_count() < 120:
                carry = c.text.strip()
                continue
        if carry:
            c.text = (carry + "\n\n" + c.text).strip()
            carry = ""
        c.module = current
        out.append(c)
    if carry:  # module sans leçon : on garde son introduction comme leçon
        out.append(Chapter(title=current, text=carry, module=current))
    return out


def group_lessons(chapters: list[Chapter], per_module: int, prefix: str = "Module") -> None:
    """Range les leçons par paquets de ``per_module`` : « Module 1 », « Module 2 »…"""
    per_module = max(1, per_module)
    for i, c in enumerate(chapters):
        c.module = f"{prefix} {i // per_module + 1}"


def module_titles(chapters: list[Chapter]) -> list[str]:
    return list(dict.fromkeys(c.module for c in chapters if c.module))


def rename_module(chapters: list[Chapter], old: str, new: str) -> int:
    n = 0
    for c in chapters:
        if c.module == old:
            c.module = new
            n += 1
    return n


def module_spoken_title(project: Project, chapter: Chapter) -> str:
    number = project.module_number(chapter)
    module = chapter.module.strip().rstrip(".")
    if re.match(r"(?i)^(module|partie|unit[ée]?|s[ée]quence|módulo|modul|modulo|lektion)\b", module):
        return module
    return f"{t(project, 'module_n', n=number)} {module}"


def lesson_spoken_title(project: Project, chapter: Chapter) -> str:
    title = chapter.title.strip().rstrip(".")
    number = project.lesson_number(chapter)
    if project.production.announce_lesson_number and number and \
            not re.match(r"(?i)^(le[çc]on|lesson|lecci[óo]n|lektion|lezione|li[çc][ãa]o)\b", title):
        return f"{t(project, 'lesson_n', n=number)} {title}"
    return title
