"""Consistency check: files without rows, rows whose files are gone."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Generation, Voice, VoiceEngineProfile, VoiceSample
from app.services import storage


@dataclass
class ConsistencyReport:
    orphan_dirs: list[str] = field(default_factory=list)  # on disk, no DB row
    missing_files: list[str] = field(default_factory=list)  # DB row points at nothing

    @property
    def ok(self) -> bool:
        return not self.orphan_dirs and not self.missing_files


def check(session: Session) -> ConsistencyReport:
    report = ConsistencyReport()
    voice_ids = set(session.scalars(select(Voice.id)))
    gen_ids = set(session.scalars(select(Generation.id)))
    for sub, ids in (("voices", voice_ids), ("generations", gen_ids)):
        root = storage.data_dir() / sub
        if root.exists():
            report.orphan_dirs += [
                str(p) for p in sorted(root.iterdir()) if p.is_dir() and p.name not in ids
            ]

    def expect(label: str, relpath: str | None) -> None:
        if relpath and not storage.resolve(relpath).exists():
            report.missing_files.append(f"{label}: {relpath}")

    for s in session.scalars(select(VoiceSample)):
        expect(f"sample {s.id} original", s.original_path)
        expect(f"sample {s.id} processed", s.processed_path)
        for seg in s.segments or []:
            expect(f"sample {s.id} segment", seg["path"])
    for v in session.scalars(select(Voice)):
        expect(f"voice {v.id} preview", v.preview_path)
    for p in session.scalars(select(VoiceEngineProfile)):
        expect(f"profile {p.voice_id}/{p.engine}", p.cache_dir)
    for g in session.scalars(select(Generation).where(Generation.status == "done")):
        expect(f"generation {g.id} audio", g.audio_path)
    return report


def remove_orphans(report: ConsistencyReport) -> int:
    from pathlib import Path

    return sum(storage.remove_tree(Path(d)) for d in report.orphan_dirs)
