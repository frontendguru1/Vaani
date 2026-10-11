"""Join synthesized chunks into one track with natural pauses and click-free edges."""

from __future__ import annotations

import numpy as np

from app.services.analysis import frame_rms, to_db


def trim_silence(
    audio: np.ndarray, sr: int, threshold_db: float = -45.0, keep_ms: int = 40
) -> np.ndarray:
    """Remove leading/trailing near-silence so the configured pause is the actual pause."""
    if len(audio) == 0:
        return audio
    frame_ms = 10
    db = to_db(frame_rms(audio, sr, frame_ms))
    loud = np.flatnonzero(db > threshold_db)
    if len(loud) == 0:
        return audio[:0]
    n = int(sr * frame_ms / 1000)
    keep = int(sr * keep_ms / 1000)
    start = max(0, loud[0] * n - keep)
    end = min(len(audio), (loud[-1] + 1) * n + keep)
    return audio[start:end]


def fade(audio: np.ndarray, sr: int, ms: int = 8) -> np.ndarray:
    n = min(len(audio) // 2, int(sr * ms / 1000))
    if n <= 1:
        return audio
    out = audio.astype(np.float32, copy=True)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def stitch(
    chunks: list[np.ndarray],
    pauses_ms: list[int],
    sr: int,
    *,
    trim: bool = True,
    lead_ms: int = 0,
) -> tuple[np.ndarray, list[float]]:
    """Return (audio, offsets) where offsets[i] is where chunk i starts, in seconds.
    `lead_ms` of silence goes before the first chunk (a [pause] at the start of a script)."""
    if len(chunks) != len(pauses_ms):
        raise ValueError("need one pause per chunk")
    parts: list[np.ndarray] = []
    offsets: list[float] = []
    cursor = 0
    if lead_ms > 0:
        parts.append(np.zeros(int(sr * lead_ms / 1000), dtype=np.float32))
        cursor = len(parts[0])
    for chunk, pause in zip(chunks, pauses_ms, strict=True):
        c = trim_silence(chunk, sr) if trim else chunk
        c = fade(np.asarray(c, dtype=np.float32), sr)
        offsets.append(round(cursor / sr, 3))
        parts.append(c)
        cursor += len(c)
        if pause > 0:
            gap = np.zeros(int(sr * pause / 1000), dtype=np.float32)
            parts.append(gap)
            cursor += len(gap)
    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return audio, offsets
