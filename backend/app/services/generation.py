"""Generation: script → chunks → per-chunk synthesis (background job, real progress) →
stitched WAV (+ MP3 on demand). History, regenerate, delete."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.engines import registry
from app.models import Generation, GenerationChunk, Job, Voice
from app.services import audio, dialogue, pronunciation, storage
from app.services.chunking import Chunk, PauseMarkerError, chunk_script
from app.services.errors import Invalid, NotFound
from app.services.jobs import JobContext, get_runner, job_handler, on_job_failure
from app.services.stitching import stitch
from app.services.voices import ensure_profile

log = logging.getLogger("vaani.generation")

MAX_SCRIPT_CHARS = 20_000
ALLOWED_SETTINGS = {"speed": (0.5, 2.0), "temperature": (0.1, 1.0)}


def _clean_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (settings or {}).items():
        if key in ALLOWED_SETTINGS and value is not None:
            lo, hi = ALLOWED_SETTINGS[key]
            out[key] = min(hi, max(lo, float(value)))
        elif (
            key in ("sentence_pause_ms", "paragraph_pause_ms", "turn_pause_ms")
            and value is not None
        ):
            out[key] = int(min(5000, max(0, int(value))))
    return out


def _check_voice(session: Session, voice: Voice, eng) -> None:  # noqa: ANN001
    if not (voice.consent_note or "").strip():
        raise Invalid(
            f"{voice.name} has no consent note, so it can't be used for generation.",
            code="consent_required",
        )
    if voice.status != "ready":
        raise Invalid(
            f"{voice.name} is {voice.status}; wait until it's ready.", code="voice_not_ready"
        )
    if eng.needs_transcript:
        # Fail now with a clear message instead of after the job starts.
        from app.services.voices import transcript_reference_or_none

        limit = getattr(eng, "max_ref_seconds", 12.0)
        if transcript_reference_or_none(session, voice, limit) is None:
            raise Invalid(
                f"{eng.label} needs one clip of {limit:.0f} seconds or less with its exact "
                f"transcript, and {voice.name} doesn't have one yet. Use XTTS-v2, or "
                "transcribe the voice's clips (Voices → Clips).",
                code="needs_transcript",
            )


def _plan(
    script: str,
    turns: list[dialogue.Turn],
    *,
    max_chars: int,
    sentence_ms: int,
    paragraph_ms: int,
    turn_ms: int,
) -> tuple[list[tuple[Chunk, str]], int]:
    """Chunk every turn, keeping spans in script coordinates. Returns ([(chunk, voice_id)],
    lead_ms). A pause marker at the start of a turn replaces the usual turn pause."""
    out: list[tuple[Chunk, str]] = []
    lead_ms = 0
    for turn in turns:
        try:
            plan = chunk_script(
                script[turn.start : turn.end],
                max_chars=max_chars,
                sentence_pause_ms=sentence_ms,
                paragraph_pause_ms=paragraph_ms,
            )
        except PauseMarkerError as exc:
            raise Invalid(
                f"Couldn’t read the pause {exc}. Write it like [pause 1s], [pause 1.5s] or "
                "[pause 500ms].",
                code="bad_pause",
            ) from exc
        if not plan.chunks:
            continue
        gap = plan.lead_ms or turn_ms
        if out:
            prev, vid = out[-1]
            out[-1] = (replace(prev, pause_after_ms=gap), vid)
        else:
            lead_ms = plan.lead_ms
        for c in plan.chunks:
            out.append(
                (
                    replace(c, index=len(out), start=c.start + turn.start, end=c.end + turn.start),
                    turn.voice_id,
                )
            )
    if out:
        last, vid = out[-1]
        out[-1] = (replace(last, pause_after_ms=0), vid)
    return out, lead_ms


def create_generation(
    session: Session,
    *,
    voice_id: str,
    script: str,
    language: str,
    engine: str | None = None,
    settings: dict[str, Any] | None = None,
) -> tuple[Generation, Job]:
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise NotFound("Voice not found", code="voice_not_found")
    script = script.strip()
    if not script:
        raise Invalid("Type or paste a script first.", code="empty_script")
    if len(script) > MAX_SCRIPT_CHARS:
        raise Invalid(
            f"Script is too long (max {MAX_SCRIPT_CHARS:,} characters).", code="script_too_long"
        )

    engine_name = engine or get_settings().default_engine
    if engine_name not in registry.engine_names():
        raise Invalid(f"Unknown engine '{engine_name}'.", code="engine_unknown")
    eng = registry.get_engine(engine_name)
    avail = eng.availability()
    if not avail.ok:
        raise Invalid(f"{eng.label} is unavailable: {avail.reason}", code="engine_unavailable")
    if language not in eng.supported_languages:
        raise Invalid(f"{eng.label} doesn't support '{language}'.", code="language_unsupported")

    # Speakers: the selected voice, plus any voice named in [Name]: tags.
    if dialogue.is_dialogue(script):
        names = dict(session.execute(select(Voice.id, Voice.name)).all())
        try:
            turns = dialogue.parse_turns(script, voice_id, names)
        except dialogue.DialogueError as exc:
            raise Invalid(str(exc), code=exc.code) from exc
    else:
        turns = [dialogue.Turn(voice_id, 0, len(script))]
    speaker_ids = list(dict.fromkeys(t.voice_id for t in turns))
    for vid in speaker_ids:
        _check_voice(session, session.get(Voice, vid), eng)

    clean = _clean_settings(settings)
    cfg = get_settings()
    planned, lead_ms = _plan(
        script,
        turns,
        max_chars=eng.max_chunk_chars(language),
        sentence_ms=clean.get("sentence_pause_ms", cfg.pause_sentence_ms),
        paragraph_ms=clean.get("paragraph_pause_ms", cfg.pause_paragraph_ms),
        turn_ms=clean.get("turn_pause_ms", cfg.pause_turn_ms),
    )
    if not planned:
        raise Invalid(
            "There’s nothing to say: the script only has pauses or tags.", code="empty_script"
        )
    if lead_ms:
        clean["lead_pause_ms"] = lead_ms  # silence before the first sentence
    if len(speaker_ids) > 1 or speaker_ids[0] != voice_id:
        clean["speakers"] = speaker_ids
    gen = Generation(
        voice_id=voice_id,
        engine=engine_name,
        language=language,
        script=script,
        settings=clean,
        status="queued",
        chunk_count=len(planned),
    )
    session.add(gen)
    session.flush()
    entries = pronunciation.list_entries(session)
    for c, vid in planned:
        spoken, applied = pronunciation.apply(c.text, language, entries)
        session.add(
            GenerationChunk(
                generation_id=gen.id,
                idx=c.index,
                text=c.text,
                voice_id=vid if vid != voice_id else None,
                spoken_text=spoken if applied else None,
                char_start=c.start,
                char_end=c.end,
                pause_after_ms=c.pause_after_ms,
            )
        )
    session.commit()
    job = get_runner().submit(
        session, "generate", {"generation_id": gen.id}, voice_id=voice_id, generation_id=gen.id
    )
    return gen, job


def get_generation(session: Session, generation_id: str) -> Generation:
    gen = session.get(Generation, generation_id, options=[selectinload(Generation.chunks)])
    if gen is None:
        raise NotFound("Generation not found", code="generation_not_found")
    return gen


def list_generations(
    session: Session, voice_id: str | None = None, limit: int = 100
) -> list[Generation]:
    q = select(Generation).order_by(Generation.created_at.desc()).limit(min(limit, 500))
    if voice_id:
        q = q.where(Generation.voice_id == voice_id)
    return list(session.scalars(q))


def regenerate(session: Session, generation_id: str) -> tuple[Generation, Job]:
    old = get_generation(session, generation_id)
    return create_generation(
        session,
        voice_id=old.voice_id,
        script=old.script,
        language=old.language,
        engine=old.engine,
        settings=old.settings,
    )


def delete_generation(session: Session, generation_id: str) -> int:
    gen = get_generation(session, generation_id)
    if gen.status in ("queued", "running"):
        raise Invalid("This generation is still running.", code="busy")
    for job in session.scalars(select(Job).where(Job.generation_id == generation_id)):
        session.delete(job)
    session.delete(gen)
    session.commit()
    return storage.remove_tree(storage.generation_dir(generation_id))


def audio_file(session: Session, generation_id: str, fmt: str = "wav") -> Path:
    gen = get_generation(session, generation_id)
    if gen.status != "done" or not gen.audio_path:
        raise Invalid("Audio isn't ready yet.", code="not_ready")
    wav = storage.resolve(gen.audio_path)
    if fmt == "wav":
        return wav
    if fmt == "mp3":
        mp3 = wav.with_suffix(".mp3")
        if not mp3.exists():
            audio.export_mp3(wav, mp3)
        return mp3
    raise Invalid("Format must be wav or mp3.", code="format")


def subtitles(session: Session, generation_id: str, fmt: str = "srt") -> str:
    """SRT or WebVTT text for a finished generation (dialogues get speaker names)."""
    from app.services import subtitles as subs

    gen = get_generation(session, generation_id)
    if gen.status != "done" or gen.duration_seconds is None:
        raise Invalid("Subtitles are available once the audio is ready.", code="not_ready")
    names = None
    speakers = (gen.settings or {}).get("speakers")
    if speakers and (len(speakers) > 1 or speakers[0] != gen.voice_id):
        names = dict(session.execute(select(Voice.id, Voice.name)).all())
    try:
        spans = subs.chunk_spans(gen.chunks, gen.duration_seconds, names, gen.voice_id)
    except ValueError as exc:
        raise Invalid(str(exc), code="no_timing") from exc
    cues = subs.build_cues(spans)
    if fmt == "srt":
        return subs.to_srt(cues)
    if fmt == "vtt":
        return subs.to_vtt(cues)
    raise Invalid("Format must be srt or vtt.", code="format")


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------


@job_handler("generate")
def run_generation(ctx: JobContext, payload: dict[str, Any]) -> dict[str, Any]:
    gen_id = payload["generation_id"]
    with ctx.session() as s:
        gen = get_generation(s, gen_id)
        voice = s.get(Voice, gen.voice_id)
        if voice is None:
            raise NotFound("Voice was deleted")
        gen.status = "running"
        s.commit()
        engine = registry.get_engine(gen.engine)
        out_dir = storage.generation_dir(gen_id)
        (out_dir / "chunks").mkdir(parents=True, exist_ok=True)
        t_start = time.perf_counter()

        # Voiceprints (one per speaker): cached after the first time, which is what makes
        # repeat generations faster.
        speaker_ids = gen.settings.get("speakers") or [gen.voice_id]
        profiles: dict[str, Any] = {}
        names: dict[str, str] = {}
        fresh = False
        ctx.progress(0.01, "voiceprint", "Preparing voice…")
        for k, vid in enumerate(speaker_ids):
            v = s.get(Voice, vid)
            if v is None:
                raise NotFound("A voice in this dialogue was deleted")
            span = (0.01 + 0.07 * k / len(speaker_ids), 0.01 + 0.07 * (k + 1) / len(speaker_ids))
            profiles[vid], was_fresh = ensure_profile(s, v, gen.engine, ctx, span)
            names[vid] = v.name
            fresh = fresh or was_fresh
        ctx.progress(
            0.08,
            "voiceprint",
            "Voiceprint extracted" if fresh else "Using cached voiceprint",
            event="voiceprint",
            cached=not fresh,
        )
        if not engine.is_loaded:
            # Cached voiceprint but cold model (e.g. after a restart): say so, or the UI
            # would sit on "sentence 1" for the ~30 s the model takes to load.
            ctx.progress(0.08, "loading_model", f"Loading {engine.label}…")
            engine.load()
        gen.engine_version = engine.version

        chunks = list(gen.chunks)
        n = len(chunks)
        arrays, sr = [], engine.sample_rate
        opts = {k: v for k, v in gen.settings.items() if k in ("speed", "temperature")}
        dialogue_mode = len(profiles) > 1 or gen.voice_id not in profiles
        for i, ch in enumerate(chunks):
            speaker = ch.voice_id or gen.voice_id
            ctx.progress(
                0.08 + 0.88 * i / n,
                "synthesizing",
                f"Sentence {i + 1} of {n}" + (f", {names[speaker]}" if dialogue_mode else ""),
                event="chunk_started",
                index=i,
                start=ch.char_start,
                end=ch.char_end,
                total=n,
                voice_id=speaker,
            )
            t0 = time.perf_counter()
            res = engine.synthesize(
                ch.spoken_text or ch.text, profiles[speaker], gen.language, **opts
            )
            compute = time.perf_counter() - t0
            sr = res.sample_rate
            path = out_dir / "chunks" / f"{i:03d}.wav"
            audio.write_wav(path, res.audio, sr)
            ch.status, ch.audio_path = "done", storage.rel(path)
            ch.duration_seconds = round(len(res.audio) / sr, 3)
            ch.compute_seconds = round(compute, 3)
            gen.device = res.device
            s.commit()
            arrays.append(res.audio)
            ctx.progress(
                0.08 + 0.88 * (i + 1) / n,
                "synthesizing",
                f"Sentence {i + 1} of {n} done",
                event="chunk_done",
                index=i,
                total=n,
                duration=ch.duration_seconds,
                compute=ch.compute_seconds,
            )

        ctx.progress(0.97, "stitching", "Stitching audio…")
        stitched, offsets = stitch(
            arrays,
            [c.pause_after_ms for c in chunks],
            sr,
            lead_ms=int(gen.settings.get("lead_pause_ms", 0)),
        )
        final = audio.write_wav(out_dir / "output.wav", stitched, sr)
        for ch, off in zip(chunks, offsets, strict=True):
            ch.offset_seconds = off
        gen.audio_path = storage.rel(final)
        gen.duration_seconds = round(len(stitched) / sr, 2)
        gen.compute_seconds = round(time.perf_counter() - t_start, 2)
        gen.status = "done"
        s.commit()
        ctx.progress(
            1.0,
            "done",
            "Ready",
            event="generation_done",
            duration=gen.duration_seconds,
            compute=gen.compute_seconds,
        )
        return {
            "generation_id": gen_id,
            "duration": gen.duration_seconds,
            "compute": gen.compute_seconds,
            "device": gen.device,
            "voiceprint_cached": not fresh,
        }


@on_job_failure("generate")
def _generation_failed(session: Session, job: Job) -> None:
    gen = session.get(Generation, job.generation_id) if job.generation_id else None
    if gen is not None:
        gen.status, gen.error = "failed", job.error
