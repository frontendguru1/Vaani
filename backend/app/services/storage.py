"""Where artefacts live on disk. The DB only ever stores paths relative to data_dir.

data/
  voices/<voice_id>/original/      uploads exactly as received
  voices/<voice_id>/processed/     cleaned WAVs + speech segments
  voices/<voice_id>/engines/<eng>/ cached conditioning (latents, ref clips)
  generations/<generation_id>/     chunks/NNN.wav, output.wav, output.mp3
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

from app.config import get_settings


def data_dir() -> Path:
    return get_settings().data_dir


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(data_dir().resolve()))


def resolve(relpath: str) -> Path:
    p = (data_dir() / relpath).resolve()
    # Never let a stored path escape the data dir.
    if data_dir().resolve() not in p.parents and p != data_dir().resolve():
        raise ValueError(f"path escapes data dir: {relpath}")
    return p


def voice_dir(voice_id: str) -> Path:
    return data_dir() / "voices" / voice_id


def engine_cache_dir(voice_id: str, engine: str) -> Path:
    return voice_dir(voice_id) / "engines" / engine


def generation_dir(generation_id: str) -> Path:
    return data_dir() / "generations" / generation_id


def safe_filename(name: str, max_len: int = 80) -> str:
    name = unicodedata.normalize("NFKD", Path(name).name)
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "audio"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext)[:8].lower()
    return f"{stem[:max_len]}.{ext}" if ext else stem[:max_len]


def remove_tree(path: Path) -> int:
    """Delete a directory; return how many files were removed."""
    if not path.exists():
        return 0
    count = sum(1 for p in path.rglob("*") if p.is_file())
    shutil.rmtree(path)
    return count


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0
