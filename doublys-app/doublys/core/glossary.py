"""Glossaire de la série : noms propres proposés automatiquement à partir du texte d'origine."""

from __future__ import annotations

import re
from collections import Counter

# mots capitalisés fréquents qui ne sont pas des noms propres
_COMMON = set("""I I'm I'll I've I'd The A An And But Or So If It It's Its This That These Those There Then Than What
Why Who Where When How Yes No Oh Ah Hey Hi Hello Okay OK Well Now Here Let Let's Come Go Get Got Look Wait Stop Run
Please Thank Thanks Sorry Good Great Right You You're Your We We're Our They They're Their He She His Her Him Them Me My
Mine Is Are Was Were Be Do Don't Did Not All Just Only Even Still Very Really Maybe Sure Of In On At To For With From By
Mr Mrs Ms Miss Sir Lady Lord Master King Queen Prince Princess Doctor Captain Mom Dad Brother Sister Everyone Nothing
Something Anything Everything Someone Anyone Monday Tuesday Wednesday Thursday Friday Saturday Sunday Ha Huh Hmm Whoa
Wow Damn God Ranger Rangers Power""".split())


def suggest_terms(texts: list[str], known: list[str] | None = None, min_count: int = 2) -> list[str]:
    """Mots capitalisés qui reviennent (au milieu d'une phrase, ou en début de phrase plusieurs fois) et ne sont pas
    des mots courants : noms de personnages, de robots, d'attaques. Triés par fréquence."""
    known_l = {k.lower() for k in known or []}
    counts: Counter[str] = Counter()
    for t in texts:
        for sentence in re.split(r"(?<=[.!?…])\s+|\n", t):
            words = re.findall(r"[A-Z][A-Za-z'-]{2,}", sentence)
            for w in words:
                w = w.strip("'-")
                if w.endswith("'s"):
                    w = w[:-2]
                if w in _COMMON or w.lower() in known_l or len(w) < 3:
                    continue
                counts[w] += 1
    return [w for w, n in counts.most_common() if n >= min_count]
