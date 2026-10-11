"""Split a script into sentence-level chunks for synthesis.

Paragraphs are separated by blank lines. Sentences end at . ? ! । ॥ (and their runs, e.g.
"?!" or "..."). Very short sentences are merged with the next one so the engine gets
enough context; sentences longer than `max_chars` are split at clause punctuation, then
at spaces. Each chunk keeps its character span in the original text so the UI can
highlight the sentence currently being generated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sentence end: terminal punctuation run, optional closing quotes/brackets, then space/end.
_SENT_END = re.compile(r"[.?!।॥]+[\"'”’)\]]*(?=\s|$)")
_PARA_SPLIT = re.compile(r"\n\s*\n")
_CLAUSE = re.compile(r"[,;:—–]\s|\s-\s")

MIN_CHARS = 20


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start: int  # char offset into the original script
    end: int
    paragraph: int
    pause_after_ms: int


def _spans(text: str, pattern: re.Pattern[str], base: int) -> list[tuple[int, int]]:
    """Split `text` after each match of `pattern`; return stripped (start, end) spans."""
    out: list[tuple[int, int]] = []
    pos = 0
    for m in pattern.finditer(text):
        out.append((pos, m.end()))
        pos = m.end()
    out.append((pos, len(text)))
    result = []
    for s, e in out:
        seg = text[s:e]
        lstrip = len(seg) - len(seg.lstrip())
        rstrip = len(seg) - len(seg.rstrip())
        if seg.strip():
            result.append((base + s + lstrip, base + e - rstrip))
    return result


def _split_long(script: str, span: tuple[int, int], max_chars: int) -> list[tuple[int, int]]:
    s, e = span
    if e - s <= max_chars:
        return [span]
    # Prefer clause boundaries, greedily packing clauses up to max_chars.
    pieces = _spans(script[s:e], _CLAUSE, s)
    if len(pieces) > 1:
        packed: list[tuple[int, int]] = []
        cur = pieces[0]
        for p in pieces[1:]:
            if p[1] - cur[0] <= max_chars:
                cur = (cur[0], p[1])
            else:
                packed.append(cur)
                cur = p
        packed.append(cur)
        return [q for p in packed for q in _split_long(script, p, max_chars)]
    # Fall back to the last space before the limit (or a hard cut for space-less text).
    cut = script.rfind(" ", s, s + max_chars)
    if cut <= s:
        cut = s + max_chars
    left = (s, len(script[s:cut].rstrip()) + s)
    rest_start = cut
    while rest_start < e and script[rest_start].isspace():
        rest_start += 1
    return [left, *_split_long(script, (rest_start, e), max_chars)]


def chunk_text(
    script: str,
    *,
    max_chars: int = 220,
    sentence_pause_ms: int = 350,
    paragraph_pause_ms: int = 800,
    min_chars: int = MIN_CHARS,
) -> list[Chunk]:
    if max_chars < 20:
        raise ValueError("max_chars must be at least 20")

    raw: list[tuple[int, int, int]] = []  # (start, end, paragraph)
    for p_idx, (ps, pe) in enumerate(_spans(script, _PARA_SPLIT, 0)):
        sentences = _spans(script[ps:pe], _SENT_END, ps)
        # Merge short sentences forward (but never across paragraphs or past max_chars).
        merged: list[tuple[int, int]] = []
        for sp in sentences:
            if (
                merged
                and (merged[-1][1] - merged[-1][0]) < min_chars
                and sp[1] - merged[-1][0] <= max_chars
            ):
                merged[-1] = (merged[-1][0], sp[1])
            else:
                merged.append(sp)
        if len(merged) > 1 and merged[-1][1] - merged[-1][0] < min_chars:
            last = merged.pop()
            if last[1] - merged[-1][0] <= max_chars:
                merged[-1] = (merged[-1][0], last[1])
            else:
                merged.append(last)
        for sp in merged:
            raw += [(s, e, p_idx) for s, e in _split_long(script, sp, max_chars)]

    chunks: list[Chunk] = []
    for i, (s, e, p) in enumerate(raw):
        is_last = i == len(raw) - 1
        next_para = not is_last and raw[i + 1][2] != p
        pause = 0 if is_last else (paragraph_pause_ms if next_para else sentence_pause_ms)
        chunks.append(Chunk(i, script[s:e], s, e, p, pause))
    return chunks
