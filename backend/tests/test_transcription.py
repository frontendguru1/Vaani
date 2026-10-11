import pytest
from sqlalchemy import select

from app.models import Job, VoiceEngineProfile, VoiceSample
from app.services import generation, transcription, voices
from app.services.errors import Invalid
from app.services.transcription import Phrase, best_window
from tests.fakes import FakeEngine
from tests.test_voices_service import make_voice

PHRASES = [
    {"start": 0.0, "end": 2.5, "text": "Hello there."},
    {"start": 2.6, "end": 6.0, "text": "This is a test."},
    {"start": 6.2, "end": 11.5, "text": "It has several phrases."},
    {"start": 11.6, "end": 20.0, "text": "And a long last one."},
]


def test_best_window_picks_longest_run_within_limit():
    start, end, text = best_window(PHRASES, max_seconds=12)
    assert (start, end) == (0.0, 11.5)
    assert text == "Hello there. This is a test. It has several phrases."


def test_best_window_respects_minimum_and_limit():
    assert best_window(PHRASES, max_seconds=2) is None
    assert best_window([], max_seconds=12) is None
    s, e, _ = best_window(PHRASES, max_seconds=9)
    assert e - s <= 9


@pytest.fixture
def fake_whisper(monkeypatch):
    calls = []

    def fake(path, language):
        calls.append((path.name, language))
        return [Phrase(0.0, 3.0, "Pehla vakya."), Phrase(3.1, 7.2, "Doosra vakya yahan hai.")]

    monkeypatch.setattr(transcription, "transcribe_file", fake)
    monkeypatch.setattr(transcription, "is_installed", lambda: True)
    return calls


def test_transcribe_job_fills_phrases_and_keeps_user_transcripts(db, fake_whisper):
    s, runner = db
    voice, _ = make_voice(s, runner)
    first = voice.samples[0]
    first.transcript, first.transcript_source = "Typed by me.", "user"
    s.commit()

    job = voices.start_transcription(s, voice.id)
    runner.run_one(job.id)
    s.expire_all()
    assert s.get(Job, job.id).status == "succeeded"
    assert s.get(Job, job.id).result["transcribed"] == 2
    a, b = s.scalars(
        select(VoiceSample).where(VoiceSample.voice_id == voice.id).order_by(VoiceSample.created_at)
    ).all()
    assert a.transcript == "Typed by me." and a.transcript_source == "user"
    assert (
        b.transcript == "Pehla vakya. Doosra vakya yahan hai." and b.transcript_source == "whisper"
    )
    assert len(b.transcript_segments) == 2 and a.transcript_segments
    assert fake_whisper[0][1] == "en"


def test_transcript_engine_uses_a_cut_whisper_window(db, fake_whisper, monkeypatch):
    s, runner = db
    voice, _ = make_voice(s, runner)
    runner.run_one(voices.start_transcription(s, voice.id).id)
    s.expire_all()

    monkeypatch.setattr(FakeEngine, "needs_transcript", True)
    monkeypatch.setattr(FakeEngine, "max_ref_seconds", 12.0, raising=False)
    seen = {}
    real = FakeEngine.create_voice

    def spy(self, refs, cache_dir, transcripts=None):
        seen["refs"], seen["text"] = refs, transcripts
        return real(self, refs, cache_dir, transcripts)

    monkeypatch.setattr(FakeEngine, "create_voice", spy)
    voices.invalidate_transcript_profiles(s, voice.id)
    s.commit()
    gen, job = generation.create_generation(
        s, voice_id=voice.id, script="Namaste duniya.", language="en"
    )
    runner.run_one(job.id)
    s.expire_all()
    assert s.get(Job, job.id).status == "succeeded", s.get(Job, job.id).error
    assert seen["text"] == ["Pehla vakya. Doosra vakya yahan hai."]
    assert seen["refs"][0].name == "ref_src.wav"  # cut to the phrase window, not the whole clip


def test_correcting_phrases_marks_user_and_invalidates_transcript_voiceprints(
    db, fake_whisper, monkeypatch
):
    s, runner = db
    voice, _ = make_voice(s, runner)
    runner.run_one(voices.start_transcription(s, voice.id).id)
    s.expire_all()
    monkeypatch.setattr(FakeEngine, "needs_transcript", True)
    # make_voice already built a voiceprint for the (now transcript-needing) fake engine
    assert s.scalar(select(VoiceEngineProfile).where(VoiceEngineProfile.voice_id == voice.id))

    smp = voices.get_voice(s, voice.id).samples[0]
    voices.update_segments(s, voice.id, smp.id, ["First fixed.", "Second fixed."])
    s.expire_all()
    smp = s.get(VoiceSample, smp.id)
    assert smp.transcript == "First fixed. Second fixed." and smp.transcript_source == "user"
    assert smp.transcript_segments[0]["start"] == 0.0  # timestamps kept
    assert (
        s.scalar(select(VoiceEngineProfile).where(VoiceEngineProfile.voice_id == voice.id)) is None
    )
    with pytest.raises(Invalid):
        voices.update_segments(s, voice.id, smp.id, ["only one"])


def test_transcription_failure_never_fails_voice_creation(db, monkeypatch):
    from app.config import get_settings

    def boom(path, language):
        raise RuntimeError("whisper exploded")

    monkeypatch.setattr(transcription, "transcribe_file", boom)
    monkeypatch.setattr(transcription, "is_installed", lambda: True)
    monkeypatch.setattr(get_settings(), "transcribe_on_create", True)
    s, runner = db
    voice, job = make_voice(s, runner)
    assert job.status == "succeeded" and voice.status == "ready"


def test_api_transcribe_and_correct(db, fake_whisper):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_api_flow import wait_job

    s, runner = db
    voice, _ = make_voice(s, runner)
    with TestClient(app) as client:
        r = client.post(f"/api/v1/voices/{voice.id}/transcribe")
        assert r.status_code == 202
        assert wait_job(client, r.json()["job_id"])["status"] == "succeeded"
        detail = client.get(f"/api/v1/voices/{voice.id}").json()
        assert detail["has_transcripts"] is True
        sid = detail["samples"][0]["id"]
        r = client.put(
            f"/api/v1/voices/{voice.id}/samples/{sid}/transcript", json={"texts": ["Ek.", "Do."]}
        )
        assert r.status_code == 200
        assert r.json()["samples"][0]["transcript"] == "Ek. Do."
        assert "transcription" in client.get("/api/v1/health").json()


def test_typed_transcript_at_upload_is_marked_user(db):
    import io

    from tests.helpers import speech_wav_bytes

    s, _ = db
    voice, _job = voices.create_voice(
        s,
        name="T",
        language="en",
        consent_note="My own voice, for testing.",
        uploads=[
            voices.Upload("a.wav", io.BytesIO(speech_wav_bytes(5)), transcript="Exact words.")
        ],
    )
    smp = voices.get_voice(s, voice.id).samples[0]
    assert smp.transcript == "Exact words." and smp.transcript_source == "user"
