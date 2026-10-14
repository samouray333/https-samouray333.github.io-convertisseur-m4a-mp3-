"""Modèles d'émission : animateurs et trame de l'épisode (rubriques, jingles), prêts à compléter."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShowTemplate:
    key: str
    name: str
    description: str
    hosts: list[tuple[str, str, str]]  # (nom, rôle, présentation)
    episode_title: str
    script: str
    style: str = "conversation"  # style proposé à l'assistant d'écriture
    minutes: int = 10
    tags: list[str] = field(default_factory=list)


TEMPLATES: list[ShowTemplate] = [
    ShowTemplate(
        "conversation", "Conversation", "Deux animateurs discutent librement d'un sujet, sur un ton détendu.",
        [("Alex", "host", "curieuse et chaleureuse, relance la discussion"),
         ("Sam", "cohost", "drôle, apporte des anecdotes")],
        "Bienvenue",
        """[son: generique]

[chapitre: Ouverture]

@Alex: [joyeux] Bonjour à toutes et à tous, et bienvenue dans ce nouvel épisode !

@Sam: Ravi d'être là. Aujourd'hui, on vous parle de… (le sujet).

@Alex: Exactement !

[virgule]

[chapitre: Le sujet]

@Alex: Alors, pour commencer… (première idée).

@Sam: Ah oui !

@Sam: (une anecdote, un exemple)

[virgule]

[chapitre: Conclusion]

@Alex: Ce qu'il faut retenir aujourd'hui… (résumé).

@Sam: Merci de nous avoir écoutés, et à la semaine prochaine !

[son: generique]""", "conversation", 10),
    ShowTemplate(
        "interview", "Interview", "Un animateur reçoit un invité : présentation, questions, conseil final.",
        [("Camille", "host", "journaliste, pose des questions claires et bienveillantes"),
         ("Invité", "guest", "expert du sujet (précisez son métier)")],
        "Rencontre avec…",
        """[son: generique]

[chapitre: Présentation]

@Camille: Bonjour et bienvenue ! Aujourd'hui, je reçois… (nom et métier de l'invité). Bonjour !

@Invité: [joyeux] Bonjour Camille, merci de m'avoir invité.

[virgule]

[chapitre: Son parcours]

@Camille: Pour commencer, racontez-nous votre parcours.

@Invité: (réponse)

[chapitre: Le cœur du sujet]

@Camille: (question principale)

@Invité: (réponse)

@Camille: Ah, intéressant !

[virgule]

[chapitre: Le conseil]

@Camille: Pour finir, quel conseil donneriez-vous à nos auditeurs ?

@Invité: (conseil)

@Camille: Merci beaucoup ! À bientôt pour un nouvel épisode.

[son: generique]""", "interview", 15),
    ShowTemplate(
        "chronique", "Chronique", "Une seule voix présente un sujet en quelques minutes, avec une chute.",
        [("Léa", "host", "chroniqueuse, ton vivant et précis")],
        "La chronique de la semaine",
        """[son: virgule]

[chapitre: Accroche]

@Léa: [excité] Saviez-vous que… (une question ou un fait surprenant) ?

[chapitre: Explication]

@Léa: (deux ou trois idées, avec un exemple concret)

[pause 1s]

[chapitre: La chute]

@Léa: Et la prochaine fois que… (la chute). C'était la chronique de la semaine, à bientôt !

[son: ding]""", "info", 4),
    ShowTemplate(
        "revue", "Revue de presse", "Les actualités de la semaine, sujet par sujet, séparées par un jingle.",
        [("Hugo", "host", "présente les actualités"), ("Inès", "cohost", "commente et met en perspective")],
        "La revue de presse",
        """[son: generique]

[chapitre: Les titres]

@Hugo: Bonjour à tous ! Au sommaire de cette revue de presse : … , … et … .

[virgule]

[chapitre: Sujet 1]

@Hugo: Premier sujet : … (le fait, la source).

@Inès: (commentaire)

[virgule]

[chapitre: Sujet 2]

@Hugo: Deuxième sujet : …

@Inès: (commentaire)

[virgule]

[chapitre: Sujet 3]

@Hugo: Et pour finir, une bonne nouvelle : …

@Inès: [joyeux] Ça fait du bien !

@Hugo: C'est tout pour cette semaine, merci de votre écoute.

[son: generique]""", "info", 12),
    ShowTemplate(
        "debat", "Débat", "Un animateur arbitre deux invités aux avis opposés, puis conclut.",
        [("Nora", "host", "animatrice neutre, distribue la parole"),
         ("Paul", "guest", "défend le pour"), ("Zoé", "guest", "défend le contre")],
        "Le débat",
        """[son: generique]

[chapitre: La question]

@Nora: Bonsoir ! Ce soir, une question qui divise : … ? Pour en débattre, Paul et Zoé.

[virgule]

[chapitre: Les arguments]

@Nora: Paul, vous êtes pour. Pourquoi ?

@Paul: (argument)

@Zoé: [par-dessus] Pas du tout !

@Nora: Zoé, votre point de vue ?

@Zoé: (contre-argument)

[virgule]

[chapitre: Conclusion]

@Nora: Un mot de conclusion chacun ?

@Paul: (conclusion)

@Zoé: (conclusion)

@Nora: Merci à tous les deux. Et vous, qu'en pensez-vous ?

[son: generique]""", "debat", 15),
]


def template(key: str) -> ShowTemplate:
    return next((t for t in TEMPLATES if t.key == key), TEMPLATES[0])
