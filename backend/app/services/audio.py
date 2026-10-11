"""Low-level audio file helpers (ffmpeg + soundfile). No business rules here."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


class AudioError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AudioError("ffmpeg not found — install it with `brew install ffmpeg`")
    return path


def convert_to_wav(
    src: Path, dst: Path, sample_rate: int, *, max_seconds: float | None = None
) -> Path:
    """Decode anything ffmpeg understands into mono 16-bit PCM WAV at `sample_rate`."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_bin(), "-nostdin", "-y", "-loglevel", "error", "-i", str(src)]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg could not decode {src.name}: {proc.stderr.strip()[:300]}")
    return dst


def duration_seconds(path: Path) -> float:
    info = sf.info(str(path))
    return info.frames / float(info.samplerate)


def read_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return audio.mean(axis=1), sr


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(audio, -1.0, 1.0).astype(np.float32), sample_rate, subtype="PCM_16")
    return path


def export_mp3(wav: Path, mp3: Path, bitrate: str = "192k") -> Path:
    cmd = [
        ffmpeg_bin(),
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(wav),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(mp3),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"MP3 export failed: {proc.stderr.strip()[:300]}")
    return mp3
