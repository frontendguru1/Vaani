"""XTTS-v2 via the maintained `coqui-tts` package. Runs in-process (main venv)."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

from app.config import get_settings
from app.engines.base import (
    Availability,
    EngineError,
    SynthesisResult,
    TTSEngine,
    VoiceProfile,
)
from app.engines.device import pick_torch_device
from app.engines.registry import register

log = logging.getLogger("vaani.engines.xtts")

MODEL_ID = "tts_models/multilingual/multi-dataset/xtts_v2"
MODEL_DIRNAME = "tts_models--multilingual--multi-dataset--xtts_v2"
LATENTS_FILE = "xtts_latents.pt"


def model_dir() -> Path:
    return get_settings().models_dir / "tts" / MODEL_DIRNAME


def is_downloaded() -> bool:
    d = model_dir()
    return (d / "model.pth").is_file() and (d / "config.json").is_file()


@register
class XTTSEngine(TTSEngine):
    name = "xtts"
    label = "XTTS-v2"
    # Hindi + English are what Vaani cares about; XTTS supports 17 languages.
    supported_languages = frozenset(
        {
            "en",
            "hi",
            "es",
            "fr",
            "de",
            "it",
            "pt",
            "pl",
            "tr",
            "ru",
            "nl",
            "cs",
            "ar",
            "zh-cn",
            "hu",
            "ko",
            "ja",
        }
    )
    sample_rate = 24_000
    license = "Coqui Public Model License (non-commercial)"

    def __init__(self, device: str | None = None) -> None:
        super().__init__()
        self._device_override = device or get_settings().xtts_device
        self._model: Any = None
        self._latents: dict[Path, tuple[Any, Any]] = {}
        self._lock = threading.Lock()

    # The tokenizer warns (and truncates audio) above 250 chars for en, 150 for hi.
    _CHAR_LIMITS = {"en": 230, "hi": 140, "zh-cn": 75, "ja": 65, "ko": 85}

    def max_chunk_chars(self, language: str) -> int:
        return self._CHAR_LIMITS.get(language, 200)

    @property
    def version(self) -> str:
        try:
            return f"coqui-tts {importlib.metadata.version('coqui-tts')}"
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def availability(self) -> Availability:
        if importlib.util.find_spec("TTS") is None:
            return Availability(False, "coqui-tts is not installed")
        return Availability(
            True, "" if is_downloaded() else "model downloads on first use (2.1 GB)"
        )

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def download(self) -> Path:
        if is_downloaded():
            return model_dir()
        # The user accepted the CPML (non-commercial) when approving the download.
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.utils.manage import ModelManager

        log.info("Downloading %s (~2.1 GB) to %s", MODEL_ID, get_settings().models_dir)
        path, _cfg, _item = ModelManager(
            output_prefix=get_settings().models_dir, progress_bar=True
        ).download_model(MODEL_ID)
        return Path(path)

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts

            path = self.download()
            config = XttsConfig()
            config.load_json(str(path / "config.json"))
            model = Xtts.init_from_config(config)
            model.load_checkpoint(config, checkpoint_dir=str(path), eval=True)

            device = pick_torch_device(self.name, self._device_override)
            if device == "mps":
                try:
                    model.to("mps")
                except Exception as exc:  # noqa: BLE001
                    log.warning("XTTS failed to move to MPS (%s); falling back to CPU", exc)
                    device = "cpu"
            if device == "cpu":
                model.to("cpu")
            self.device = device
            self._model = model
            log.info("XTTS-v2 loaded on %s", device.upper())

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._latents.clear()
            self.device = None

    def builtin_speakers(self) -> list[str]:
        path = model_dir() / "speakers_xtts.pth"
        if not path.is_file():
            return []
        import torch

        return list(torch.load(path, map_location="cpu", weights_only=True))

    def create_builtin_voice(self, key: str, cache_dir: Path) -> VoiceProfile:
        """Copy a studio speaker's latents (from speakers_xtts.pth, part of the model download)
        into the same cache format create_voice() writes. No model load needed."""
        import torch

        path = model_dir() / "speakers_xtts.pth"
        if not path.is_file():
            self.download()
        speakers = torch.load(path, map_location="cpu", weights_only=True)
        if key not in speakers:
            raise EngineError(f"XTTS has no built-in speaker called {key!r}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "gpt_cond_latent": speakers[key]["gpt_cond_latent"].cpu(),
                "speaker_embedding": speakers[key]["speaker_embedding"].cpu(),
            },
            cache_dir / LATENTS_FILE,
        )
        return VoiceProfile(self.name, self.version, cache_dir, {"latents": LATENTS_FILE})

    def create_voice(
        self,
        reference_files: list[Path],
        cache_dir: Path,
        transcripts: list[str] | None = None,
    ) -> VoiceProfile:
        import torch

        if not reference_files:
            raise EngineError("XTTS needs at least one reference file")
        self.load()
        cache_dir.mkdir(parents=True, exist_ok=True)
        with self._lock, torch.inference_mode():
            gpt_cond_latent, speaker_embedding = self._model.get_conditioning_latents(
                audio_path=[str(p) for p in reference_files],
                max_ref_length=30,
            )
        torch.save(
            {
                "gpt_cond_latent": gpt_cond_latent.cpu(),
                "speaker_embedding": speaker_embedding.cpu(),
            },
            cache_dir / LATENTS_FILE,
        )
        profile = VoiceProfile(self.name, self.version, cache_dir, {"latents": LATENTS_FILE})
        self._latents[profile.path("latents")] = (gpt_cond_latent, speaker_embedding)
        return profile

    def _get_latents(self, profile: VoiceProfile) -> tuple[Any, Any]:
        import torch

        path = profile.path("latents")
        if path not in self._latents:
            if not path.is_file():
                raise EngineError(f"Cached XTTS latents missing: {path}")
            blob = torch.load(path, map_location="cpu")
            self._latents[path] = (blob["gpt_cond_latent"], blob["speaker_embedding"])
        gpt, spk = self._latents[path]
        dev = self.device or "cpu"
        return gpt.to(dev), spk.to(dev)

    def synthesize(
        self, text: str, profile: VoiceProfile, language: str, **options: Any
    ) -> SynthesisResult:
        import torch

        if language not in self.supported_languages:
            raise EngineError(f"XTTS does not support language '{language}'")
        self.load()
        gpt, spk = self._get_latents(profile)
        kwargs = {k: options[k] for k in ("temperature", "speed", "top_p", "top_k") if k in options}
        with self._lock, torch.inference_mode():
            out = self._model.inference(text, language, gpt, spk, **kwargs)
        audio = np.asarray(out["wav"], dtype=np.float32)
        return SynthesisResult(audio, self.sample_rate, self.device or "cpu")
