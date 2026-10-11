import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Batch, Generation, Job
from app.services import batches, storage, voices
from app.services.errors import Invalid
from tests.test_voices_service import make_voice

ITEMS = [
    {"title": "Welcome", "script": "Hello and welcome to the show."},
    {"title": "Rules", "script": "Please keep your phones on silent. [pause 1s] Thank you."},
    {"title": "", "script": "This one has no title at all."},
]


def run_all(s, runner, batch):
    for g in batch.generations:
        job = s.scalar(select(Job).where(Job.generation_id == g.id))
        runner.run_one(job.id)
    s.expire_all()
    return batches.get_batch(s, batch.id)


def test_batch_creates_ordered_items_and_runs_them(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    b = batches.create_batch(s, voice_id=voice.id, language="en", items=ITEMS, title="Show")
    assert [g.title for g in b.generations] == ["Welcome", "Rules", "Item 3"]
    assert [g.batch_index for g in b.generations] == [0, 1, 2]
    assert batches.summary(s, b)["progress"] == 0
    b = run_all(s, runner, b)
    sm = batches.summary(s, b)
    assert sm["finished"] and sm["counts"] == {"done": 3} and sm["progress"] == 1
    assert b.engine == "fake" and all(g.engine == "fake" for g in b.generations)


def test_one_bad_item_means_nothing_is_queued(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    bad = [
        *ITEMS,
        {"title": "Broken", "script": "Hi there. [pause soon] Bye."},
        {"title": "Ghost", "script": "[Nobody]: hello there."},
    ]
    with pytest.raises(Invalid) as e:
        batches.create_batch(s, voice_id=voice.id, language="en", items=bad)
    assert e.value.code == "batch_invalid"
    assert [(d["index"], d["title"], d["code"]) for d in e.value.details] == [
        (3, "Broken", "bad_pause"),
        (4, "Ghost", "unknown_speaker"),
    ]
    assert "Broken:" in e.value.message and "1 more" in e.value.message
    assert s.scalar(select(Batch)) is None and s.scalar(select(Generation)) is None


def test_limits(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    with pytest.raises(Invalid, match="at least one"):
        batches.create_batch(s, voice_id=voice.id, language="en", items=[{"script": "  "}])
    with pytest.raises(Invalid, match="At most"):
        batches.create_batch(
            s, voice_id=voice.id, language="en", items=[{"script": "Hello there friend."}] * 51
        )


def test_cancel_stops_queued_items_only(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    b = batches.create_batch(s, voice_id=voice.id, language="en", items=ITEMS)
    first = s.scalar(select(Job).where(Job.generation_id == b.generations[0].id))
    runner.run_one(first.id)
    assert batches.cancel_batch(s, b.id) == 2
    s.expire_all()
    b = batches.get_batch(s, b.id)
    assert [g.status for g in b.generations] == ["done", "failed", "failed"]
    assert b.generations[1].error == "Cancelled"
    for g in b.generations[1:]:  # the runner skips cancelled jobs
        job = s.scalar(select(Job).where(Job.generation_id == g.id))
        runner.run_one(job.id)
    s.expire_all()
    assert batches.get_batch(s, b.id).generations[1].status == "failed"
    assert batches.summary(s, batches.get_batch(s, b.id))["finished"]


def test_zip_has_numbered_audio_subtitles_and_scripts(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    b = run_all(
        s,
        runner,
        batches.create_batch(s, voice_id=voice.id, language="en", items=ITEMS, title="My Show"),
    )
    path, name = batches.build_zip(s, b.id, "wav", "srt")
    assert name == "vaani-my-show.zip"
    names = sorted(zipfile.ZipFile(path).namelist())
    assert names == [
        "01 - Welcome.srt",
        "01 - Welcome.wav",
        "02 - Rules.srt",
        "02 - Rules.wav",
        "03 - Item 3.srt",
        "03 - Item 3.wav",
        "scripts.txt",
    ]
    scripts = zipfile.ZipFile(path).read("scripts.txt").decode()
    assert "Please keep your phones on silent." in scripts
    path.unlink()


def test_delete_batch_removes_items_and_files(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    b = run_all(s, runner, batches.create_batch(s, voice_id=voice.id, language="en", items=ITEMS))
    dirs = [storage.generation_dir(g.id) for g in b.generations]
    assert all(d.exists() for d in dirs)
    assert batches.delete_batch(s, b.id) > 0
    assert not any(d.exists() for d in dirs)
    assert s.scalar(select(Batch)) is None and s.scalar(select(Generation)) is None


def test_deleting_the_voice_deletes_its_batches(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    b = run_all(s, runner, batches.create_batch(s, voice_id=voice.id, language="en", items=ITEMS))
    report = voices.delete_voice(s, voice.id)
    assert report.generations_removed == 3 and report.leftover_paths == []
    assert s.get(Batch, b.id) is None


def test_api_flow_and_item_errors(db):
    s, runner = db
    voice, _ = make_voice(s, runner)
    with TestClient(app) as client:
        r = client.post(
            "/api/v1/batches",
            json={
                "voice_id": voice.id,
                "language": "en",
                "items": [{"title": "Bad", "script": "[pause x]"}],
            },
        )
        assert r.status_code == 422 and r.json()["details"][0]["title"] == "Bad"
        r = client.post(
            "/api/v1/batches",
            json={"voice_id": voice.id, "language": "en", "title": "Demo", "items": ITEMS},
        )
        assert r.status_code == 202
        bid = r.json()["id"]
        import time

        for _ in range(100):
            body = client.get(f"/api/v1/batches/{bid}").json()
            if body["finished"]:
                break
            time.sleep(0.1)
        assert body["finished"] and body["progress"] == 1
        assert [i["title"] for i in body["items"]] == ["Welcome", "Rules", "Item 3"]
        z = client.get(f"/api/v1/batches/{bid}/download?format=wav&subtitles=none")
        assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
        assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist())[0] == "01 - Welcome.wav"
        assert client.get("/api/v1/batches").json()[0]["id"] == bid
        hist = client.get("/api/v1/generations").json()
        assert {h["title"] for h in hist} >= {"Welcome", "Rules"}
        assert client.delete(f"/api/v1/batches/{bid}").status_code == 200
