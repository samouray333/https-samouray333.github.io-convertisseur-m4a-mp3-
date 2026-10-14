import json

import pytest

from contestudio.core import ai
from contestudio.core.models import LexiconEntry, VoiceProfile

TEXT = """Marie entra dans la pièce.

— Qui est là ? demanda-t-elle.

— C'est moi, répondit Paul.

# Intertitre

@Marie: [triste] Je croyais que tu étais parti.

[voix:Lucas]
« Moi aussi », dit Lucas.

[/voix]

Siobhan les regardait en silence.   
"""


class FakeClient(ai.DeepSeekClient):
    def __init__(self, answers):
        super().__init__("sk-test")
        self.answers = list(answers)
        self.calls = []

    def _request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/models":
            return {"data": [{"id": "deepseek-v4-pro"}, {"id": "deepseek-v4-flash"}]}
        return {"choices": [{"message": {"content": self.answers.pop(0)}}]}


def test_split_paragraphs_skips_markup_and_keeps_text():
    parts, paras = ai.split_paragraphs(TEXT)
    assert "".join(parts) == TEXT
    assert [p.flat for p in paras] == ["Marie entra dans la pièce.", "— Qui est là ? demanda-t-elle.",
                                      "— C'est moi, répondit Paul.", "Je croyais que tu étais parti.",
                                      "Siobhan les regardait en silence."]
    assert paras[3].speaker == "Marie" and paras[3].emotion == "triste"


def test_annotate_and_apply_keep_every_word():
    answer = json.dumps({
        "paragraphes": [{"n": 2, "personnage": "Marie", "emotion": "peur"},
                        {"n": 3, "personnage": "Paul", "emotion": None},
                        {"n": 1, "personnage": "narrateur", "emotion": "neutre"},
                        {"n": 4, "personnage": "Marie", "emotion": "triste"},
                        {"n": 99, "personnage": "Fantôme"}],
        "personnages": [{"nom": "Marie", "genre": "F"}, {"nom": "Paul", "genre": "M"}],
        "noms": [{"mot": "Siobhan", "prononciation": "Chivône"}, {"mot": "Absent", "prononciation": "x"}]})
    client = FakeClient([answer])
    result = ai.annotate(TEXT, client, ["Marie"])
    assert client.model == "deepseek-v4-flash"
    body = client.calls[-1][2]
    assert body["response_format"] == {"type": "json_object"} and body["thinking"] == {"type": "disabled"}
    assert [(s.number, s.speaker, s.emotion) for s in result.paragraphs] == [(2, "Marie", "peur"),
                                                                          (3, "Paul", "")]
    assert result.characters == {"Marie": "F", "Paul": "M"}
    assert [(n.word, n.say) for n in result.names] == [("Siobhan", "Chivône")]
    new = ai.apply_suggestions(TEXT, result.paragraphs)
    assert "@Marie: [peur] — Qui est là ? demanda-t-elle." in new
    assert "@Paul: — C'est moi, répondit Paul." in new
    stripped = new.replace("@Marie: [peur] ", "").replace("@Paul: ", "")
    assert stripped == TEXT  # aucun mot du livre n'est modifié


def test_rejected_suggestion_is_not_applied():
    s = ai.ParagraphSuggestion(1, "", "Marie", "joyeux", accepted=False)
    assert ai.apply_suggestions(TEXT, [s]) == TEXT


def test_thinking_parameter_fallback_and_empty_answer():
    class Picky(FakeClient):
        def _request(self, method, path, body=None):
            if path == "/chat/completions" and body and "thinking" in body:
                err = ai.AIError("bad")
                err.code = 400
                raise err
            return super()._request(method, path, body)

    client = Picky(["", '{"paragraphes": []}'])
    assert client.chat_json("s", "u") == {"paragraphes": []}
    assert client._thinking_param is False


def test_errors_and_json_parsing():
    assert "Solde" in ai._http_message(402)
    assert "refusée" in ai._http_message(401)
    assert ai.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai.parse_json("pas de json") is None
    with pytest.raises(ai.AIError):
        ai.DeepSeekClient("  ")


def test_lexicon_and_voices():
    names = [ai.NameSuggestion("Siobhan", "Chivône"), ai.NameSuggestion("Kael", "Kaël", accepted=False)]
    entries = ai.lexicon_entries(names, [LexiconEntry("Autre", "x")])
    assert [(e.pattern, e.replacement) for e in entries] == [("Siobhan", "Chivône")]
    narrator = VoiceProfile(name="N", engine="edge", engine_voice="fr-FR-DeniseNeural")
    voices = ai.voices_for_characters({"Marie": "F", "Paul": "M", "Zoé": "F", "X": "?"}, [narrator])
    keys = {(v.engine_voice, v.params.get("pitch", 0)) for v in voices.values()}
    assert len(keys) == 4 and ("fr-FR-DeniseNeural", 0) not in keys
    assert voices["Paul"].gender == "M" and voices["Marie"].gender == "F"


def test_secrets_roundtrip():
    from contestudio.core.secrets import protect, unprotect

    assert unprotect(protect("sk-abc")) == "sk-abc"
    assert protect("") == "" and unprotect("") == ""


def test_dramatic_pauses_are_written_into_the_text():
    answer = json.dumps({"paragraphes": [{"n": 1, "pause": 1.5}, {"n": 5, "pause": "9"},
                                         {"n": 3, "personnage": "Paul", "pause": 0}]})
    result = ai.annotate(TEXT, FakeClient([answer]), ["Marie"])
    got = {s.number: (s.speaker, s.pause_ms) for s in result.paragraphs}
    assert got[1] == (None, 1500) and got[5] == (None, ai.MAX_PAUSE_MS) and got[3] == ("Paul", 0)
    new = ai.apply_suggestions(TEXT, result.paragraphs)
    assert "Marie entra dans la pièce. [pause 1.5s]" in new
    assert "Siobhan les regardait en silence. [pause 4s]" in new
    # nouvelle analyse : la pause existante est reconnue et conservée
    _parts, paras = ai.split_paragraphs(new)
    assert paras[0].pause_ms == 1500 and paras[0].flat == "Marie entra dans la pièce."
    again = ai.annotate(new, FakeClient([json.dumps({"paragraphes": [{"n": 1, "emotion": "calme"}]})]), [],
                        pauses=False)
    assert ai.apply_suggestions(new, again.paragraphs).startswith("[calme] Marie entra dans la pièce. [pause 1.5s]")
    assert "« pause »" not in ai.system_prompt(False) and "« pause »" in ai.system_prompt(True)


def test_rate_and_emphasis_suggestions():
    text = "[lent] Il ne reviendrait *jamais*.\n\nIl courut vers la porte sans se retourner.\n\nTout était fini."
    _parts, paras = ai.split_paragraphs(text)
    assert paras[0].rate == "lent" and paras[0].emphasis == ["jamais"] and paras[0].body.startswith("Il ne")
    answer = json.dumps({"paragraphes": [
        {"n": 2, "debit": "Rapide", "insister": ["porte", "inventé", "sans se retourner"]},
        {"n": 3, "debit": "très lent", "insister": "fini"},
        {"n": 1, "debit": "lent"}]})
    client = FakeClient([answer])
    result = ai.annotate(text, client, [])
    got = {s.number: (s.rate, s.emphasis) for s in result.paragraphs}
    assert got == {2: ("rapide", ["porte", "sans se retourner"]), 3: ("très lent", ["fini"])}
    assert '"debit"' in client.calls[-1][2]["messages"][0]["content"]
    new = ai.apply_suggestions(text, result.paragraphs)
    assert new == ("[lent] Il ne reviendrait *jamais*.\n\n[rapide] Il courut vers la *porte* *sans se retourner*."
                   "\n\n[très lent] Tout était *fini*.")
    # sans l'option : ni débit ni mise en valeur demandés, les balises existantes sont gardées
    plain = ai.annotate(new, FakeClient([json.dumps({"paragraphes": [{"n": 1, "emotion": "triste"}]})]), [],
                        prosody=False)
    assert ai.apply_suggestions(new, plain.paragraphs).startswith("[triste] [lent] Il ne reviendrait *jamais*.")
    assert '"debit"' not in ai.system_prompt(prosody=False)
