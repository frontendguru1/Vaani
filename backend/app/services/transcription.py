"""Auto-transcription with mlx-whisper (Apple GPU). Used to give every clip timestamped
phrases, so engines that need an exact transcript (F5, IndicF5) can cut a short reference
whose words are known, and so the user can check what was heard.

The model loads lazily once and stays loaded (mlx_whisper caches it in-process).
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings

log = logging.getLogger("vaani.transcription")

WHISPER_SR = 16_000
_lock = threading.Lock()


@dataclass(frozen=True)
class Phrase:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "text": self.text}


def model_dir() -> Path:
    name = get_settings().transcribe_model.rsplit("/", 1)[-1]
    return get_settings().models_dir / "whisper" / name


def is_installed() -> bool:
    return importlib.util.find_spec("mlx_whisper") is not None


def is_downloaded() -> bool:
    d = model_dir()
    has_weights = any(d.glob("*.safetensors")) or (d / "weights.npz").is_file()
    return (d / "config.json").is_file() and has_weights


def status() -> dict:
    return {
        "available": is_installed(),
        "model": get_settings().transcribe_model,
        "downloaded": is_downloaded(),
        "on_create": get_settings().transcribe_on_create,
    }


def _ensure_model() -> str:
    if not is_downloaded():
        from huggingface_hub import snapshot_download

        log.info("Downloading %s to %s", get_settings().transcribe_model, model_dir())
        snapshot_download(get_settings().transcribe_model, local_dir=str(model_dir()))
    return str(model_dir())  # a local path: mlx_whisper never touches the network


def transcribe_array(audio: np.ndarray, language: str | None) -> list[Phrase]:
    """`audio` is mono float32 at 16 kHz."""
    import mlx_whisper

    with _lock:  # one transcription on the GPU at a time
        result = mlx_whisper.transcribe(
            audio.astype(np.float32),
            path_or_hf_repo=_ensure_model(),
            language=language,
            condition_on_previous_text=False,  # avoids repetition loops on short clips
            verbose=None,
        )
    phrases = []
    for seg in result.get("segments", []):
        text = str(seg.get("text", "")).strip()
        if text:
            phrases.append(Phrase(float(seg["start"]), float(seg["end"]), text))
    return phrases


def transcribe_file(path: Path, language: str | None) -> list[Phrase]:
    import librosa

    audio, _ = librosa.load(str(path), sr=WHISPER_SR, mono=True)
    return transcribe_array(audio, language)


def best_window(
    phrases: list[dict], max_seconds: float, min_seconds: float = 3.0
) -> tuple[float, float, str] | None:
    """Longest run of consecutive phrases that fits in `max_seconds` (ties → earliest).
    Returns (start, end, joined text) or None if nothing is at least `min_seconds` long."""
    best: tuple[float, float, str] | None = None
    for i in range(len(phrases)):
        for j in range(i, len(phrases)):
            start, end = phrases[i]["start"], phrases[j]["end"]
            span = end - start
            if span > max_seconds:
                break
            if span >= min_seconds and (best is None or span > best[1] - best[0]):
                text = " ".join(p["text"].strip() for p in phrases[i : j + 1])
                best = (start, end, text)
    return best
