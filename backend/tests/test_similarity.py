import io

import numpy as np
import pytest

from app.models import Generation
from app.services import generation, similarity, storage, voices
from tests.helpers import speech_wav_bytes
from tests.test_voices_service import CONSENT


def fake_embed_array(audio, sr):
    """Pitch → direction: same pitch ≈ same 'speaker', far pitch ≈ different speaker."""
    spec = np.abs(np.fft.rfft(audio[: sr * 2] if len(audio) > sr else audio))
    f0 = np.argmax(spec[1:]) * sr / (2 * (len(spec) - 1)) + 1
    v = np.array([np.cos(f0 / 60), np.sin(f0 / 60), 0.2])
    return v / np.linalg.norm(v)


@pytest.fixture
def fake_encoder(monkeypatch):
    import soundfile as sf

    def embed_file(path):
        y, sr = sf.read(str(path), dtype="float32")
        return fake_embed_array(y if y.ndim == 1 else y.mean(axis=1), sr)

    monkeypatch.setattr(similarity, "embed_file", embed_file)
    monkeypatch.setattr(similarity, "embed_array", fake_embed_array)


def test_robust_centroid_flags_the_odd_one_out():
    a = np.array([1.0, 0, 0])
    b = np.array([0.98, 0.2, 0])
    c = np.array([0, 1.0, 0])
    centroid, matches = similarity.robust_centroid([a, b, c])
    assert matches[0] > 0.9 and matches[1] > 0.9 and matches[2] < similarity.OUTLIER_BELOW


def test_labels():
    assert similarity.label(0.84) == "very close"
    assert similarity.label(0.65) == "close"
    assert similarity.label(0.5) == "somewhat similar"
    assert similarity.label(0.2) == "different"
    assert similarity.label(None) is None


def make(s, runner, clips):
    uploads = [voices.Upload(n, io.BytesIO(b)) for n, b in clips]
    v, job = voices.create_voice(s, name="V", language="en", consent_note=CONSENT, uploads=uploads)
    runner.run_one(job.id)
    s.expire_all()
    return voices.get_voice(s, v.id)


def test_clip_of_a_different_speaker_is_left_out_of_the_voiceprint(db, fake_encoder, monkeypatch):
    s, runner = db
    v = make(
        s,
        runner,
        [
            ("a.wav", speech_wav_bytes(8, f0=140)),
            ("b.wav", speech_wav_bytes(8, f0=145)),
            ("intruder.wav", speech_wav_bytes(8, f0=320)),
        ],
    )
    voices.voice_embedding(s, v)
    s.expire_all()
    v = voices.get_voice(s, v.id)
    matches = {smp.original_filename: smp.segments[0]["match"] for smp in v.samples}
    assert (
        matches["intruder.wav"] < similarity.OUTLIER_BELOW < min(matches["a.wav"], matches["b.wav"])
    )
    picked = {p.parent.name + "/" + p.name for p in voices._reference_segments(v, 60)}
    intruder = next(smp for smp in v.samples if smp.original_filename == "intruder.wav")
    assert not any(
        seg["path"].endswith(p.split("/")[-1])
        for seg in intruder.segments
        for p in picked
        if storage.resolve(seg["path"]).name == p.split("/")[-1]
    )
    assert len(picked) == 2


def test_embedding_is_cached_on_disk(db, fake_encoder, monkeypatch):
    s, runner = db
    v = make(s, runner, [("a.wav", speech_wav_bytes(8))])
    e1 = voices.voice_embedding(s, v)
    calls = []
    monkeypatch.setattr(similarity, "embed_file", lambda p: calls.append(p))
    e2 = voices.voice_embedding(s, voices.get_voice(s, v.id))
    assert np.allclose(e1, e2) and calls == []
    assert storage.resolve(voices.get_voice(s, v.id).embedding_path).is_file()


def test_generation_gets_a_similarity_score(db, fake_encoder):
    s, runner = db
    v = make(s, runner, [("a.wav", speech_wav_bytes(8))])
    gen, job = generation.create_generation(s, voice_id=v.id, script="Hello there.", language="en")
    runner.run_one(job.id)
    s.expire_all()
    g = s.get(Generation, gen.id)
    assert g.status == "done" and g.similarity is not None and -1 <= g.similarity <= 1


def test_similarity_failure_never_fails_a_generation(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("encoder missing")

    monkeypatch.setattr(similarity, "embed_file", boom)
    monkeypatch.setattr(similarity, "embed_array", boom)
    s, runner = db
    v = make(s, runner, [("a.wav", speech_wav_bytes(8))])
    gen, job = generation.create_generation(s, voice_id=v.id, script="Hello there.", language="en")
    runner.run_one(job.id)
    s.expire_all()
    g = s.get(Generation, gen.id)
    assert g.status == "done" and g.similarity is None


def test_recommendation_prefers_f5_for_english_with_a_transcribed_clip(db, monkeypatch):
    from app.engines import registry
    from app.engines.base import Availability
    from app.services.generation import recommend_engine

    s, runner = db
    v = make(s, runner, [("a.wav", speech_wav_bytes(8))])
    for name in ("f5_mlx", "indicf5", "xtts"):
        monkeypatch.setattr(
            type(registry.get_engine(name)), "availability", lambda self: Availability(True)
        )
    assert recommend_engine(s, v, "en")["engine"] == "xtts"  # no transcript yet
    assert recommend_engine(s, v, "en")["alternatives"][0]["engine"] == "f5_mlx"
    smp = v.samples[0]
    smp.transcript, smp.transcript_source = "Exact words.", "user"
    s.commit()
    assert recommend_engine(s, voices.get_voice(s, v.id), "en")["engine"] == "f5_mlx"
    hi = recommend_engine(s, v, "hi")
    assert hi["engine"] == "xtts" and hi["alternatives"][0]["engine"] == "indicf5"
    assert "Needs a Hindi recording" in hi["alternatives"][0]["note"]  # English-made voice
    v.language = "hi"
    assert "10× slower" in recommend_engine(s, v, "hi")["alternatives"][0]["note"]
    v.language = "en"
    v.source = "builtin"
    assert recommend_engine(s, v, "en")["engine"] == "xtts"


def test_embedding_uses_real_locking_without_deadlock(monkeypatch):
    """Regression: embed_array held a lock and then called the loader, which took the same
    lock again — the first real voice creation hung forever. Exercise the real code path
    with a stand-in model (the autouse fixture's fake is bypassed here)."""
    import importlib
    import threading

    import torch

    real = importlib.reload(similarity)  # undo the autouse fake for this module object

    class Enc:
        def encode_batch(self, x):
            return torch.ones(1, 1, 4)

    monkeypatch.setattr(real, "_encoder", Enc())
    out = {}
    t = threading.Thread(
        target=lambda: out.setdefault("e", real.embed_array(np.zeros(16000), 16000))
    )
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "embed_array deadlocked"
    assert np.allclose(np.linalg.norm(out["e"]), 1.0)


def test_voice_creation_drops_false_multi_speaker_warnings(db):
    """With all clips matching, the pitch-based 'multiple speakers' warning is removed;
    a clip of someone else gets 'different_speaker' instead."""
    s, runner = db
    v = make(
        s,
        runner,
        [
            ("a.wav", speech_wav_bytes(8, f0=140)),
            ("b.wav", speech_wav_bytes(8, f0=142)),
            ("intruder.wav", speech_wav_bytes(8, f0=320)),
        ],
    )
    codes = {smp.original_filename: [i["code"] for i in smp.quality["issues"]] for smp in v.samples}
    assert "multiple_speakers" not in sum(codes.values(), [])
    assert "different_speaker" in codes["intruder.wav"]
    assert "different_speaker" not in codes["a.wav"]
