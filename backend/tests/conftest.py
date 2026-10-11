import os
import shutil
from pathlib import Path

import pytest

# Point the app at a throwaway data dir BEFORE app modules are imported,
# so tests never touch the real data/ (which holds real people's voices).
_TMP = Path(os.environ.setdefault("VAANI_TEST_DATA", "/tmp/vaani-test-data"))
os.environ["VAANI_DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["VAANI_DEFAULT_ENGINE"] = "fake"
os.environ["VAANI_TRANSCRIBE_ON_CREATE"] = "false"
os.environ["VAANI_SEED_BUILTIN_VOICES"] = (
    "false"  # tests seed explicitly with a fake engine  # tests use a fake transcriber explicitly
)
# Starlette's TestClient sends Host: testserver.
os.environ["VAANI_ALLOWED_HOSTS"] = '["localhost", "127.0.0.1", "testserver"]'

import tests.fakes  # noqa: E402,F401  (registers the fake engine)


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
    _TMP.mkdir(parents=True)
    from app.cli import upgrade_to_head

    upgrade_to_head()
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def db():
    """A session plus a synchronous job runner (call runner.run_one(job_id) to execute)."""
    from app.db import SessionLocal
    from app.models import Base
    from app.services.jobs import JobRunner, set_runner

    runner = JobRunner(SessionLocal)
    set_runner(runner)
    with SessionLocal() as s:
        yield s, runner
    with SessionLocal() as s:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "alembic_version":
                s.execute(table.delete())
        s.commit()
    set_runner(None)
    for sub in ("voices", "generations"):
        shutil.rmtree(_TMP / sub, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_speaker_model(monkeypatch):
    """Never load the real SpeechBrain model in tests (89 MB, ~20 s); use a pitch-based fake.
    Tests that need specific behaviour patch similarity themselves."""
    import numpy as np
    import soundfile as sf

    from app.services import similarity

    def fake_array(audio, sr):
        spec = np.abs(np.fft.rfft(audio[: sr * 2] if len(audio) > sr else audio))
        f0 = np.argmax(spec[1:]) * sr / (2 * max(1, len(spec) - 1)) + 1
        v = np.array([np.cos(f0 / 60), np.sin(f0 / 60), 0.2])
        return v / np.linalg.norm(v)

    def fake_file(path):
        y, sr = sf.read(str(path), dtype="float32")
        return fake_array(y if y.ndim == 1 else y.mean(axis=1), sr)

    monkeypatch.setattr(similarity, "embed_array", fake_array)
    monkeypatch.setattr(similarity, "embed_file", fake_file)
