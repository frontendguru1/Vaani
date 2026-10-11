"""Local-only hardening: DNS rebinding, cross-site form posts, oversized uploads,
non-audio containers and hung workers."""

import io
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engines.base import EngineError
from app.engines.subprocess_engine import SubprocessEngine
from app.main import app
from app.services import audio, voices
from app.services.errors import Invalid
from tests.helpers import speech_wav_bytes

CONSENT = "My own voice, recorded by me for personal use."


def form_post(client, headers=None):
    return client.post(
        "/api/v1/voices",
        headers=headers or {},
        data={"name": "X", "consent_note": CONSENT},
        files=[("files", ("a.wav", speech_wav_bytes(2), "audio/wav"))],
    )


def test_dns_rebinding_host_is_refused(db):
    with TestClient(app) as client:
        r = client.get("/api/v1/voices", headers={"Host": "evil.example:8000"})
        assert r.status_code == 400
        assert client.get("/api/v1/voices", headers={"Host": "127.0.0.1:8000"}).status_code == 200
        assert client.get("/api/v1/voices", headers={"Host": "localhost:8000"}).status_code == 200


def test_cross_site_form_post_is_refused(db):
    with TestClient(app) as client:
        r = form_post(client, {"Origin": "https://evil.example"})
        assert r.status_code == 403 and r.json()["code"] == "cross_site"
        r = form_post(client, {"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403
        assert client.delete("/api/v1/voices/x", headers={"Origin": "null"}).status_code == 403


def test_same_site_and_non_browser_requests_still_work(db):
    with TestClient(app) as client:
        assert form_post(client, {"Origin": "http://localhost:5173"}).status_code == 202
        assert form_post(client).status_code == 202  # curl / scripts send no Origin
        # Reads are unaffected by Origin (no state change, and CORS still blocks reading).
        assert (
            client.get("/api/v1/voices", headers={"Origin": "https://evil.example"}).status_code
            == 200
        )


def test_oversized_request_is_refused_before_reading(db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/voices",
            data={"name": "X", "consent_note": CONSENT},
            files=[("files", ("a.wav", b"\0" * (2 * 1024 * 1024), "audio/wav"))],
        )
        assert r.status_code == 413 and r.json()["code"] == "too_large"


def test_copy_limited_stops_at_the_limit(tmp_path):
    dst = tmp_path / "x.bin"
    with pytest.raises(Invalid):
        voices.copy_limited(io.BytesIO(b"a" * 3000), dst, 1000, "x.bin")
    assert not dst.exists()
    assert voices.copy_limited(io.BytesIO(b"a" * 500), dst, 1000, "x.bin") == 500


def test_playlists_and_non_audio_are_rejected(tmp_path):
    playlist = tmp_path / "evil.mp3"
    playlist.write_text("#EXTM3U\n#EXTINF:1,\nfile:///etc/passwd\n")
    with pytest.raises(audio.AudioError, match="isn't an audio file"):
        audio.convert_to_wav(playlist, tmp_path / "out.wav", 24000)
    concat = tmp_path / "c.wav"
    concat.write_text("ffconcat version 1.0\nfile '/etc/passwd'\n")
    with pytest.raises(audio.AudioError):
        audio.convert_to_wav(concat, tmp_path / "out2.wav", 24000)
    ok = tmp_path / "ok.wav"
    ok.write_bytes(speech_wav_bytes(1))
    assert audio.check_format(ok).startswith("wav")


def test_hung_worker_times_out_and_is_killed(tmp_path):
    script = tmp_path / "hang.py"
    script.write_text(
        textwrap.dedent("""
        import time
        from _protocol import serve
        def load(req): return {"device": "x", "version": "hang"}
        def synthesize(req):
            time.sleep(60)
            return {}
        serve({"load": load, "synthesize": synthesize})
    """)
    )

    class Hang(SubprocessEngine):
        name, label, venv, worker_script = "hang", "Hang", "unused", "hang.py"
        supported_languages = frozenset({"en"})
        sample_rate = 24_000
        call_timeout = 1.0

        @property
        def python(self) -> Path:
            return Path(sys.executable)

        @property
        def worker_path(self) -> Path:
            return script

    eng = Hang()
    ref = tmp_path / "r.wav"
    ref.write_bytes(speech_wav_bytes(2, lead=0.1))
    profile = eng.create_voice([ref], tmp_path / "c", ["words"])
    with pytest.raises(EngineError, match="didn't respond"):
        eng.synthesize("hi", profile, "en")
    assert not eng.is_loaded and eng._logf is None
    eng.ready_marker.unlink(missing_ok=True)
