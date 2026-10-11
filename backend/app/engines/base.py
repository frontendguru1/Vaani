"""The contract every TTS engine implements. API/UI code only ever talks to this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import numpy as np


@dataclass
class VoiceProfile:
    """An engine's cached conditioning for one voice.

    `data` holds engine-specific values; any file paths in it are relative to `cache_dir`
    so the whole folder can be deleted with the voice.
    """

    engine: str
    engine_version: str
    cache_dir: Path
    data: dict[str, Any] = field(default_factory=dict)

    def path(self, key: str) -> Path:
        return self.cache_dir / self.data[key]

    FILE_SUFFIXES = (".pt", ".wav", ".npy", ".npz", ".safetensors", ".json", ".bin")

    def file_keys(self) -> list[str]:
        """Keys whose values are cache files (as opposed to text like a transcript or a
        built-in speaker's name)."""
        return [
            k
            for k, v in self.data.items()
            if isinstance(v, str) and v.lower().endswith(self.FILE_SUFFIXES)
        ]


@dataclass
class SynthesisResult:
    audio: np.ndarray  # mono float32 in [-1, 1]
    sample_rate: int
    device: str


@dataclass(frozen=True)
class Availability:
    ok: bool
    reason: str = ""


class EngineError(RuntimeError):
    pass


class TTSEngine(ABC):
    name: ClassVar[str]
    label: ClassVar[str]
    supported_languages: ClassVar[frozenset[str]]
    sample_rate: ClassVar[int]
    needs_transcript: ClassVar[bool] = False
    license: ClassVar[str] = ""

    def __init__(self) -> None:
        self.device: str | None = None

    @property
    def version(self) -> str:
        return "unknown"

    def max_chunk_chars(self, language: str) -> int:
        """Longest text the engine handles well in one call; the chunker splits above it."""
        return 200

    def availability(self) -> Availability:
        """Cheap check (no model load): is this engine installed and usable?"""
        return Availability(True)

    def builtin_speakers(self) -> list[str]:
        """Studio speakers that ship with the engine (none by default)."""
        return []

    def create_builtin_voice(self, key: str, cache_dir: Path) -> VoiceProfile:
        raise EngineError(f"{self.label} has no built-in speakers")

    @property
    @abstractmethod
    def is_loaded(self) -> bool: ...

    @abstractmethod
    def load(self) -> None:
        """Load weights into memory. Idempotent; called lazily, kept loaded."""

    @abstractmethod
    def unload(self) -> None: ...

    @abstractmethod
    def create_voice(
        self,
        reference_files: list[Path],
        cache_dir: Path,
        transcripts: list[str] | None = None,
    ) -> VoiceProfile:
        """Compute and persist conditioning from cleaned reference WAVs."""

    @abstractmethod
    def synthesize(
        self, text: str, profile: VoiceProfile, language: str, **options: Any
    ) -> SynthesisResult: ...
