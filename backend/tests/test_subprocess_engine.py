"""The JSON-lines worker bridge, exercised with a fake worker in the main venv."""

import sys
import textwrap
from pathlib import Path

import pytest

from app.engines.base import EngineError
from app.engines.subprocess_engine import SubprocessEngine
from app.services import audio
from tests.helpers import speech_wav_bytes

FAKE_WORKER = textwrap.dedent("""
    import numpy as np, soundfile as sf
    print("library noise on stdout must not break the protocol")
    from _protocol import serve

    def load(req):
        print("more noise")
        return {"device": "fake-gpu", "version": "fake-worker 1"}

    def synthesize(req):
        if "crash" in req["text"]:
            raise RuntimeError("worker exploded")
        if "die" in req["text"]:
            import os; os._exit(3)
        n = 24000 // 2
        sf.write(req["out"], np.full(n, 0.1, dtype=np.float32), 24000)
        return {"sample_rate": 24000}

    serve({"load": load, "synthesize": synthesize})
""")


@pytest.fixture
def engine(tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER)

    class FakeWorkerEngine(SubprocessEngine):
        name, label, venv, worker_script = "fw", "FakeWorker", "unused", "fake_worker.py"
        supported_languages = frozenset({"en"})
        sample_rate = 24_000

        @property
        def python(self) -> Path:
            return Path(sys.executable)

        @property
        def worker_path(self) -> Path:
            return script

    eng = FakeWorkerEngine()
    yield eng
    eng.unload()


def test_load_synthesize_and_unload(engine, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(speech_wav_bytes(5, lead=0.2))
    profile = engine.create_voice([ref], tmp_path / "cache", ["exact words"])
    assert profile.data["ref_text"] == "exact words"
    assert audio.duration_seconds(profile.path("ref_audio")) > 4

    res = engine.synthesize("hello", profile, "en")
    assert engine.is_loaded and engine.device == "fake-gpu"
    assert engine.version == "fake-worker 1"
    assert res.sample_rate == 24000 and len(res.audio) == 12000
    engine.unload()
    assert not engine.is_loaded


def test_worker_errors_are_reported_and_worker_survives(engine, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(speech_wav_bytes(3, lead=0.1))
    profile = engine.create_voice([ref], tmp_path / "c", ["words"])
    with pytest.raises(EngineError, match="worker exploded"):
        engine.synthesize("please crash", profile, "en")
    assert len(engine.synthesize("fine", profile, "en").audio) > 0


def test_worker_death_is_detected(engine, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(speech_wav_bytes(3, lead=0.1))
    profile = engine.create_voice([ref], tmp_path / "c", ["words"])
    with pytest.raises(EngineError, match="exited"):
        engine.synthesize("now die", profile, "en")


def test_transcript_and_length_are_required(engine, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(speech_wav_bytes(20, lead=0.1))
    with pytest.raises(EngineError, match="transcript"):
        engine.create_voice([ref], tmp_path / "c", None)
    with pytest.raises(EngineError, match="at most"):
        engine.create_voice([ref], tmp_path / "c", ["words"])


def test_missing_venv_is_unavailable():
    class Missing(SubprocessEngine):
        name, label, venv, worker_script = "m", "Missing", "does-not-exist", "x.py"
        supported_languages = frozenset({"en"})
        sample_rate = 24_000

    avail = Missing().availability()
    assert not avail.ok and "venv missing" in avail.reason
