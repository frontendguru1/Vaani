"""Subtitles (SRT / WebVTT) for a finished generation.

Timing comes from the stitched audio: chunk i starts at `offset_seconds`, and ends where its
pause begins (the next chunk's offset minus this chunk's pause), or at the end of the file.
Text is the script as written (not the pronunciation-fixed form). Readability rules:
lines wrap at ~42 characters, at most 2 lines per cue; longer sentences are split into
several cues, timed by their share of the characters.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

MAX_LINE = 42
MAX_LINES = 2
MIN_CUE_SECONDS = 0.8


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str  # may contain "\n"


@dataclass(frozen=True)
class Span:
    """One spoken chunk, already placed on the timeline."""

    start: float
    end: float
    text: str
    speaker: str | None = None


def chunk_spans(
    chunks,
    total_seconds: float,
    speaker_names: dict[str, str] | None = None,
    default_voice: str | None = None,
) -> list[Span]:  # noqa: ANN001
    """`chunks`: ordered GenerationChunk-like objects with offset_seconds, pause_after_ms,
    text and voice_id. Speaker names are only attached for dialogues."""
    chunks = list(chunks)
    spans: list[Span] = []
    for i, c in enumerate(chunks):
        if c.offset_seconds is None:
            raise ValueError("This generation has no timing information.")
        if i + 1 < len(chunks):
            end = chunks[i + 1].offset_seconds - (c.pause_after_ms or 0) / 1000
        else:
            end = total_seconds
        speaker = None
        if speaker_names:
            speaker = speaker_names.get(c.voice_id or default_voice or "")
        spans.append(
            Span(
                c.offset_seconds,
                max(c.offset_seconds + 0.1, end),
                " ".join(c.text.split()),
                speaker,
            )
        )
    return spans


def _wrap(text: str, width: int = MAX_LINE) -> list[str]:
    return textwrap.wrap(text, width, break_long_words=True, break_on_hyphens=False) or [""]


def _balanced(text: str) -> list[str]:
    """Two-line cues read better with lines of similar length ("…studied at / IIT." looks
    broken). Use the narrowest width that still fits in two lines."""
    lines = _wrap(text)
    if len(lines) != 2:
        return lines
    # Prefer breaking after sentence/clause punctuation when both lines fit and neither is
    # tiny: "Welcome to Vaani." / "My friend studied at IIT."
    best = None
    for m in re.finditer(r"[.!?।,;:—]\s+", text):
        a, b = text[: m.start() + 1].strip(), text[m.end() :].strip()
        if (
            a
            and b
            and len(a) <= MAX_LINE
            and len(b) <= MAX_LINE
            and min(len(a), len(b)) * 3 >= max(len(a), len(b))
        ):
            score = abs(len(a) - len(b)) - (10 if text[m.start()] in ".!?।" else 0)
            if best is None or score < best[0]:
                best = (score, [a, b])
    if best:
        return best[1]
    for width in range((len(text) + 1) // 2, MAX_LINE + 1):
        candidate = _wrap(text, width)
        if len(candidate) == 2:
            return candidate
    return lines


def build_cues(spans: list[Span]) -> list[Cue]:
    cues: list[Cue] = []
    for sp in spans:
        text = f"{sp.speaker}: {sp.text}" if sp.speaker else sp.text
        lines = _wrap(text)
        groups = [lines[i : i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)]
        if len(groups) == 1:
            cues.append(Cue(sp.start, sp.end, "\n".join(_balanced(text))))
            continue
        # Split the time by each group's share of the characters (≈ speaking time).
        weights = [sum(len(line) for line in g) for g in groups]
        total = sum(weights) or 1
        t = sp.start
        for g, w in zip(groups, weights, strict=True):
            dur = (sp.end - sp.start) * w / total
            cues.append(Cue(t, t + dur, "\n".join(g)))
            t += dur
    # Very short cues are hard to read: stretch into the following gap when there is room.
    out = []
    for i, c in enumerate(cues):
        limit = cues[i + 1].start if i + 1 < len(cues) else c.end
        end = c.end if c.end - c.start >= MIN_CUE_SECONDS else min(limit, c.start + MIN_CUE_SECONDS)
        out.append(Cue(c.start, max(c.end, end), c.text))
    return out


def _ts(seconds: float, sep: str) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{i}\n{_ts(c.start, ',')} --> {_ts(c.end, ',')}\n{c.text}"
        for i, c in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[Cue]) -> str:
    blocks = [f"{_ts(c.start, '.')} --> {_ts(c.end, '.')}\n{c.text}" for c in cues]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"
