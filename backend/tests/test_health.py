from fastapi.testclient import TestClient

from app.main import app
from app.services import system


def test_health_reports_db_ffmpeg_and_device():
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "vaani"
    assert body["database"] is True
    assert set(body["ffmpeg"]) == {"available", "version"}
    assert body["device"]["preferred"] in {"mps", "cpu"}


def test_health_degrades_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda _name: None)
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()
    assert body["ffmpeg"]["available"] is False
    assert body["status"] == "degraded"


def test_cpu_preference_is_respected():
    assert system.device_info("cpu").preferred == "cpu"


def test_health_reports_a_schema_that_is_behind(monkeypatch):
    import app.cli as cli

    monkeypatch.setattr(cli, "schema_is_current", lambda url=None: (False, "old", "new"))
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()
    assert body["schema_current"] is False and body["status"] == "degraded"
