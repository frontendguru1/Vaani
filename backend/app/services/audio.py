"""Low-level audio file helpers (ffmpeg + soundfile). No business rules here."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


class AudioError(RuntimeError):
    pass


FFMPEG_TIMEOUT = 180  # seconds; a crafted file must not stall a worker thread forever
# Containers we accept. ffmpeg sniffs the format from the content, not the extension, so a
# ".mp3" could really be an HLS/concat playlist that makes ffmpeg open other files or URLs.
ALLOWED_FORMATS = {
    "wav",
    "mp3",
    "ogg",
    "flac",
    "aac",
    "aiff",
    "webm",
    "matroska",
    "mov",
    "mp4",
    "m4a",
    "3gp",
    "3g2",
    "mj2",
    "opus",
    "caf",
}
_INPUT_FLAGS = ["-protocol_whitelist", "file,pipe"]


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise AudioError("ffprobe not found — install ffmpeg with `brew install ffmpeg`")
    return path


def check_format(src: Path) -> str:
    """Refuse anything that isn't a plain audio/video container (playlists, images, …)."""
    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        *_INPUT_FLAGS,
        "-show_entries",
        "format=format_name",
        "-of",
        "default=nw=1:nk=1",
        str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"{src.name}: took too long to inspect") from exc
    names = set(proc.stdout.strip().split(","))
    if proc.returncode != 0 or not names & ALLOWED_FORMATS:
        raise AudioError(f"{src.name} isn't an audio file Vaani can read.")
    return proc.stdout.strip()


def run_ffmpeg(cmd: list[str], what: str) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"{what} took longer than {FFMPEG_TIMEOUT}s and was stopped") from exc
    if proc.returncode != 0:
        raise AudioError(f"{what} failed: {proc.stderr.strip()[:300]}")


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
    check_format(src)
    cmd = [ffmpeg_bin(), "-nostdin", "-y", "-loglevel", "error", *_INPUT_FLAGS, "-i", str(src)]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)]
    run_ffmpeg(cmd, f"Decoding {src.name}")
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
    run_ffmpeg(cmd, "MP3 export")
    return mp3
