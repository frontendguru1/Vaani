import numpy as np
import pytest
from sqlalchemy import select

from app.models import Generation, Job
from app.services import audio, generation, storage
from app.services.errors import Invalid, NotFound
from app.services.stitching import stitch, trim_silence
from tests.fakes import FakeEngine
from tests.test_voices_service import make_voice

SCRIPT = (
    "This is the first sentence of the script. Here comes a second one.\n\n"
    "A brand new paragraph starts here. And it finally ends right here."
)


def test_generation_produces_stitched_audio_with_offsets(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    gen, job = generation.create_generation(
        s, voice_id=voice.id, script=SCRIPT, language="en", settings={"speed": 1.1, "bogus": 1}
    )
    assert gen.settings == {"speed": 1.1}
    assert gen.chunk_count == 4
    runner.run_one(job.id)
    s.expire_all()
    gen = generation.get_generation(s, gen.id)
    assert gen.status == "done", gen.error
    out = storage.resolve(gen.audio_path)
    data, sr = audio.read_mono(out)
    assert sr == FakeEngine.sample_rate
    assert abs(len(data) / sr - gen.duration_seconds) < 0.05
    offsets = [c.offset_seconds for c in gen.chunks]
    assert offsets == sorted(offsets) and offsets[0] == 0
    assert all(c.status == "done" and c.duration_seconds for c in gen.chunks)
    assert gen.device == "cpu"
    # Paragraph pause is longer than the sentence pause.
    assert gen.chunks[1].pause_after_ms > gen.chunks[0].pause_after_ms


def test_mp3_export_is_created_on_demand(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    gen, job = generation.create_generation(
        s, voice_id=voice.id, script="Short test line here.", language="en"
    )
    runner.run_one(job.id)
    s.expire_all()
    mp3 = generation.audio_file(s, gen.id, "mp3")
    assert mp3.suffix == ".mp3" and mp3.stat().st_size > 0


def test_blocked_without_consent_or_unknown_inputs(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    voice.consent_note = ""
    s.commit()
    with pytest.raises(Invalid, match="consent"):
        generation.create_generation(s, voice_id=voice.id, script="Hi there.", language="en")
    with pytest.raises(NotFound):
        generation.create_generation(s, voice_id="nope", script="Hi.", language="en")


def test_rejects_bad_requests(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    with pytest.raises(Invalid, match="script"):
        generation.create_generation(s, voice_id=voice.id, script="   ", language="en")
    with pytest.raises(Invalid, match="support"):
        generation.create_generation(s, voice_id=voice.id, script="Hola.", language="es")
    with pytest.raises(Invalid, match="Unknown engine"):
        generation.create_generation(
            s, voice_id=voice.id, script="Hi.", language="en", engine="nope"
        )


def test_failure_marks_generation_failed(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    FakeEngine.fail_on = "explode"
    try:
        gen, job = generation.create_generation(
            s, voice_id=voice.id, script="Fine sentence here. Now explode please.", language="en"
        )
        runner.run_one(job.id)
    finally:
        FakeEngine.fail_on = None
    s.expire_all()
    assert s.get(Job, job.id).status == "failed"
    assert s.get(Generation, gen.id).status == "failed"
    assert "boom" in s.get(Generation, gen.id).error


def test_regenerate_and_delete(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    gen, job = generation.create_generation(
        s, voice_id=voice.id, script="Again and again.", language="en"
    )
    runner.run_one(job.id)
    gen2, job2 = generation.regenerate(s, gen.id)
    assert gen2.id != gen.id and gen2.script == gen.script
    runner.run_one(job2.id)
    s.expire_all()
    assert len(generation.list_generations(s, voice.id)) == 2
    removed = generation.delete_generation(s, gen.id)
    assert removed >= 2 and not storage.generation_dir(gen.id).exists()
    assert s.scalar(select(Job).where(Job.generation_id == gen.id)) is None


def test_progress_events_are_published_in_order(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    events = []
    runner.publish = lambda job_id, ev: events.append(ev)
    gen, job = generation.create_generation(s, voice_id=voice.id, script=SCRIPT, language="en")
    runner.run_one(job.id)
    kinds = [e["type"] for e in events]
    assert kinds.count("chunk_started") == 4 and kinds.count("chunk_done") == 4
    assert kinds[-1] == "succeeded"
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress)
    started = [e for e in events if e["type"] == "chunk_started"]
    assert (
        SCRIPT[started[1]["data"]["start"] : started[1]["data"]["end"]]
        == "Here comes a second one."
    )


def test_stitch_inserts_pauses_and_offsets():
    sr = 1000
    a, b = np.ones(500, dtype=np.float32) * 0.5, np.ones(300, dtype=np.float32) * 0.5
    out, offsets = stitch([a, b], [200, 0], sr, trim=False)
    assert len(out) == 500 + 200 + 300
    assert offsets == [0.0, 0.7]
    assert out[0] == 0 and out[499] == 0  # faded edges, no clicks
    assert np.all(out[500:700] == 0)


def test_trim_silence_keeps_a_little_padding():
    sr = 1000
    x = np.concatenate([np.zeros(300), np.ones(200) * 0.5, np.zeros(300)]).astype(np.float32)
    y = trim_silence(x, sr, keep_ms=40)
    assert 270 <= len(y) <= 300


def test_cold_model_reports_loading_step(db):
    from app.engines import registry

    s, runner = db
    voice, _ = make_voice(s, runner)
    registry.get_engine("fake").unload()
    events = []
    runner.publish = lambda job_id, ev: events.append(ev)
    _gen, job = generation.create_generation(
        s, voice_id=voice.id, script="Cold start here.", language="en"
    )
    runner.run_one(job.id)
    steps = [e["step"] for e in events]
    assert "loading_model" in steps
    assert steps.index("loading_model") < steps.index("synthesizing")


def test_transcript_engine_fails_fast_without_a_transcribed_clip(db, monkeypatch):
    s, runner = db
    voice, _ = make_voice(s, runner)
    monkeypatch.setattr(FakeEngine, "needs_transcript", True)
    monkeypatch.setattr(FakeEngine, "max_ref_seconds", 12.0, raising=False)
    with pytest.raises(Invalid) as e:
        generation.create_generation(s, voice_id=voice.id, script="Hello there.", language="en")
    assert e.value.code == "needs_transcript"
    assert "12 seconds" in e.value.message
    assert s.scalar(select(Job).where(Job.kind == "generate")) is None  # nothing queued


def test_pause_markers_end_to_end(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    script = "[pause 1s] First line is spoken here. [pause 2s] Second line is spoken here."
    gen, job = generation.create_generation(s, voice_id=voice.id, script=script, language="en")
    assert gen.settings["lead_pause_ms"] == 1000
    runner.run_one(job.id)
    s.expire_all()
    g = generation.get_generation(s, gen.id)
    assert g.status == "done", g.error
    assert [c.text for c in g.chunks] == [
        "First line is spoken here.",
        "Second line is spoken here.",
    ]
    assert g.chunks[0].pause_after_ms == 2000
    assert g.chunks[0].offset_seconds == pytest.approx(1.0, abs=0.01)  # after the lead-in
    gap = g.chunks[1].offset_seconds - (g.chunks[0].offset_seconds + 0)
    assert gap > 2.0  # chunk 0 audio + the 2 s pause


def test_bad_pause_marker_is_a_clear_error(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    with pytest.raises(Invalid) as e:
        generation.create_generation(
            s, voice_id=voice.id, script="Hi there. [pause soon] Bye.", language="en"
        )
    assert e.value.code == "bad_pause" and "[pause soon]" in e.value.message
    with pytest.raises(Invalid, match="only has pauses"):
        generation.create_generation(s, voice_id=voice.id, script="[pause 2s]", language="en")


def test_stitch_lead_in():
    sr = 1000
    out, offsets = stitch([np.ones(100, dtype=np.float32) * 0.5], [0], sr, trim=False, lead_ms=500)
    assert len(out) == 600 and offsets == [0.5] and np.all(out[:500] == 0)
