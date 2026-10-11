"""Built-in voices: studio speakers that ship with XTTS-v2 (speakers_xtts.pth, part of the
model download and its Coqui Public Model License — non-commercial). They are not
recordings of private individuals, so they come ready to use with a fixed consent note.

Seeding (once, in the background, on first start — or on demand via "Restore"):
  1. a Voice row (source="builtin") per catalog entry,
  2. the speaker's ready-made XTTS latents as its voiceprint (no reference audio needed),
  3. an ~8 s sample clip spoken by that voice, with its exact transcript — used as the
     preview, and as the short transcribed reference F5/IndicF5 need.

Gender labels were chosen by measuring each speaker's median pitch (2026-10-11 survey:
female 197–237 Hz, male 93–116 Hz); speakers whose pitch didn't clearly match a label
were left out rather than guessed from their names.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engines import registry
from app.models import AppSetting, Job, Voice, VoiceEngineProfile, VoiceSample
from app.services import audio, storage
from app.services.errors import Invalid
from app.services.jobs import JobContext, get_runner, job_handler, on_job_failure
from app.services.quality import analyze

log = logging.getLogger("vaani.builtin")

ENGINE = "xtts"
SEEDED_FLAG = "builtin_voices_seeded"
SAMPLE_TEXT = (
    "Hello! I'm one of Vaani's built-in voices. Pick me on the Generate page, type a "
    "script, and I'll read it out for you."
)
CONSENT = (
    "Built-in studio voice that ships with the XTTS-v2 model (Coqui Public Model License, "
    "non-commercial use only). Not a recording of a private individual."
)
CATALOG: list[dict[str, Any]] = [
    # female — higher pitch first
    {"key": "Daisy Studious", "gender": "female", "pitch_hz": 237},
    {"key": "Rosemary Okafor", "gender": "female", "pitch_hz": 220},
    {"key": "Brenda Stern", "gender": "female", "pitch_hz": 217},
    {"key": "Narelle Moon", "gender": "female", "pitch_hz": 208},
    {"key": "Annmarie Nele", "gender": "female", "pitch_hz": 205},
    {"key": "Gracie Wise", "gender": "female", "pitch_hz": 197},
    # male — deeper first
    {"key": "Damien Black", "gender": "male", "pitch_hz": 93},
    {"key": "Dionisio Schuyler", "gender": "male", "pitch_hz": 94},
    {"key": "Kumar Dahl", "gender": "male", "pitch_hz": 97},
    {"key": "Aaron Dreschner", "gender": "male", "pitch_hz": 106},
    {"key": "Viktor Eka", "gender": "male", "pitch_hz": 113},
    {"key": "Royston Min", "gender": "male", "pitch_hz": 116},
]


def _describe(entry: dict[str, Any]) -> str:
    pitch = (
        "deeper"
        if entry["gender"] == "male" and entry["pitch_hz"] < 100
        else (
            "brighter" if entry["gender"] == "female" and entry["pitch_hz"] > 215 else "mid-range"
        )
    )
    return f"{pitch.capitalize()} pitch, English accent."


def missing(session: Session) -> list[dict[str, Any]]:
    have = set(session.scalars(select(Voice.builtin_key).where(Voice.source == "builtin")))
    return [e for e in CATALOG if e["key"] not in have]


def is_seeded(session: Session) -> bool:
    return session.get(AppSetting, SEEDED_FLAG) is not None


def can_seed() -> bool:
    eng = registry.get_engine(ENGINE)
    return eng.availability().ok


def start_seeding(session: Session) -> Job | None:
    """Queue a job that adds every catalog voice that isn't there. None if nothing to do."""
    if not can_seed():
        raise Invalid("Built-in voices need the XTTS-v2 engine.", code="engine_unavailable")
    todo = missing(session)
    if not todo:
        return None
    active = session.scalar(
        select(Job).where(Job.kind == "seed_builtin_voices", Job.status.in_(("queued", "running")))
    )
    if active:
        return active
    # Create the rows now, so the library shows them (as "processing") immediately.
    for e in todo:
        session.add(
            Voice(
                name=e["key"],
                language="en",
                description=_describe(e),
                consent_note=CONSENT,
                status="processing",
                source="builtin",
                builtin_key=e["key"],
                gender=e["gender"],
            )
        )
    session.commit()
    return get_runner().submit(session, "seed_builtin_voices", {})


def seed_on_startup(session: Session) -> None:
    """First start only (a flag in app_settings), so deleted built-ins stay deleted until
    the user presses Restore."""
    if is_seeded(session) or not can_seed():
        return
    start_seeding(session)
    # Only after the work is queued: if seeding couldn't start, try again next time.
    session.add(AppSetting(key=SEEDED_FLAG, value=True))
    session.commit()


@job_handler("seed_builtin_voices")
def run_seed(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.voices import ensure_profile  # noqa: F401  (keeps import cycle lazy)

    engine = registry.get_engine(ENGINE)
    with ctx.session() as s:
        pending = list(
            s.scalars(select(Voice).where(Voice.source == "builtin", Voice.status == "processing"))
        )
        n = len(pending)
        if n and not engine.is_loaded:
            ctx.progress(0.02, "loading_model", f"Loading {engine.label}…")
            engine.load()
        done = 0
        for i, voice in enumerate(pending):
            ctx.progress(
                0.05 + 0.9 * i / max(1, n),
                "voiceprint",
                f"Preparing {voice.name} ({i + 1}/{n})…",
                voice_id=voice.id,
            )
            try:
                _prepare(s, voice, engine)
                done += 1
            except Exception as exc:  # noqa: BLE001 - one bad speaker shouldn't stop the rest
                log.exception("built-in voice %s failed", voice.name)
                voice.status, voice.error = "failed", str(exc)
                s.commit()
        ctx.progress(1.0, "done", f"{done} built-in voices ready", event="voice_ready")
        return {"created": done, "failed": n - done}


def _prepare(s: Session, voice: Voice, engine) -> None:  # noqa: ANN001
    cache = storage.engine_cache_dir(voice.id, engine.name)
    profile = engine.create_builtin_voice(voice.builtin_key, cache)
    s.add(
        VoiceEngineProfile(
            voice_id=voice.id,
            engine=engine.name,
            engine_version=profile.engine_version,
            cache_dir=storage.rel(cache),
            data=profile.data,
            size_bytes=storage.dir_size(cache),
        )
    )

    # Sample clip in this voice: preview + an exactly-transcribed short reference for F5.
    res = engine.synthesize(SAMPLE_TEXT, profile, "en")
    proc = storage.voice_dir(voice.id) / "processed" / "sample.wav"
    audio.write_wav(proc, res.audio, res.sample_rate)
    dur = round(len(res.audio) / res.sample_rate, 3)
    report = analyze(res.audio, res.sample_rate)
    s.add(
        VoiceSample(
            voice_id=voice.id,
            kind="builtin",
            original_filename="Built-in sample",
            original_path=storage.rel(proc),
            processed_path=storage.rel(proc),
            size_bytes=proc.stat().st_size,
            duration_seconds=dur,
            transcript=SAMPLE_TEXT,
            transcript_source="builtin",
            transcript_segments=[{"start": 0.0, "end": dur, "text": SAMPLE_TEXT}],
            quality=report.to_dict(),
            segments=[{"path": storage.rel(proc), "start": 0.0, "end": dur, "duration": dur}],
        )
    )
    # No upload-quality rating: it judges recordings someone uploaded (e.g. "15 s minimum"),
    # which would wrongly call a studio voice with a short sample "Poor".
    voice.quality_rating, voice.quality_report = None, None
    voice.speech_seconds = report.speech_seconds
    voice.preview_path = storage.rel(proc)
    voice.status, voice.error = "ready", None
    s.commit()


@on_job_failure("seed_builtin_voices")
def _seed_failed(session: Session, job: Job) -> None:
    for v in session.scalars(
        select(Voice).where(Voice.source == "builtin", Voice.status == "processing")
    ):
        v.status, v.error = "failed", job.error
