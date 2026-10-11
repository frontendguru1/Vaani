"""A tiny in-process engine so services can be tested end-to-end without real models."""

from pathlib import Path

import numpy as np

from app.engines.base import EngineError, SynthesisResult, TTSEngine, VoiceProfile
from app.engines.registry import register


@register
class FakeEngine(TTSEngine):
    name = "fake"
    label = "Fake"
    supported_languages = frozenset({"en", "hi"})
    sample_rate = 16_000
    license = "test"
    fail_on: str | None = None  # synthesize raises if this substring is in the text
    voices_created = 0

    def __init__(self) -> None:
        super().__init__()
        self._loaded = False

    @property
    def version(self) -> str:
        return "fake-1"

    def max_chunk_chars(self, language: str) -> int:
        return 60

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded, self.device = True, "cpu"

    def unload(self) -> None:
        self._loaded = False

    def create_voice(self, reference_files, cache_dir: Path, transcripts=None) -> VoiceProfile:
        if not reference_files:
            raise EngineError("no refs")
        FakeEngine.voices_created += 1
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(cache_dir / "emb.npy", np.ones(4))
        return VoiceProfile(
            self.name, self.version, cache_dir, {"emb": "emb.npy", "refs": len(reference_files)}
        )

    def builtin_speakers(self) -> list[str]:
        return ["Fake Female", "Fake Male"]

    def create_builtin_voice(self, key, cache_dir: Path) -> VoiceProfile:
        if key not in self.builtin_speakers():
            raise EngineError(f"no speaker {key}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(cache_dir / "emb.npy", np.zeros(4))
        return VoiceProfile(self.name, self.version, cache_dir, {"emb": "emb.npy", "builtin": key})

    def synthesize(self, text, profile, language, **options) -> SynthesisResult:
        if self.fail_on and self.fail_on in text:
            raise EngineError(f"boom on {text!r}")
        n = int(self.sample_rate * (0.2 + 0.02 * len(text)))
        t = np.arange(n) / self.sample_rate
        return SynthesisResult(
            (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), self.sample_rate, "cpu"
        )
