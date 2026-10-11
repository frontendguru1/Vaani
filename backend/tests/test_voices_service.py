import io

import pytest
from sqlalchemy import select

from app.models import Generation, GenerationChunk, Job, Voice, VoiceEngineProfile, VoiceSample
from app.services import generation, storage, voices
from app.services.errors import Invalid
from tests.fakes import FakeEngine
from tests.helpers import speech_wav_bytes

CONSENT = "My own voice, recorded by me for personal use."


def make_voice(session, runner, files=None, **kw):
    files = files or [("a.wav", speech_wav_bytes(8)), ("b.wav", speech_wav_bytes(9, f0=155))]
    uploads = [voices.Upload(n, io.BytesIO(b)) for n, b in files]
    voice, job = voices.create_voice(
        session,
        name=kw.get("name", "Me"),
        language=kw.get("language", "en"),
        consent_note=kw.get("consent", CONSENT),
        uploads=uploads,
    )
    runner.run_one(job.id)
    session.expire_all()
    return session.get(Voice, voice.id), session.get(Job, job.id)


def test_create_voice_processes_samples_and_caches_voiceprint(db):
    s, runner = db
    voice, job = make_voice(s, runner)
    assert job.status == "succeeded", job.error
    assert voice.status == "ready"
    assert voice.quality_rating in {"good", "okay"}
    assert voice.speech_seconds > 14
    assert voice.preview_path and storage.resolve(voice.preview_path).is_file()
    assert len(voice.samples) == 2
    for smp in voice.samples:
        assert storage.resolve(smp.original_path).is_file()
        assert storage.resolve(smp.processed_path).is_file()
        assert smp.quality["rating"] in {"good", "okay"}
        assert smp.segments
    prof = s.scalar(select(VoiceEngineProfile).where(VoiceEngineProfile.voice_id == voice.id))
    assert prof.engine == "fake" and prof.engine_version == "fake-1"
    assert (storage.resolve(prof.cache_dir) / "emb.npy").is_file()
    assert job.result["voiceprint"] == "computed"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("consent", "", "consent_required"),
        ("consent", "yes", "consent_required"),
        ("name", "  ", "name_required"),
        ("language", "fr", "language"),
    ],
)
def test_validation(db, field, value, code):
    s, _ = db
    kw = {"name": "Me", "language": "en", "consent": CONSENT, field: value}
    with pytest.raises(Invalid) as e:
        voices.create_voice(
            s,
            name=kw["name"],
            language=kw["language"],
            consent_note=kw["consent"],
            uploads=[voices.Upload("a.wav", io.BytesIO(speech_wav_bytes()))],
        )
    assert e.value.code == code
    assert s.scalar(select(Voice)) is None


def test_rejects_bad_file_types_and_empty_files(db):
    s, _ = db
    with pytest.raises(Invalid, match="unsupported"):
        voices.create_voice(
            s,
            name="x",
            language="en",
            consent_note=CONSENT,
            uploads=[voices.Upload("notes.txt", io.BytesIO(b"hi"))],
        )
    with pytest.raises(Invalid, match="empty"):
        voices.create_voice(
            s,
            name="x",
            language="en",
            consent_note=CONSENT,
            uploads=[voices.Upload("a.wav", io.BytesIO(b""))],
        )
    # The half-created voice folder is cleaned up.
    assert not any((storage.data_dir() / "voices").glob("*/original/*"))


def test_undecodable_upload_marks_voice_failed(db):
    s, runner = db
    voice, job = make_voice(s, runner, files=[("broken.mp3", b"definitely not audio")])
    assert job.status == "failed"
    assert voice.status == "failed" and voice.error


def test_silent_upload_fails_with_reason(db):
    import numpy as np  # noqa: E401
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.zeros(22050 * 3, dtype=np.float32), 22050, format="WAV")
    s, runner = db
    voice, job = make_voice(s, runner, files=[("silence.wav", buf.getvalue())])
    assert job.status == "failed"
    assert "No speech" in job.error


def test_rename_and_update(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    voices.update_voice(s, voice.id, name="Papa", description="Dad reading")
    assert s.get(Voice, voice.id).name == "Papa"
    with pytest.raises(Invalid):
        voices.update_voice(s, voice.id, consent_note="")


def test_delete_removes_every_row_and_file(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    gen, job = generation.create_generation(
        s, voice_id=voice.id, script="Hello there my friend.", language="en"
    )
    runner.run_one(job.id)
    gen_dir = storage.generation_dir(gen.id)
    assert (gen_dir / "output.wav").is_file()

    report = voices.delete_voice(s, voice.id)
    assert report.leftover_paths == []
    assert report.generations_removed == 1
    assert report.files_removed >= 6
    assert not storage.voice_dir(voice.id).exists() and not gen_dir.exists()
    for model in (Voice, VoiceSample, VoiceEngineProfile, Generation, GenerationChunk, Job):
        assert s.scalar(select(model)) is None, model.__name__


def test_voiceprint_is_cached_across_generations(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    before = FakeEngine.voices_created
    for _ in range(2):
        _gen, job = generation.create_generation(
            s, voice_id=voice.id, script="Testing one two.", language="en"
        )
        runner.run_one(job.id)
        s.expire_all()
        assert s.get(Job, job.id).result["voiceprint_cached"] is True
    assert FakeEngine.voices_created == before


def test_consistency_check_finds_orphans_and_missing_files(db):
    from app.services import maintenance

    s, runner = db
    voice, _ = make_voice(s, runner)
    assert maintenance.check(s).ok

    orphan = storage.data_dir() / "voices" / "01ORPHAN000000000000000000"
    (orphan / "original").mkdir(parents=True)
    (orphan / "original" / "x.wav").write_bytes(b"x")
    storage.resolve(voice.samples[0].processed_path).unlink()

    report = maintenance.check(s)
    assert report.orphan_dirs == [str(orphan)]
    assert any("processed" in m for m in report.missing_files)
    assert maintenance.remove_orphans(report) == 1 and not orphan.exists()
