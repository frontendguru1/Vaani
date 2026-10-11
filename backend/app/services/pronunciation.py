"""Pronunciation dictionary: user-defined replacements applied to each chunk right before
synthesis (names, acronyms, words an engine says wrong). The script the user sees is never
changed, so sentence highlighting still lines up.

Matching rules:
- whole words only — "IIT" doesn't touch "IITians"; works for Devanagari too (Python's \\w
  doesn't cover combining vowel signs like ा ि, so word characters are spelled out);
- longest term wins when terms overlap ("New York" before "York");
- one pass, so a replacement is never itself replaced again;
- entries with a language apply only to that language; entries without one apply to all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PronunciationEntry
from app.services.errors import Conflict, Invalid, NotFound

# Letters, digits, underscore, plus all of Devanagari (incl. matras / nukta / virama).
_WORD = r"[\wऀ-ॿ‌‍]"
LANGUAGES = {"en", "hi"}


@dataclass(frozen=True)
class Applied:
    term: str
    replacement: str
    count: int


def _validate(term: str, replacement: str, language: str | None) -> tuple[str, str, str | None]:
    term, replacement = term.strip(), replacement.strip()
    if not term:
        raise Invalid("Type the word or phrase to replace.", code="term_required")
    if not replacement:
        raise Invalid("Type how it should be said.", code="replacement_required")
    if len(term) > 200 or len(replacement) > 400:
        raise Invalid(
            "That’s too long (word max 200, replacement max 400 characters).", code="too_long"
        )
    if language is not None and language not in LANGUAGES:
        raise Invalid("Language must be English, Hindi or all.", code="language")
    if term.casefold() == replacement.casefold():
        raise Invalid("The replacement is the same as the word.", code="same")
    return term, replacement, language


def _duplicate(session: Session, term: str, language: str | None, exclude: str | None) -> bool:
    q = select(PronunciationEntry.id).where(
        func.lower(PronunciationEntry.term) == term.lower(),
        PronunciationEntry.language.is_(None)
        if language is None
        else PronunciationEntry.language == language,
    )
    if exclude:
        q = q.where(PronunciationEntry.id != exclude)
    return session.scalar(q) is not None


def list_entries(session: Session) -> list[PronunciationEntry]:
    return list(
        session.scalars(select(PronunciationEntry).order_by(func.lower(PronunciationEntry.term)))
    )


def create_entry(
    session: Session,
    term: str,
    replacement: str,
    language: str | None = None,
    case_sensitive: bool = False,
) -> PronunciationEntry:
    term, replacement, language = _validate(term, replacement, language)
    if _duplicate(session, term, language, None):
        raise Conflict(f"“{term}” is already in the dictionary.", code="duplicate")
    entry = PronunciationEntry(
        term=term, replacement=replacement, language=language, case_sensitive=case_sensitive
    )
    session.add(entry)
    session.commit()
    return entry


def update_entry(session: Session, entry_id: str, **fields) -> PronunciationEntry:  # noqa: ANN003
    entry = session.get(PronunciationEntry, entry_id)
    if entry is None:
        raise NotFound("Entry not found", code="entry_not_found")
    language = fields["language"] if "language" in fields else entry.language
    term, replacement, language = _validate(
        fields.get("term", entry.term), fields.get("replacement", entry.replacement), language
    )
    if _duplicate(session, term, language, entry.id):
        raise Conflict(f"“{term}” is already in the dictionary.", code="duplicate")
    entry.term, entry.replacement, entry.language = term, replacement, language
    if fields.get("case_sensitive") is not None:
        entry.case_sensitive = bool(fields["case_sensitive"])
    session.commit()
    return entry


def delete_entry(session: Session, entry_id: str) -> None:
    entry = session.get(PronunciationEntry, entry_id)
    if entry is None:
        raise NotFound("Entry not found", code="entry_not_found")
    session.delete(entry)
    session.commit()


def apply(text: str, language: str, entries: list[PronunciationEntry]) -> tuple[str, list[Applied]]:
    """Return (text with replacements, what was applied). Pure; no DB access."""
    usable = [e for e in entries if e.language in (None, language) and e.term.strip()]
    if not usable or not text:
        return text, []
    # Longest first so the alternation prefers "New York" over "York".
    usable.sort(key=lambda e: len(e.term), reverse=True)
    lookup: dict[str, PronunciationEntry] = {}
    parts = []
    for i, e in enumerate(usable):
        group = f"t{i}"
        flags = "" if e.case_sensitive else "(?i:"
        body = re.escape(e.term.strip()).replace(r"\ ", r"\s+")  # tolerate line breaks/spaces
        parts.append(f"(?P<{group}>{flags}{body}{')' if flags else ''})")
        lookup[group] = e
    pattern = re.compile(rf"(?<!{_WORD})(?:{'|'.join(parts)})(?!{_WORD})")
    counts: dict[str, int] = {}

    def sub(m: re.Match) -> str:
        e = lookup[m.lastgroup]  # type: ignore[index]
        counts[e.id] = counts.get(e.id, 0) + 1
        return e.replacement

    out = pattern.sub(sub, text)
    applied = [Applied(e.term, e.replacement, counts[e.id]) for e in usable if e.id in counts]
    return out, applied


def apply_for(session: Session, text: str, language: str) -> tuple[str, list[Applied]]:
    return apply(text, language, list_entries(session))
