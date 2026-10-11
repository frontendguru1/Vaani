import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import PronunciationEntry
from app.services import generation, pronunciation
from app.services.errors import Conflict, Invalid
from tests.fakes import FakeEngine
from tests.test_voices_service import make_voice


def E(term, rep, lang=None, cs=False, id_=None):  # noqa: N802
    return PronunciationEntry(
        id=id_ or term, term=term, replacement=rep, language=lang, case_sensitive=cs
    )


def apply(text, lang, entries):
    return pronunciation.apply(text, lang, entries)[0]


def test_whole_words_only():
    es = [E("IIT", "I I T")]
    assert apply("I studied at IIT Delhi.", "en", es) == "I studied at I I T Delhi."
    assert apply("IITians are smart", "en", es) == "IITians are smart"
    assert apply("(IIT)", "en", es) == "(I I T)"


def test_case_insensitive_by_default_and_case_sensitive_when_asked():
    assert apply("vaani and VAANI", "en", [E("Vaani", "Vaa-nee")]) == "Vaa-nee and Vaa-nee"
    assert apply("US and us", "en", [E("US", "U S", cs=True)]) == "U S and us"


def test_longest_term_wins_and_no_cascading():
    es = [E("York", "Yawk"), E("New York", "Noo Yawk"), E("Yawk", "SHOULD NOT APPEAR")]
    out = apply("New York and York", "en", es)
    assert out == "Noo Yawk and Yawk"


def test_devanagari_word_boundaries_respect_vowel_signs():
    es = [E("राम", "रा-म")]
    assert apply("राम घर गया", "hi", es) == "रा-म घर गया"
    # "रामा" continues with a vowel sign (ा, a combining mark) — must not match.
    assert apply("रामा घर गया", "hi", es) == "रामा घर गया"
    assert apply("रामायण", "hi", es) == "रामायण"


def test_language_scoping():
    es = [E("Ji", "जी", lang="hi"), E("GIF", "jif", lang="en"), E("Rahul", "Raa-hul")]
    assert apply("GIF Ji Rahul", "en", es) == "jif Ji Raa-hul"
    assert apply("GIF Ji Rahul", "hi", es) == "GIF जी Raa-hul"


def test_counts_and_multiword_across_whitespace():
    text, applied = pronunciation.apply("New\nYork, new york!", "en", [E("New York", "NYC")])
    assert text == "NYC, NYC!"
    assert applied[0].count == 2


def test_regex_characters_are_literal():
    assert apply("C++ and C", "en", [E("C++", "C plus plus")]) == "C plus plus and C"


def test_crud_validation(db):
    s, _ = db
    e = pronunciation.create_entry(s, " Vaani ", "Vaa-nee")
    assert e.term == "Vaani"
    with pytest.raises(Conflict):
        pronunciation.create_entry(s, "vaani", "other")
    pronunciation.create_entry(s, "vaani", "वाणी", language="hi")  # different scope is fine
    with pytest.raises(Invalid):
        pronunciation.create_entry(s, "", "x")
    with pytest.raises(Invalid):
        pronunciation.create_entry(s, "same", "SAME")
    with pytest.raises(Invalid):
        pronunciation.create_entry(s, "x", "y", language="fr")
    pronunciation.update_entry(s, e.id, replacement="Vah-nee")
    assert s.get(PronunciationEntry, e.id).replacement == "Vah-nee"
    pronunciation.delete_entry(s, e.id)
    assert s.get(PronunciationEntry, e.id) is None


def test_generation_speaks_fixed_text_but_keeps_script(db, monkeypatch):
    s, runner = db
    voice, _ = make_voice(s, runner)
    pronunciation.create_entry(s, "Vaani", "Vaa-nee")
    spoken = []
    real = FakeEngine.synthesize

    def spy(self, text, profile, language, **kw):
        spoken.append(text)
        return real(self, text, profile, language, **kw)

    monkeypatch.setattr(FakeEngine, "synthesize", spy)
    script = "Welcome to Vaani, my friend. Nothing to fix in this one."
    gen, job = generation.create_generation(s, voice_id=voice.id, script=script, language="en")
    runner.run_one(job.id)
    s.expire_all()
    g = generation.get_generation(s, gen.id)
    assert g.status == "done"
    assert g.script == script
    assert g.chunks[0].text == "Welcome to Vaani, my friend."
    assert g.chunks[0].spoken_text == "Welcome to Vaa-nee, my friend."
    assert g.chunks[1].spoken_text is None
    assert spoken == ["Welcome to Vaa-nee, my friend.", "Nothing to fix in this one."]


def test_api(db):
    with TestClient(app) as client:
        r = client.post("/api/v1/pronunciations", json={"term": "GIF", "replacement": "jif"})
        assert r.status_code == 201
        eid = r.json()["id"]
        assert (
            client.post(
                "/api/v1/pronunciations", json={"term": "gif", "replacement": "x"}
            ).status_code
            == 409
        )
        r = client.post(
            "/api/v1/pronunciations/preview", json={"text": "A GIF is a gif.", "language": "en"}
        )
        assert r.json() == {
            "text": "A jif is a jif.",
            "applied": [{"term": "GIF", "replacement": "jif", "count": 2}],
        }
        assert (
            client.patch(f"/api/v1/pronunciations/{eid}", json={"case_sensitive": True}).json()[
                "case_sensitive"
            ]
            is True
        )
        assert [e["term"] for e in client.get("/api/v1/pronunciations").json()] == ["GIF"]
        assert client.delete(f"/api/v1/pronunciations/{eid}").status_code == 204
        assert client.delete(f"/api/v1/pronunciations/{eid}").status_code == 404
