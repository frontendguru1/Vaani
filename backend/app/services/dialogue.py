"""Multi-voice dialogue scripts.

A line that starts with a speaker tag hands the following text to that voice:

    [Papa]: Beta, what are you reading?
    [Meera]: A story about a tiger! [pause 1s] A big one.

Text before the first tag (and any untagged script) belongs to the default voice — the one
chosen on the Generate page. Names match voice names, ignoring case and extra spaces.
Spans returned here point into the original script (the tags themselves are never spoken).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TAG_RE = re.compile(r"^[ \t]*\[([^\[\]\n]{1,120})\][ \t]*:[ \t]*", re.MULTILINE)


class DialogueError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Turn:
    voice_id: str
    start: int  # span of the turn's text in the script (tag excluded)
    end: int


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def find_tags(script: str) -> list[re.Match[str]]:
    # "[pause 1s]:" at a line start is a pause marker followed by a colon, not a speaker.
    return [m for m in TAG_RE.finditer(script) if not _norm(m.group(1)).startswith("pause")]


def is_dialogue(script: str) -> bool:
    return bool(find_tags(script))


def parse_turns(script: str, default_voice_id: str, voices: dict[str, str]) -> list[Turn]:
    """`voices` maps voice id → name. Raises DialogueError for unknown or ambiguous names."""
    by_name: dict[str, list[str]] = {}
    for vid, name in voices.items():
        by_name.setdefault(_norm(name), []).append(vid)

    tags = find_tags(script)
    unknown = sorted({m.group(1).strip() for m in tags if _norm(m.group(1)) not in by_name})
    if unknown:
        names = ", ".join(sorted(voices.values())) or "none yet"
        raise DialogueError(
            f"No voice called {', '.join(unknown)}. Speaker tags must match a voice name "
            f"(your voices: {names}).",
            code="unknown_speaker",
        )
    dupes = sorted({m.group(1).strip() for m in tags if len(by_name[_norm(m.group(1))]) > 1})
    if dupes:
        raise DialogueError(
            f"More than one voice is called {', '.join(dupes)}. Rename one so the script is "
            "unambiguous.",
            code="ambiguous_speaker",
        )

    turns: list[Turn] = []
    current, pos = default_voice_id, 0
    for m in tags:
        if script[pos : m.start()].strip():
            turns.append(Turn(current, pos, m.start()))
        current = by_name[_norm(m.group(1))][0]
        pos = m.end()
    if script[pos:].strip():
        turns.append(Turn(current, pos, len(script)))
    return turns
