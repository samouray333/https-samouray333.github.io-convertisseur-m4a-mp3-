"""Langues autres que l'anglais : découpage japonais, glossaire, passages inventés par Whisper, choix du
traducteur."""

from doublys.core import segment, translate
from doublys.core.models import AUTO_LANGUAGE, LANGUAGES, DubSettings, Project


def test_japanese_lines_and_sentences():
    w = [[0, 0.3, "みんな", 1], [0.3, 0.4, "、", 1], [0.4, 0.8, "行くぞ", 1], [0.8, 0.9, "！", 1],
         [1.0, 1.5, "変身", 1], [1.5, 1.6, "！", 1]]
    assert [ln.en for ln in segment.lines_from_words(w)] == ["みんな、行くぞ！", "変身！"]
    assert translate.split_sentences("大丈夫か？怪我はないか？") == ["大丈夫か？", "怪我はないか？"]


def test_glossary():
    from doublys.core import pipeline

    pr = Project()
    pr.settings.glossary = [["変身", "Henshin"], ["Red Ranger", "Ranger Rouge"], ["Gokaiger", ""]]
    terms = pipeline.glossary(pr)
    assert ("Gokaiger", "Gokaiger") in terms
    assert pipeline.apply_glossary("変身！", terms) == "Henshin！"
    assert pipeline.apply_glossary("Go, red ranger!", terms) == "Go, Ranger Rouge!"


def test_language_setting():
    s = DubSettings(source_language=AUTO_LANGUAGE)
    assert s.language == "en"
    s.detected_language = "ja"
    assert s.language == "ja"
    assert all(len(v) == 4 and (v[2] or v[3] or k == "en") for k, v in LANGUAGES.items())


def test_whisper_hallucination_filter():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doublys" / "worker"))
    import tts_worker

    class Seg:
        def __init__(self, text):
            self.text, self.compression_ratio, self.no_speech_prob, self.avg_logprob = text, None, 0.0, 0.0

    assert tts_worker.is_hallucination(Seg("中国語でやると、" * 6))
    assert not tts_worker.is_hallucination(Seg("Go go go go go!"))
    assert not tts_worker.is_hallucination(Seg("いくぞ！いくぞ！"))
    assert not tts_worker.is_hallucination(Seg("Hello there, how are you?"))


def test_opus_unknown_c_cedilla():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "doublys" / "worker"))
    import tts_worker

    class Tok:
        unk_token, pad_token, eos_token = "<unk>", "<pad>", "</s>"

    assert tts_worker.fix_unknown("<pad> <unk>a a l'air bizarre.</s>", Tok()) == "Ça a l'air bizarre."
    assert tts_worker.fix_unknown("<pad> <unk>a va ?</s>", Tok()) == "Ça va ?"
