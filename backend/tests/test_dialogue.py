import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Generation, GenerationChunk, Voice
from app.services import dialogue, generation, storage, voices
from app.services.dialogue import DialogueError, parse_turns
from app.services.errors import Invalid
from tests.fakes import FakeEngine
from tests.test_voices_service import make_voice

VOICES = {"v1": "Papa", "v2": "Meera", "v3": "Dadi Ji"}


def spans(script, turns):
    return [(t.voice_id, script[t.start : t.end].strip()) for t in turns]


def test_tags_hand_lines_to_voices_and_untagged_goes_to_default():
    s = (
        "Once upon a time.\n[Papa]: Beta, what are you reading?\n"
        "[meera]:A story!\n[ dadi  ji ]: Hmm."
    )
    turns = parse_turns(s, "v9", VOICES)
    assert spans(s, turns) == [
        ("v9", "Once upon a time."),
        ("v1", "Beta, what are you reading?"),
        ("v2", "A story!"),
        ("v3", "Hmm."),
    ]


def test_multiline_turns_and_inline_brackets_are_not_tags():
    s = "[Papa]: First line.\nSecond line, same speaker [pause 1s] still Papa.\n[Meera]: Mine."
    turns = parse_turns(s, "v1", VOICES)
    assert spans(s, turns)[0] == (
        "v1",
        "First line.\nSecond line, same speaker [pause 1s] still Papa.",
    )
    assert not dialogue.is_dialogue("Hello [Papa]: not at line start")
    assert not dialogue.is_dialogue("[pause 1s]: dramatic")


def test_unknown_and_ambiguous_speakers():
    with pytest.raises(DialogueError) as e:
        parse_turns("[Ravi]: hi", "v1", VOICES)
    assert e.value.code == "unknown_speaker" and "Ravi" in str(e.value) and "Papa" in str(e.value)
    with pytest.raises(DialogueError) as e:
        parse_turns("[Papa]: hi", "v1", {"a": "Papa", "b": "papa"})
    assert e.value.code == "ambiguous_speaker"


def two_voices(s, runner):
    papa, _ = make_voice(s, runner, name="Papa")
    meera, _ = make_voice(s, runner, name="Meera")
    return papa, meera


SCRIPT = (
    "[Papa]: Beta, what are you reading tonight?\n"
    "[Meera]: [pause 1s] A story about a very big tiger!\n"
    "[Papa]: That sounds exciting, tell me more."
)


def test_dialogue_generation_uses_each_voices_voiceprint(db, monkeypatch):
    s, runner = db
    papa, meera = two_voices(s, runner)
    used = []
    real = FakeEngine.synthesize

    def spy(self, text, profile, language, **kw):
        used.append((profile.cache_dir.parent.parent.name, text))
        return real(self, text, profile, language, **kw)

    monkeypatch.setattr(FakeEngine, "synthesize", spy)
    events = []
    runner.publish = lambda job_id, ev: events.append(ev)
    gen, job = generation.create_generation(s, voice_id=papa.id, script=SCRIPT, language="en")
    assert gen.settings["speakers"] == [papa.id, meera.id]
    runner.run_one(job.id)
    s.expire_all()
    g = generation.get_generation(s, gen.id)
    assert g.status == "done", g.error
    assert [c.voice_id for c in g.chunks] == [None, meera.id, None]
    assert [u[0] for u in used] == [papa.id, meera.id, papa.id]
    assert used[1][1] == "A story about a very big tiger!"  # tag and marker never spoken
    assert g.chunks[0].pause_after_ms == 1000  # marker at turn start replaces turn pause
    assert g.chunks[1].pause_after_ms == 500  # default turn pause
    for c in g.chunks:
        assert g.script[c.char_start : c.char_end] == c.text
    started = [e for e in events if e["type"] == "chunk_started"]
    assert [e["data"]["voice_id"] for e in started] == [papa.id, meera.id, papa.id]
    assert started[1]["message"].endswith("Meera")


def test_dialogue_validation(db):
    s, runner = db
    papa, meera = two_voices(s, runner)
    with pytest.raises(Invalid) as e:
        generation.create_generation(
            s, voice_id=papa.id, script="[Ravi]: hello there.", language="en"
        )
    assert e.value.code == "unknown_speaker"
    meera.consent_note = ""
    s.commit()
    with pytest.raises(Invalid, match="Meera has no consent note"):
        generation.create_generation(s, voice_id=papa.id, script=SCRIPT, language="en")
    with pytest.raises(Invalid, match="nothing to say"):
        generation.create_generation(
            s, voice_id=papa.id, script="[Papa]: [pause 1s]", language="en"
        )


def test_single_speaker_tag_for_another_voice(db):
    s, runner = db
    papa, meera = two_voices(s, runner)
    gen, job = generation.create_generation(
        s, voice_id=papa.id, script="[Meera]: Just me talking today.", language="en"
    )
    assert gen.settings["speakers"] == [meera.id]
    runner.run_one(job.id)
    s.expire_all()
    assert generation.get_generation(s, gen.id).status == "done"


def test_deleting_a_speaker_deletes_the_dialogues_they_spoke_in(db):
    s, runner = db
    papa, meera = two_voices(s, runner)
    gen, job = generation.create_generation(s, voice_id=papa.id, script=SCRIPT, language="en")
    runner.run_one(job.id)
    s.expire_all()
    out_dir = storage.generation_dir(gen.id)
    assert (out_dir / "output.wav").is_file()
    report = voices.delete_voice(s, meera.id)  # Meera only spoke lines; Papa owns it
    assert report.generations_removed == 1 and report.leftover_paths == []
    assert not out_dir.exists()
    assert s.get(Generation, gen.id) is None
    assert s.scalar(select(GenerationChunk).where(GenerationChunk.generation_id == gen.id)) is None
    assert s.get(Voice, papa.id) is not None  # the other speaker is untouched


def test_api_lists_speakers(db):
    s, runner = db
    papa, meera = two_voices(s, runner)
    gen, job = generation.create_generation(s, voice_id=papa.id, script=SCRIPT, language="en")
    runner.run_one(job.id)
    with TestClient(app) as client:
        item = client.get("/api/v1/generations").json()[0]
        assert item["speakers"] == ["Papa", "Meera"]
        detail = client.get(f"/api/v1/generations/{gen.id}").json()
        assert [c["voice_id"] for c in detail["chunks"]] == [None, meera.id, None]
