"""Batch generation: several scripts, one voice and one set of settings, generated in order.

Each item becomes an ordinary Generation (with batch_id, batch_index, title), so pause
markers, dialogue tags, the pronunciation dictionary, similarity scores and subtitles all
work per item. All items are validated before any is queued: one bad script means nothing
starts, and the error says which item and why.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Batch, GenerationChunk, Job, Voice
from app.services import generation, storage
from app.services.errors import Invalid, NotFound

MAX_ITEMS = 50


def _get(session: Session, batch_id: str) -> Batch:
    # populate_existing: always re-read statuses (the job thread updates them in its own
    # session, so a long-lived session would otherwise see stale "queued" items).
    b = session.get(
        Batch, batch_id, options=[selectinload(Batch.generations)], populate_existing=True
    )
    if b is None:
        raise NotFound("Batch not found", code="batch_not_found")
    return b


def create_batch(
    session: Session,
    *,
    voice_id: str,
    language: str,
    items: list[dict[str, str]],
    title: str = "",
    engine: str | None = None,
    settings: dict[str, Any] | None = None,
) -> Batch:
    voice = session.get(Voice, voice_id)
    if voice is None:
        raise NotFound("Voice not found", code="voice_not_found")
    items = [i for i in items if (i.get("script") or "").strip()]
    if not items:
        raise Invalid("Add at least one script.", code="empty_batch")
    if len(items) > MAX_ITEMS:
        raise Invalid(f"At most {MAX_ITEMS} scripts per batch.", code="too_many_items")

    # One engine for the whole batch, so every item sounds the same.
    engine_name = generation.resolve_engine(session, voice, language, engine)
    prepared, problems = [], []
    for n, item in enumerate(items, start=1):
        label = (item.get("title") or "").strip() or f"Item {n}"
        try:
            prepared.append(
                (
                    generation.prepare_generation(
                        session,
                        voice_id=voice_id,
                        script=item["script"],
                        language=language,
                        engine=engine_name,
                        settings=settings,
                    ),
                    label,
                )
            )
        except Invalid as exc:
            problems.append(
                {"index": n - 1, "title": label, "detail": exc.message, "code": exc.code}
            )
    if problems:
        first = problems[0]
        more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
        raise Invalid(
            f"{first['title']}: {first['detail']}{more}", code="batch_invalid", details=problems
        )

    batch = Batch(
        title=title.strip() or f"Batch of {len(items)}",
        voice_id=voice_id,
        language=language,
        engine=engine_name,
        settings=prepared[0][0].settings if prepared else {},
    )
    session.add(batch)
    session.flush()
    gens = [
        generation.save_generation(
            session, prep, batch_id=batch.id, batch_index=i, title=label, commit=False
        )
        for i, (prep, label) in enumerate(prepared)
    ]
    session.commit()
    for g in gens:  # queued in order; the single job thread runs them one after another
        generation.queue_generation(session, g)
    session.refresh(batch)
    return batch


def summary(session: Session, batch: Batch) -> dict[str, Any]:
    """Status counts and real progress (finished sentences / all sentences)."""
    ids = [g.id for g in batch.generations]
    done_chunks = (
        dict(
            session.execute(
                select(GenerationChunk.generation_id, func.count())
                .where(GenerationChunk.generation_id.in_(ids), GenerationChunk.status == "done")
                .group_by(GenerationChunk.generation_id)
            ).all()
        )
        if ids
        else {}
    )
    total = sum(g.chunk_count for g in batch.generations) or 1
    done = sum(min(done_chunks.get(g.id, 0), g.chunk_count) for g in batch.generations)
    counts: dict[str, int] = {}
    for g in batch.generations:
        counts[g.status] = counts.get(g.status, 0) + 1
    finished = all(g.status in ("done", "failed") for g in batch.generations)
    return {
        "progress": round(done / total, 4),
        "counts": counts,
        "finished": finished,
        "done_chunks": done_chunks,
    }


def list_batches(session: Session, limit: int = 50) -> list[Batch]:
    return list(
        session.scalars(
            select(Batch)
            .options(selectinload(Batch.generations))
            .order_by(Batch.created_at.desc())
            .limit(limit)
        )
    )


def get_batch(session: Session, batch_id: str) -> Batch:
    return _get(session, batch_id)


def cancel_batch(session: Session, batch_id: str) -> int:
    """Stop items that haven't started. The one running now finishes."""
    batch = _get(session, batch_id)
    n = 0
    for g in batch.generations:
        if g.status == "queued":
            g.status, g.error = "failed", "Cancelled"
            for job in session.scalars(
                select(Job).where(Job.generation_id == g.id, Job.status == "queued")
            ):
                job.status, job.error, job.message = "failed", "Cancelled", "Cancelled"
            n += 1
    session.commit()
    return n


def delete_batch(session: Session, batch_id: str) -> int:
    batch = _get(session, batch_id)
    if any(g.status == "running" for g in batch.generations):
        raise Invalid(
            "An item is generating right now. Cancel the batch, then delete it "
            "when that item finishes.",
            code="busy",
        )
    cancel_batch(session, batch_id)
    removed = 0
    for g in list(batch.generations):
        for job in session.scalars(select(Job).where(Job.generation_id == g.id)):
            session.delete(job)
        removed += storage.remove_tree(storage.generation_dir(g.id))
        session.delete(g)
    session.delete(batch)
    session.commit()
    return removed


def _safe(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", name)[:60] or "item"


def build_zip(
    session: Session, batch_id: str, fmt: str = "wav", subtitles: str | None = "srt"
) -> tuple[Path, str]:
    """A ZIP of every finished item ("01 - Title.wav" + subtitles) and a scripts.txt."""
    if fmt not in ("wav", "mp3") or subtitles not in (None, "srt", "vtt"):
        raise Invalid("Format must be wav or mp3; subtitles srt, vtt or none.", code="format")
    batch = _get(session, batch_id)
    ready = [g for g in batch.generations if g.status == "done"]
    if not ready:
        raise Invalid("Nothing has finished yet.", code="not_ready")
    tmp = Path(tempfile.mkstemp(suffix=".zip", dir=storage.data_dir())[1])
    width = max(2, len(str(len(batch.generations))))
    lines = []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for g in ready:
            stem = f"{(g.batch_index or 0) + 1:0{width}d} - {_safe(g.title or 'item')}"
            z.write(generation.audio_file(session, g.id, fmt), f"{stem}.{fmt}")
            if subtitles:
                z.writestr(f"{stem}.{subtitles}", generation.subtitles(session, g.id, subtitles))
            lines.append(f"{stem}\n{g.script}\n")
        z.writestr("scripts.txt", "\n".join(lines))
    return tmp, f"vaani-{_safe(batch.title).replace(' ', '-').lower()}.zip"
