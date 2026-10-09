import pytest

from audiolivre.core.models import LexiconEntry
from audiolivre.core.textproc import (NormalizeOptions, chunk_text, clean_imported_text, find_characters,
                                      normalize_for_speech, parse_script, roman_to_int, split_sentences)

FR = NormalizeOptions(language="fr")
EN = NormalizeOptions(language="en")


@pytest.mark.parametrize("src, expected", [
    ("M. Dupont arrive.", "Monsieur Dupont arrive."),
    ("Mme Martin et Mlle Rose", "Madame Martin et Mademoiselle Rose"),
    ("à 14h30", "à quatorze heures trente"),
    ("à 1h05", "à une heure cinq"),
    ("12,50 €", "douze euros cinquante"),
    ("0,50 €", "cinquante centimes"),
    ("15 %", "quinze pour cent"),
    ("le 1er mai", "le premier mai"),
    ("la 2e fois", "la deuxième fois"),
    ("au XIXe siècle", "au dix-neuvième siècle"),
    ("Louis XIV", "Louis quatorze"),
    ("François Ier", "François premier"),
    ("Chapitre IV", "Chapitre quatre"),
    ("10 000 habitants", "dix mille habitants"),
    ("3,05 km", "trois virgule zéro cinq kilomètres"),
    ("1914-1918", "mille neuf cent quatorze à mille neuf cent dix-huit"),
    ("le 12/05/2024", "le douze mai deux mille vingt-quatre"),
])
def test_normalize_fr(src, expected):
    assert expected in normalize_for_speech(src, FR)


@pytest.mark.parametrize("src", ["Ce matin, Le chat dort.", "Monsieur X est venu.", "Madame L. aussi."])
def test_no_false_roman(src):
    out = normalize_for_speech(src, FR)
    assert "cent" not in out and "dix" not in out and "cinquante" not in out


def test_normalize_en():
    out = normalize_for_speech("Mr. Smith paid $12.50 at 3:05 in 1984. Elizabeth II.", EN)
    assert "Mister Smith" in out
    assert "twelve dollars and fifty cents" in out
    assert "nineteen eighty-four" in out
    assert "Elizabeth the Second" in out


def test_lexicon():
    lex = [LexiconEntry("GIEC", "gièque", case_sensitive=True)]
    assert normalize_for_speech("Le GIEC alerte.", FR, lex) == "Le gièque alerte."
    regex = [LexiconEntry(r"\bSaint-Saëns\b", "Saint-Sanss", regex=True)]
    assert "Saint-Sanss" in normalize_for_speech("Saint-Saëns composa.", FR, regex)


def test_etc_keeps_sentence_end():
    out = normalize_for_speech("Des pommes, etc. Puis il partit.", FR)
    assert "et cetera. Puis" in out


def test_split_sentences():
    s = split_sentences("Il dit : « Viens ! » Puis il partit. J. Dupont arriva... Ensuite ? Oui.")
    assert s[0].startswith("Il dit")
    assert any(x.startswith("J. Dupont") for x in s)


def test_chunk_respects_limit():
    text = "Une phrase assez longue pour le test du découpage. " * 30
    chunks = chunk_text(text, 120, 20)
    assert all(len(c) <= 140 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunk_long_sentence_without_punctuation():
    text = "mot " * 200
    chunks = chunk_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)


def test_parse_script_markup():
    items = parse_script("# Titre\n\nTexte.\n\n[pause 2s]\n\n@Marie: Bonjour !\n\n[voix:Paul]\nSalut.\n\n[/voix]\n\n"
                         "— Dialogue.\n\n%% commentaire\n\nAvant [pause:500ms] après.", detect_dialogues=True)
    kinds = [(i.kind, i.voice_key, i.pause_ms) for i in items]
    assert kinds[0][0] == "heading"
    assert ("pause", None, 2000) in kinds
    assert ("para", "Marie", 0) in kinds
    assert ("para", "Paul", 0) in kinds
    assert ("para", "__dialogue__", 0) in kinds
    assert ("pause", None, 500) in kinds
    assert not any("commentaire" in i.text for i in items)


def test_find_characters():
    assert find_characters("@Marie: x\n[voix:Paul]\n@narrateur: y\n@Marie: z") == ["Marie", "Paul"]


def test_clean_imported_text():
    out = clean_imported_text("Un exem-\nple de texte\ncoupé.\n\n12\n\nNote¹ ici[3].")
    assert "exemple de texte coupé." in out
    assert "\n12\n" not in out
    assert "Note ici." in out


def test_roman():
    assert roman_to_int("XIV") == 14
    assert roman_to_int("IL") is None


@pytest.mark.parametrize("src,dialogue,spoken", [
    ("- Bonjour, dit Marie.", True, "Bonjour, dit Marie."),
    ("-Bonjour, dit Marie.", True, "Bonjour, dit Marie."),
    ("—Salut.", True, "Salut."),
    ("- Viens ici - dit-il - tout de suite.", True, "Viens ici, dit-il, tout de suite."),
    ("-Bonjour, dit-il. -Salut, répondit Paul.", True, "Bonjour, dit-il. Salut, répondit Paul."),
    ("-5 degrés ce matin.", False, "moins cinq degrés ce matin."),
    ("Un porte-monnaie rouge-vif.", False, "Un porte-monnaie rouge-vif."),
])
def test_hyphen_dialogues(src, dialogue, spoken):
    from audiolivre.core.textproc import parse_script

    items = [i for i in parse_script(src, detect_dialogues=True) if i.kind == "para"]
    assert (items[0].voice_key == "__dialogue__") is dialogue
    assert normalize_for_speech(src) == spoken
