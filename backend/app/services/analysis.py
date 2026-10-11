"""Pure-numpy audio analysis: frame energy, a simple energy VAD and speech segmentation.
Deliberately dependency-light so it's fast and unit-testable with synthetic signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FRAME_MS = 30
EPS = 1e-10


def frame_rms(audio: np.ndarray, sr: int, frame_ms: int = FRAME_MS) -> np.ndarray:
    n = max(1, int(sr * frame_ms / 1000))
    frames = len(audio) // n
    if frames == 0:
        return np.array([float(np.sqrt(np.mean(audio**2) + EPS))]) if len(audio) else np.zeros(0)
    x = audio[: frames * n].reshape(frames, n)
    return np.sqrt(np.mean(x**2, axis=1) + EPS)


def to_db(x: np.ndarray | float) -> np.ndarray | float:
    return 20 * np.log10(np.maximum(x, EPS))


@dataclass(frozen=True)
class VadResult:
    speech_mask: np.ndarray  # per frame
    noise_floor_db: float
    speech_level_db: float
    threshold_db: float
    frame_seconds: float


def energy_vad(audio: np.ndarray, sr: int, frame_ms: int = FRAME_MS) -> VadResult:
    """Adaptive threshold between the noise floor (3rd pct: the quietest gaps between words)
    and the speech level (95th pct)."""
    db = to_db(frame_rms(audio, sr, frame_ms))
    if len(db) == 0:
        return VadResult(np.zeros(0, bool), -100.0, -100.0, -100.0, frame_ms / 1000)
    floor = float(np.percentile(db, 3))
    level = float(np.percentile(db, 95))
    # Speech must be clearly above the floor and not absurdly quiet in absolute terms.
    threshold = max(floor + 0.35 * (level - floor), floor + 6.0, -55.0)
    mask = db > threshold
    # Hangover smoothing: bridge gaps < 150 ms, drop blips < 90 ms.
    mask = _close_gaps(mask, max_gap=int(150 / frame_ms))
    mask = _drop_short(mask, min_len=int(90 / frame_ms) or 1)
    return VadResult(mask, floor, level, threshold, frame_ms / 1000)


def _runs(mask: np.ndarray) -> list[tuple[int, int, bool]]:
    runs, start = [], 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            runs.append((start, i, bool(mask[start])))
            start = i
    return runs


def _close_gaps(mask: np.ndarray, max_gap: int) -> np.ndarray:
    out = mask.copy()
    runs = _runs(mask)
    for k, (s, e, v) in enumerate(runs):
        if not v and 0 < k < len(runs) - 1 and e - s <= max_gap:
            out[s:e] = True
    return out


def _drop_short(mask: np.ndarray, min_len: int) -> np.ndarray:
    out = mask.copy()
    for s, e, v in _runs(mask):
        if v and e - s < min_len:
            out[s:e] = False
    return out


def speech_segments(
    audio: np.ndarray,
    sr: int,
    *,
    min_silence: float = 0.45,
    pad: float = 0.12,
    min_segment: float = 1.0,
    max_segment: float = 14.0,
) -> list[tuple[float, float]]:
    """Return (start, end) seconds of speech regions, split at pauses >= min_silence and
    packed so each segment is at most max_segment long."""
    vad = energy_vad(audio, sr)
    fs = vad.frame_seconds
    mask = _close_gaps(vad.speech_mask, max_gap=int(min_silence / fs) - 1)
    regions = [(s * fs, e * fs) for s, e, v in _runs(mask) if v]
    total = len(audio) / sr

    packed: list[tuple[float, float]] = []
    for s, e in regions:
        # Split overly long regions evenly (no natural pause to cut at).
        n = int(np.ceil((e - s) / max_segment)) or 1
        step = (e - s) / n
        for i in range(n):
            a, b = s + i * step, s + (i + 1) * step
            if packed and b - packed[-1][0] <= max_segment and a - packed[-1][1] < 1.0:
                packed[-1] = (packed[-1][0], b)  # merge close neighbours
            else:
                packed.append((a, b))
    padded = [(max(0.0, s - pad), min(total, e + pad)) for s, e in packed]
    return [(round(s, 3), round(e, 3)) for s, e in padded if e - s >= min_segment]
