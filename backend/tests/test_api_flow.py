"""End-to-end over HTTP with the real background thread and SSE (fake engine)."""

import json
import time

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import speech_wav_bytes

CONSENT = "My own voice, recorded by me for personal use."


def sse_events(client, job_id, timeout=30):
    events = []
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events", timeout=timeout) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events.append(ev)
                if ev["status"] in ("succeeded", "failed"):
                    break
    return events


def wait_job(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError("job timed out")


def test_full_voice_and_generation_flow(db):
    with TestClient(app) as client:
        engines = client.get("/api/v1/engines").json()
        assert {"xtts", "f5_mlx", "indicf5", "fake"} <= {e["name"] for e in engines}
        assert next(e for e in engines if e["name"] == "fake")["default"] is True

        r = client.post(
            "/api/v1/voices",
            data={
                "name": "Rahul",
                "language": "en",
                "consent_note": CONSENT,
                "kinds": ["upload", "recording"],
            },
            files=[
                ("files", ("a.wav", speech_wav_bytes(8), "audio/wav")),
                ("files", ("mic.wav", speech_wav_bytes(9), "audio/wav")),
            ],
        )
        assert r.status_code == 202, r.text
        voice_id, job_id = r.json()["voice"]["id"], r.json()["job_id"]

        events = sse_events(client, job_id)
        types = [e["type"] for e in events]
        assert types[0] == "snapshot" and types[-1] == "succeeded"
        assert "quality" in types and "voice_ready" in types

        voice = client.get(f"/api/v1/voices/{voice_id}").json()
        assert voice["status"] == "ready" and voice["engines_ready"] == ["fake"]
        assert [s["kind"] for s in voice["samples"]] == ["upload", "recording"]
        assert client.get(f"/api/v1/voices/{voice_id}/preview").status_code == 200
        sid = voice["samples"][0]["id"]
        assert client.get(f"/api/v1/voices/{voice_id}/samples/{sid}/audio").status_code == 200

        r = client.post(
            "/api/v1/generations",
            json={
                "voice_id": voice_id,
                "language": "hi",
                "script": "आज मौसम बहुत सुहाना है। चलो बाहर टहलने चलते हैं।",
            },
        )
        assert r.status_code == 202, r.text
        gen_id = r.json()["generation"]["id"]
        job = wait_job(client, r.json()["job_id"])
        assert job["status"] == "succeeded", job["error"]

        wav = client.get(f"/api/v1/generations/{gen_id}/audio")
        assert wav.status_code == 200 and wav.content[:4] == b"RIFF"
        mp3 = client.get(f"/api/v1/generations/{gen_id}/audio?format=mp3&download=true")
        assert mp3.headers["content-type"] == "audio/mpeg"
        assert "attachment" in mp3.headers["content-disposition"]

        history = client.get("/api/v1/generations").json()
        assert history[0]["id"] == gen_id and history[0]["voice_name"] == "Rahul"
        assert client.get("/api/v1/voices").json()[0]["generation_count"] == 1

        r = client.patch(f"/api/v1/voices/{voice_id}", json={"name": "Rahul K"})
        assert r.json()["name"] == "Rahul K"

        d = client.delete(f"/api/v1/voices/{voice_id}").json()
        assert d["leftover_paths"] == [] and d["generations_removed"] == 1
        assert client.get(f"/api/v1/voices/{voice_id}").status_code == 404
        assert client.get(f"/api/v1/generations/{gen_id}").status_code == 404


def test_errors_are_json_with_codes(db):
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/voices",
            data={"name": "x", "consent_note": ""},
            files=[("files", ("a.wav", speech_wav_bytes(2), "audio/wav"))],
        )
        assert r.status_code == 422 and r.json()["code"] == "consent_required"
        r = client.post(
            "/api/v1/generations", json={"voice_id": "missing", "language": "en", "script": "hi"}
        )
        assert r.status_code == 404 and r.json()["code"] == "voice_not_found"
        assert client.get("/api/v1/jobs/nope").status_code == 404


def test_quality_check_endpoint_stores_nothing(db):
    from app.services import storage

    with TestClient(app) as client:
        r = client.post(
            "/api/v1/voices/quality-check",
            files={"file": ("clip.wav", speech_wav_bytes(6), "audio/wav")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["report"]["rating"] in {"good", "okay", "poor"}
        assert 6 < body["duration"] < 8
    assert not (storage.data_dir() / "voices").exists() or not any(
        (storage.data_dir() / "voices").iterdir()
    )


def test_timestamps_are_utc_aware(db):
    """Regression: SQLite returned naive datetimes, so the UI showed '5 h ago' in IST."""
    from datetime import UTC, datetime

    from app.models import AppSetting

    s, _ = db
    s.add(AppSetting(key="tz-test", value=1))
    s.commit()
    s.expire_all()
    row = s.get(AppSetting, "tz-test")
    assert row.created_at.tzinfo is not None
    assert abs((datetime.now(UTC) - row.created_at).total_seconds()) < 60
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/voices",
            data={"name": "T", "consent_note": CONSENT},
            files=[("files", ("a.wav", speech_wav_bytes(6), "audio/wav"))],
        )
        stamp = r.json()["voice"]["created_at"]
    assert stamp.endswith("Z") or stamp.endswith("+00:00"), stamp
