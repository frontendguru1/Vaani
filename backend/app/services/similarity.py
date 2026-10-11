"""Speaker similarity: "does the generated audio sound like the person?", as a number.

Uses SpeechBrain's ECAPA-TDNN speaker-verification model (speechbrain/spkrec-ecapa-voxceleb,
Apache-2.0, ~89 MB, downloaded once into data/models/speechbrain). It is independent of the
TTS engines, so it can judge them. Embeddings are L2-normalised; similarity = cosine.

Calibration (2026-10-11, macOS test voices): two clips of the same voice 0.89-0.91;
different voices -0.02-0.38. Cloned speech: XTTS ≈ 0.54-0.56, F5-TTS ≈ 0.84.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from app.config import get_settings

log = logging.getLogger("vaani.similarity")

SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
SR = 16_000
OUTLIER_BELOW = 0.45  # a clip this far from the voice's centroid is probably someone else
_load_lock = threading.Lock()  # guards loading the model
_run_lock = threading.Lock()  # one embedding at a time (separate lock: no self-deadlock)
_encoder = None


def model_dir() -> Path:
    return get_settings().models_dir / "speechbrain" / "spkrec-ecapa-voxceleb"


def _enc():
    global _encoder
    with _load_lock:
        if _encoder is None:
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import LocalStrategy

            # COPY_SKIP_CACHE: real files in data/models (not symlinks into ~/.cache), so the
            # model lives with Vaani's other models and works offline from there.
            local = (model_dir() / "embedding_model.ckpt").is_file() and not (
                model_dir() / "embedding_model.ckpt"
            ).is_symlink()
            _encoder = EncoderClassifier.from_hparams(
                source=str(model_dir()) if local else SOURCE,
                savedir=str(model_dir()),
                run_opts={"device": "cpu"},
                local_strategy=LocalStrategy.COPY_SKIP_CACHE,
            )
    return _encoder


def embed_array(audio: np.ndarray, sr: int) -> np.ndarray:
    import librosa
    import torch

    y = audio.astype(np.float32)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    enc = _enc()  # load outside the run lock
    with _run_lock, torch.inference_mode():
        e = enc.encode_batch(torch.from_numpy(y).unsqueeze(0)).squeeze().numpy()
    return e / (np.linalg.norm(e) + 1e-9)


def embed_file(path: Path) -> np.ndarray:
    import librosa

    y, _ = librosa.load(str(path), sr=SR, mono=True)
    return embed_array(y, SR)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


def robust_centroid(embs: list[np.ndarray]) -> tuple[np.ndarray, list[float]]:
    """Centroid of the majority speaker, robust to a minority of other voices.

    Start from the medoid (the clip most similar to all the others), keep the clips close to
    it, and average those. A plain mean doesn't work: with 3 clips, one intruder pulls the
    mean far enough towards itself to survive the cut-off.
    Returns (centroid, each clip's similarity to it)."""
    if not embs:
        raise ValueError("no embeddings")
    m = np.stack([e / (np.linalg.norm(e) + 1e-9) for e in embs])
    sims = m @ m.T
    medoid = int(np.argmax(sims.sum(axis=1)))
    keep = [i for i in range(len(embs)) if sims[medoid, i] >= OUTLIER_BELOW] or [medoid]
    c = m[keep].mean(axis=0)
    c = c / (np.linalg.norm(c) + 1e-9)
    return c, [round(float(np.dot(e, c)), 3) for e in m]


def label(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.75:
        return "very close"
    if score >= 0.6:
        return "close"
    if score >= 0.45:
        return "somewhat similar"
    return "different"
