import pytest
from sqlalchemy import select

from app.models import AppSetting, Voice, VoiceEngineProfile, VoiceSample
from app.services import builtin_voices as bv
from app.services import generation, storage, voices
from tests.fakes import FakeEngine

CATALOG = [
    {"key": "Fake Female", "gender": "female", "pitch_hz": 220},
    {"key": "Fake Male", "gender": "male", "pitch_hz": 95},
]


@pytest.fixture
def fake_builtins(monkeypatch):
    monkeypatch.setattr(bv, "ENGINE", "fake")
    monkeypatch.setattr(bv, "CATALOG", CATALOG)


def seed(s, runner):
    job = bv.start_seeding(s)
    runner.run_one(job.id)
    s.expire_all()
    return job


def test_seeding_creates_ready_voices_with_voiceprint_and_sample(db, fake_builtins):
    s, runner = db
    job = bv.start_seeding(s)
    # Rows exist immediately so the library can show them as processing.
    assert {v.status for v in s.scalars(select(Voice))} == {"processing"}
    runner.run_one(job.id)
    s.expire_all()
    vs = {v.name: v for v in s.scalars(select(Voice))}
    assert set(vs) == {"Fake Female", "Fake Male"}
    for v in vs.values():
        assert v.status == "ready" and v.source == "builtin" and v.consent_note
        assert v.preview_path and storage.resolve(v.preview_path).is_file()
        prof = s.scalar(select(VoiceEngineProfile).where(VoiceEngineProfile.voice_id == v.id))
        assert prof.data["builtin"] == v.builtin_key
        smp = s.scalar(select(VoiceSample).where(VoiceSample.voice_id == v.id))
        assert smp.transcript == bv.SAMPLE_TEXT and smp.transcript_source == "builtin"
        assert smp.kind == "builtin" and smp.transcript_segments[0]["text"] == bv.SAMPLE_TEXT
    assert vs["Fake Female"].gender == "female" and vs["Fake Male"].gender == "male"
    # Upload-quality ratings don't apply to studio voices (a short sample isn't "Poor").
    assert all(v.quality_rating is None for v in vs.values())


def test_builtin_voice_generates_without_rebuilding_its_voiceprint(db, fake_builtins):
    s, runner = db
    seed(s, runner)
    v = s.scalar(select(Voice).where(Voice.name == "Fake Male"))
    before = FakeEngine.voices_created
    gen, job = generation.create_generation(s, voice_id=v.id, script="Ready to use.", language="en")
    runner.run_one(job.id)
    s.expire_all()
    assert generation.get_generation(s, gen.id).status == "done"
    assert FakeEngine.voices_created == before  # used the built-in latents as-is


def test_builtin_sample_serves_as_exact_transcript_reference(db, fake_builtins):
    s, runner = db
    seed(s, runner)
    v = voices.get_voice(s, s.scalar(select(Voice.id).where(Voice.name == "Fake Female")))
    ref = voices._transcript_reference(v, max_seconds=60)
    assert ref.text == bv.SAMPLE_TEXT and ref.start is None


def test_startup_seeds_once_and_restore_brings_back_deleted(db, fake_builtins):
    s, runner = db
    bv.seed_on_startup(s)
    assert s.get(AppSetting, bv.SEEDED_FLAG) is not None
    job = s.scalars(select(Voice)).all()
    assert len(job) == 2
    runner.run_one(s.scalar(select(__import__("app.models", fromlist=["Job"]).Job.id)))
    s.expire_all()
    female = s.scalar(select(Voice).where(Voice.name == "Fake Female"))
    voices.delete_voice(s, female.id)
    bv.seed_on_startup(s)  # already seeded: deleted built-ins stay deleted
    assert [e["key"] for e in bv.missing(s)] == ["Fake Female"]
    assert s.scalar(select(Voice).where(Voice.name == "Fake Female")) is None
    seed(s, runner)  # Restore
    assert bv.missing(s) == []
    assert s.scalar(select(Voice).where(Voice.name == "Fake Female")).status == "ready"
    assert bv.start_seeding(s) is None  # nothing to do


def test_transcription_skips_builtin_samples(db, fake_builtins, monkeypatch):
    from app.services import transcription

    calls = []
    monkeypatch.setattr(transcription, "transcribe_file", lambda p, lang: calls.append(p) or [])
    monkeypatch.setattr(transcription, "is_installed", lambda: True)
    s, runner = db
    seed(s, runner)
    v = voices.get_voice(s, s.scalar(select(Voice.id).where(Voice.name == "Fake Male")))
    assert voices.transcribe_samples(s, v, None, (0, 1), force=True) == 0
    assert calls == []


def test_api_restore_and_missing(db, fake_builtins):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_api_flow import wait_job

    with TestClient(app) as client:
        assert client.get("/api/v1/voices/builtin/missing").json() == ["Fake Female", "Fake Male"]
        r = client.post("/api/v1/voices/builtin/restore")
        assert wait_job(client, r.json()["job_id"])["status"] == "succeeded"
        assert client.get("/api/v1/voices/builtin/missing").json() == []
        assert client.post("/api/v1/voices/builtin/restore").json() is None
        listed = client.get("/api/v1/voices").json()
        assert {(v["name"], v["source"], v["gender"]) for v in listed} == {
            ("Fake Female", "builtin", "female"),
            ("Fake Male", "builtin", "male"),
        }


def test_real_catalog_is_balanced_and_unique():
    from app.services.builtin_voices import CATALOG as REAL

    keys = [e["key"] for e in REAL]
    assert len(keys) == len(set(keys)) >= 10
    assert sum(e["gender"] == "female" for e in REAL) >= 5
    assert sum(e["gender"] == "male" for e in REAL) >= 5


def test_profile_file_keys_ignore_plain_text_values(tmp_path):
    from app.engines.base import VoiceProfile

    p = VoiceProfile(
        "x",
        "1",
        tmp_path,
        {
            "latents": "a.pt",
            "ref_audio": "ref.wav",
            "ref_text": "Hello there.",
            "builtin": "Fake Male",
        },
    )
    assert sorted(p.file_keys()) == ["latents", "ref_audio"]
