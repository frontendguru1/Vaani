"""Voice library: create (upload/record → background processing), list, update, delete,
and per-engine conditioning (voiceprint) caching."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.engines import registry
from app.engines.base import EngineError, VoiceProfile
from app.models import Generation, Job, Voice, VoiceEngineProfile, VoiceSample
from app.services import storage
from app.services.errors import Invalid, NotFound
from app.services.jobs import JobContext, get_runner, job_handler, on_job_failure
from app.services.preprocessing import process_sample
from app.services.quality import QualityReport, summarize

log = logging.getLogger("vaani.voices")

ALLOWED_EXTENSIONS = {
    "wav",
    "mp3",
    "m4a",
    "ogg",
    "webm",
    "flac",
    "aac",
    "mp4",
    "opus",
    "aiff",
    "aif",
}
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_FILES = 20
LANGUAGES = {"en", "hi"}  # what the UI offers today; engines may support more
XTTS_REF_BUDGET = 60.0  # seconds of the cleanest speech used for conditioning


@dataclass
class Upload:
    filename: str
    file: BinaryIO
    kind: str = "upload"  # upload|recording
    transcript: str | None = None


def _get(session: Session, voice_id: str) -> Voice:
    voice = session.get(Voice, voice_id, options=[selectinload(Voice.samples)])
    if voice is None:
        raise NotFound(f"Voice {voice_id} not found", code="voice_not_found")
    return voice


def get_voice(session: Session, voice_id: str) -> Voice:
    return _get(session, voice_id)


def list_voices(session: Session) -> list[Voice]:
    return list(
        session.scalars(
            select(Voice)
            .options(selectinload(Voice.samples))
            .order_by(Voice.sort_order, Voice.created_at.desc())
        )
    )


def generation_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(Generation.voice_id, func.count()).group_by(Generation.voice_id))
    return {vid: n for vid, n in rows}


def validate_fields(name: str, language: str, consent_note: str) -> None:
    if not name.strip():
        raise Invalid("Give the voice a name.", code="name_required")
    if len(name) > 120:
        raise Invalid("Name is too long (max 120 characters).", code="name_too_long")
    if language not in LANGUAGES:
        raise Invalid(f"Language must be one of: {', '.join(sorted(LANGUAGES))}.", code="language")
    if len(consent_note.strip()) < 10:
        raise Invalid(
            "A consent note is required: whose voice is this, and do you have permission?",
            code="consent_required",
        )


def _check_upload(u: Upload) -> str:
    ext = Path(u.filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise Invalid(
            f"{u.filename}: unsupported file type .{ext or '?'} (use wav, mp3, m4a or ogg).",
            code="file_type",
        )
    return ext


def create_voice(
    session: Session,
    *,
    name: str,
    language: str,
    consent_note: str,
    description: str = "",
    uploads: list[Upload],
    denoise: bool = False,
) -> tuple[Voice, Job]:
    validate_fields(name, language, consent_note)
    if not uploads:
        raise Invalid("Add at least one audio file or recording.", code="no_files")
    if len(uploads) > MAX_FILES:
        raise Invalid(f"At most {MAX_FILES} files per voice.", code="too_many_files")
    for u in uploads:
        _check_upload(u)

    voice = Voice(
        name=name.strip(),
        language=language,
        description=description.strip(),
        consent_note=consent_note.strip(),
        status="processing",
    )
    session.add(voice)
    session.flush()
    orig_dir = storage.voice_dir(voice.id) / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)
    try:
        for i, u in enumerate(uploads):
            dst = orig_dir / f"{i:02d}_{storage.safe_filename(u.filename)}"
            size = copy_limited(u.file, dst, MAX_FILE_BYTES, u.filename)
            if size == 0:
                raise Invalid(f"{u.filename} is empty.", code="empty_file")
            session.add(
                VoiceSample(
                    voice_id=voice.id,
                    kind=u.kind,
                    original_filename=u.filename[:255],
                    original_path=storage.rel(dst),
                    size_bytes=size,
                    transcript=(u.transcript or "").strip() or None,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        storage.remove_tree(storage.voice_dir(voice.id))
        raise

    job = get_runner().submit(
        session, "create_voice", {"voice_id": voice.id, "denoise": denoise}, voice_id=voice.id
    )
    session.refresh(voice)
    return voice, job


def copy_limited(src: BinaryIO, dst: Path, limit: int, name: str) -> int:
    """Copy in chunks and stop as soon as `limit` bytes is exceeded (never fill the disk)."""
    size = 0
    with dst.open("wb") as out:
        while chunk := src.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                dst.unlink(missing_ok=True)
                raise Invalid(
                    f"{name} is larger than {limit // (1024 * 1024)} MB.", code="file_too_large"
                )
            out.write(chunk)
    return size


def update_voice(session: Session, voice_id: str, **fields: Any) -> Voice:
    voice = _get(session, voice_id)
    name = fields.get("name", voice.name)
    language = fields.get("language", voice.language)
    consent = fields.get("consent_note", voice.consent_note)
    validate_fields(name or "", language, consent or "")
    voice.name, voice.language, voice.consent_note = name.strip(), language, consent.strip()
    if fields.get("description") is not None:
        voice.description = fields["description"].strip()
    if fields.get("sort_order") is not None:
        voice.sort_order = int(fields["sort_order"])
    session.commit()
    return voice


@dataclass
class DeleteReport:
    voice_id: str
    files_removed: int
    generations_removed: int
    leftover_paths: list[str]


def delete_voice(session: Session, voice_id: str) -> DeleteReport:
    """Hard delete: rows (cascade) + every file for the voice and its generations."""
    voice = _get(session, voice_id)
    runner = get_runner()
    active_ids = set(
        session.scalars(
            select(Job.id).where(Job.voice_id == voice_id, Job.status.in_(("queued", "running")))
        )
    )
    # Only a job that is executing right now can recreate files; queued ones are deleted
    # below, and the runner skips job ids whose rows are gone.
    if runner.current_job in active_ids:
        raise Invalid(
            "This voice is being processed right now — try again in a moment.", code="busy"
        )
    gen_ids = list(session.scalars(select(Generation.id).where(Generation.voice_id == voice_id)))
    # Drop cached latents held in engine memory.
    for eng in registry.all_engines():
        cache = getattr(eng, "_latents", None)
        if isinstance(cache, dict):
            for key in [k for k in cache if str(storage.voice_dir(voice_id)) in str(k)]:
                cache.pop(key, None)

    session.delete(voice)  # cascades samples, profiles, generations, chunks
    # Jobs reference the voice loosely; remove them too so nothing names it.
    for job in session.scalars(select(Job).where(Job.voice_id == voice_id)):
        session.delete(job)
    for gid in gen_ids:
        for job in session.scalars(select(Job).where(Job.generation_id == gid)):
            session.delete(job)
    session.commit()

    removed = storage.remove_tree(storage.voice_dir(voice_id))
    for gid in gen_ids:
        removed += storage.remove_tree(storage.generation_dir(gid))
    leftovers = [
        str(p)
        for p in [storage.voice_dir(voice_id), *[storage.generation_dir(g) for g in gen_ids]]
        if p.exists()
    ]
    log.info("deleted voice %s: %d files, %d generations", voice_id, removed, len(gen_ids))
    return DeleteReport(voice_id, removed, len(gen_ids), leftovers)


# ---------------------------------------------------------------------------
# Voiceprints (per-engine conditioning), cached on disk + in the DB
# ---------------------------------------------------------------------------


def _reference_segments(voice: Voice, budget: float) -> list[Path]:
    """Cleanest segments first (by sample quality score, then length), up to `budget` s."""
    scored: list[tuple[int, float, Path]] = []
    for s in voice.samples:
        score = (s.quality or {}).get("score", 50)
        if (s.quality or {}).get("rating") == "poor" and len(voice.samples) > 1:
            continue
        for seg in s.segments or []:
            scored.append((score, seg["duration"], storage.resolve(seg["path"])))
    if not scored:  # every clip rated poor: use them anyway rather than fail outright
        scored = [
            ((s.quality or {}).get("score", 0), seg["duration"], storage.resolve(seg["path"]))
            for s in voice.samples
            for seg in s.segments or []
        ]
    scored.sort(key=lambda t: (-t[0], -t[1]))
    picked, total = [], 0.0
    for _score, dur, path in scored:
        if total >= budget:
            break
        picked.append(path)
        total += dur
    return picked


def transcript_reference_or_none(session: Session, voice: Voice, max_seconds: float):
    voice = _get(session, voice.id)
    try:
        return _transcript_reference(voice, max_seconds)
    except EngineError:
        return None


def _transcript_reference(voice: Voice, max_seconds: float) -> tuple[Path, str]:
    for s in sorted(voice.samples, key=lambda x: -(x.quality or {}).get("score", 0)):
        if s.transcript and s.processed_path and s.duration_seconds <= max_seconds + 0.5:
            return storage.resolve(s.processed_path), s.transcript
    raise EngineError(
        f"This engine needs a clip of at most {max_seconds:.0f}s with its exact transcript. "
        "Add a short recording and type what was said."
    )


def ensure_profile(
    session: Session,
    voice: Voice,
    engine_name: str,
    ctx: JobContext | None = None,
    progress_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[VoiceProfile, bool]:
    """Return the cached voiceprint for (voice, engine), computing it if missing or stale.
    The bool says whether it was freshly computed."""
    engine = registry.get_engine(engine_name)
    lo, hi = progress_range
    row = session.scalar(
        select(VoiceEngineProfile).where(
            VoiceEngineProfile.voice_id == voice.id, VoiceEngineProfile.engine == engine_name
        )
    )
    # Worker engines report "unknown" until loaded; trust the cache rather than rebuild.
    if row is not None and engine.version in ("unknown", row.engine_version):
        profile = VoiceProfile(
            engine_name, row.engine_version, storage.resolve(row.cache_dir), dict(row.data)
        )
        files = [k for k, v in profile.data.items() if isinstance(v, str) and k != "ref_text"]
        if all(profile.path(k).exists() for k in files):
            return profile, False

    if not engine.is_loaded and ctx:
        ctx.progress(lo, "loading_model", f"Loading {engine.label} (first time takes a while)…")
    engine.load()
    if ctx:
        ctx.progress(lo + (hi - lo) * 0.3, "voiceprint", "Extracting voiceprint…")
    cache = storage.engine_cache_dir(voice.id, engine_name)
    storage.remove_tree(cache)
    if engine.needs_transcript:
        ref, text = _transcript_reference(voice, getattr(engine, "max_ref_seconds", 12.0))
        profile = engine.create_voice([ref], cache, [text])
    else:
        refs = _reference_segments(voice, XTTS_REF_BUDGET)
        if not refs:
            raise EngineError("No usable speech found in this voice's samples.")
        profile = engine.create_voice(refs, cache)

    if row is None:
        row = VoiceEngineProfile(voice_id=voice.id, engine=engine_name)
        session.add(row)
    row.engine_version = profile.engine_version
    row.cache_dir = storage.rel(cache)
    row.data = profile.data
    row.size_bytes = storage.dir_size(cache)
    session.commit()
    return profile, True


# ---------------------------------------------------------------------------
# Background job: process a new voice
# ---------------------------------------------------------------------------


@job_handler("create_voice")
def run_create_voice(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    voice_id, denoise = payload["voice_id"], bool(payload.get("denoise"))
    with ctx.session() as s:
        voice = _get(s, voice_id)
        samples = list(voice.samples)
        n = len(samples)
        reports: list[QualityReport] = []
        proc_dir = storage.voice_dir(voice_id) / "processed"

        # 1. cleaning + per-sample quality (0 → 0.55)
        for i, sample in enumerate(samples):
            ctx.progress(
                0.55 * i / n,
                "cleaning",
                f"Cleaning {sample.original_filename} ({i + 1}/{n})…",
                event="sample_started",
                sample_id=sample.id,
                index=i,
            )
            result = process_sample(
                storage.resolve(sample.original_path), proc_dir, f"{i:02d}", denoise=denoise
            )
            sample.processed_path = storage.rel(result.processed)
            sample.duration_seconds = result.duration
            sample.quality = result.quality.to_dict()
            sample.segments = [
                {
                    "path": storage.rel(seg.path),
                    "start": seg.start,
                    "end": seg.end,
                    "duration": seg.duration,
                }
                for seg in result.segments
            ]
            s.commit()
            reports.append(result.quality)
            ctx.progress(
                0.55 * (i + 1) / n,
                "cleaning",
                f"Cleaned {sample.original_filename}",
                event="sample_done",
                sample_id=sample.id,
                index=i,
                quality=sample.quality,
                duration=result.duration,
            )

        # 2. voice-level quality (0.55 → 0.6)
        ctx.progress(0.56, "quality", "Checking quality…")
        summary = summarize(reports)
        voice.quality_rating = summary["rating"]
        voice.quality_report = summary
        voice.speech_seconds = summary["speech_seconds"]
        preview = max(
            (
                seg
                for smp in samples
                if (smp.quality or {}).get("rating") != "poor"
                for seg in smp.segments or []
            ),
            key=lambda seg: min(seg["duration"], 12.0),
            default=None,
        ) or next((seg for smp in samples for seg in smp.segments or []), None)
        voice.preview_path = preview["path"] if preview else None
        s.commit()
        ctx.progress(
            0.6, "quality", f"Quality: {summary['rating']}", event="quality", summary=summary
        )
        if not any(smp.segments for smp in samples):
            raise EngineError("No speech was found in these recordings.")

        # 3. voiceprint for the default engine (0.6 → 0.95). If the engine isn't
        #    available the voice is still usable; the voiceprint is built on first generation.
        engine_name = get_settings().default_engine
        voiceprint = "skipped"
        engine = registry.get_engine(engine_name)
        if engine.availability().ok:
            _profile, fresh = ensure_profile(s, voice, engine_name, ctx, (0.6, 0.95))
            voiceprint = "computed" if fresh else "cached"
        ctx.progress(0.97, "saving", "Saving…")
        voice.status, voice.error = "ready", None
        s.commit()
        ctx.progress(1.0, "saving", "Voice ready", event="voice_ready")
        return {
            "voice_id": voice_id,
            "rating": summary["rating"],
            "voiceprint": voiceprint,
            "engine": engine_name,
        }


@on_job_failure("create_voice")
def _voice_failed(session: Session, job: Job) -> None:
    voice = session.get(Voice, job.voice_id) if job.voice_id else None
    if voice is not None:
        voice.status, voice.error = "failed", job.error
