"""Sample quality checker: duration, noise, clipping, silence ratio, rough multi-speaker
hint. Produces a Good / Okay / Poor rating with human-readable reasons."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

import numpy as np

from app.services.analysis import energy_vad, frame_rms, to_db

Rating = Literal["good", "okay", "poor"]
_ORDER = {"good": 0, "okay": 1, "poor": 2}

RECOMMENDED_MIN_SPEECH = 15.0
RECOMMENDED_MAX_SPEECH = 60.0


@dataclass
class Issue:
    severity: Literal["okay", "poor"]  # the rating this issue caps the sample at
    code: str
    message: str


@dataclass
class QualityReport:
    rating: Rating
    score: int  # 0-100, for the animated meter
    duration: float
    speech_seconds: float
    silence_ratio: float
    noise_floor_db: float
    snr_db: float | None  # None = no pauses to measure noise against
    clipping_ratio: float
    peak_db: float
    pitch_spread: float | None  # semitones IQR of voiced f0; high = maybe several speakers
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _worst(ratings: list[Rating]) -> Rating:
    return max(ratings, key=lambda r: _ORDER[r]) if ratings else "good"


def _pitch_spread(audio: np.ndarray, sr: int, mask: np.ndarray, frame_s: float) -> float | None:
    """IQR (in semitones) of f0 over speech frames. One speaker is usually < ~5 st IQR."""
    try:
        import librosa
    except ImportError:  # pragma: no cover - librosa ships with coqui-tts
        return None
    speech_idx = np.flatnonzero(mask)
    if len(speech_idx) * frame_s < 2.0:
        return None
    hop = int(sr * frame_s)
    # Limit to ~40 s of speech to keep this fast.
    keep = speech_idx[: int(40 / frame_s)]
    voiced = np.concatenate([audio[i * hop : (i + 1) * hop] for i in keep])
    f0 = librosa.yin(voiced, fmin=65, fmax=500, sr=sr, frame_length=2048)
    f0 = f0[(f0 > 66) & (f0 < 495)]
    if len(f0) < 20:
        return None
    st = 12 * np.log2(f0 / np.median(f0))
    q75, q25 = np.percentile(st, [75, 25])
    return round(float(q75 - q25), 2)


def analyze(audio: np.ndarray, sr: int, *, check_pitch: bool = True) -> QualityReport:
    duration = len(audio) / sr if sr else 0.0
    if duration == 0:
        return QualityReport(
            "poor",
            0,
            0,
            0,
            1,
            -100,
            0,
            0,
            -100,
            None,
            [Issue("poor", "empty", "The file contains no audio.")],
        )

    vad = energy_vad(audio, sr)
    speech_s = float(vad.speech_mask.sum() * vad.frame_seconds)
    silence_ratio = 1 - speech_s / duration
    rms_db = to_db(frame_rms(audio, sr))
    speech_db = (
        float(np.median(rms_db[vad.speech_mask])) if vad.speech_mask.any() else vad.speech_level_db
    )
    # Without real pauses the "floor" is just quiet speech and SNR can't be measured.
    measurable = (vad.speech_level_db - vad.noise_floor_db) >= 12 and silence_ratio >= 0.02
    snr = speech_db - vad.noise_floor_db if measurable else None
    peak = float(np.max(np.abs(audio)))
    clipping = float(np.mean(np.abs(audio) >= 0.999))
    spread = _pitch_spread(audio, sr, vad.speech_mask, vad.frame_seconds) if check_pitch else None

    issues: list[Issue] = []
    if speech_s < 3 and (vad.speech_level_db - vad.noise_floor_db) < 12 and peak > 0.01:
        issues.append(
            Issue(
                "poor",
                "noisy",
                "Speech can't be separated from the background — the recording is "
                "too noisy, or there's no speech in it.",
            )
        )
    elif speech_s < 3:
        issues.append(
            Issue(
                "poor",
                "too_little_speech",
                f"Only {speech_s:.1f}s of speech detected — aim for 15–60 seconds.",
            )
        )
    elif speech_s < 8:
        issues.append(
            Issue(
                "okay",
                "short",
                f"{speech_s:.0f}s of speech. Works, but 15–60 seconds clones better.",
            )
        )
    if snr is None:
        pass  # no silence to measure noise against; don't guess
    elif snr < 12:
        issues.append(
            Issue("poor", "noisy", f"Very noisy: speech is only {snr:.0f} dB above the background.")
        )
    elif snr < 22:
        issues.append(
            Issue(
                "okay",
                "some_noise",
                f"Some background noise ({snr:.0f} dB signal-to-noise). A quieter room helps.",
            )
        )
    if clipping > 0.005:
        issues.append(
            Issue(
                "poor",
                "clipping",
                f"{clipping:.1%} of samples are clipped (distorted). Record a bit quieter.",
            )
        )
    elif clipping > 0.0005:
        issues.append(Issue("okay", "some_clipping", "A few clipped peaks — slight distortion."))
    if speech_db < -45:
        issues.append(Issue("okay", "quiet", "The recording is very quiet; it will be normalised."))
    if silence_ratio > 0.6 and speech_s >= 3:
        issues.append(
            Issue(
                "okay",
                "mostly_silence",
                f"{silence_ratio:.0%} of the file is silence; it will be trimmed.",
            )
        )
    if spread is not None and spread > 6.5:
        issues.append(
            Issue(
                "okay",
                "multiple_speakers",
                "Pitch varies a lot — there may be more than one speaker. "
                "Use clips with only this person talking.",
            )
        )

    rating = _worst([i.severity for i in issues])
    score = 100
    score -= max(0, 15 - speech_s) * 2.5
    score -= max(0, 28 - snr) * 2 if snr is not None else 0
    score -= min(30, clipping * 4000)
    score -= 8 if spread is not None and spread > 6.5 else 0
    score = int(np.clip(score, 0, 100))
    # Keep the number consistent with the label.
    score = {"good": max(score, 70), "okay": int(np.clip(score, 40, 69)), "poor": min(score, 39)}[
        rating
    ]

    return QualityReport(
        rating,
        score,
        round(duration, 2),
        round(speech_s, 2),
        round(silence_ratio, 3),
        round(vad.noise_floor_db, 1),
        round(snr, 1) if snr is not None else None,
        round(clipping, 5),
        round(float(to_db(peak)), 1),
        spread,
        issues,
    )


def summarize(reports: list[QualityReport]) -> dict[str, Any]:
    """Combine per-sample reports into a voice-level verdict."""
    total_speech = sum(r.speech_seconds for r in reports)
    issues: list[Issue] = []
    if total_speech < RECOMMENDED_MIN_SPEECH:
        sev: Literal["okay", "poor"] = "poor" if total_speech < 6 else "okay"
        issues.append(
            Issue(
                sev,
                "total_short",
                f"{total_speech:.0f}s of speech in total; 15–60 seconds is recommended.",
            )
        )
    elif total_speech > RECOMMENDED_MAX_SPEECH * 3:
        issues.append(
            Issue(
                "okay",
                "total_long",
                "Lots of audio — only the cleanest ~60 seconds are used for cloning.",
            )
        )
    sample_ratings = [r.rating for r in reports]
    good = [r for r in reports if r.rating != "poor"]
    # Carry the reasons up from the clips, so a voice-level rating always says why.
    seen = {i.code for i in issues}
    usable = good or reports
    for r in usable:
        for i in r.issues:
            if i.code not in seen:
                seen.add(i.code)
                n = sum(any(x.code == i.code for x in rr.issues) for rr in usable)
                prefix = (
                    ""
                    if len(reports) == 1
                    else ("All clips: " if n == len(usable) else f"{n} of {len(reports)} clips: ")
                )
                issues.append(Issue(i.severity, i.code, prefix + i.message))
    if len(good) < len(reports):
        issues.append(
            Issue(
                "okay",
                "poor_clips_skipped",
                f"{len(reports) - len(good)} clip(s) rated Poor and left out of the voiceprint.",
            )
        )
    # A voice is as good as its usable samples, not dragged down by one bad clip.
    base = _worst([r.rating for r in good]) if good else "poor"
    voice_level = [i.severity for i in issues if i.code in ("total_short", "total_long")]
    rating = _worst([base, *voice_level])
    scores = [r.score for r in (good or reports)]
    score = int(np.mean(scores)) if scores else 0
    score = {"good": max(score, 70), "okay": int(np.clip(score, 40, 69)), "poor": min(score, 39)}[
        rating
    ]
    return {
        "rating": rating,
        "score": score,
        "speech_seconds": round(total_speech, 1),
        "sample_ratings": sample_ratings,
        "issues": [asdict(i) for i in issues],
    }


def apply_speaker_check(
    report: QualityReport, match: float | None, outlier_below: float
) -> QualityReport:
    """Replace the pitch-spread guess with the speaker model's verdict.

    The pitch heuristic flags lively voices (children especially) as "maybe several
    speakers": on a real 13-clip voice it warned on 5 clips while the speaker model matched
    all of them at 0.81-0.92. When a match score exists, it decides instead."""
    if match is None:
        return report
    issues = [i for i in report.issues if i.code != "multiple_speakers"]
    if match < outlier_below:
        issues.append(
            Issue(
                "okay",
                "different_speaker",
                "This clip sounds like a different person, so it isn't used for the voiceprint.",
            )
        )
    rating = _worst([i.severity for i in issues])
    removed_penalty = any(i.code == "multiple_speakers" for i in report.issues)
    score = report.score + (8 if removed_penalty else 0)
    score = {"good": max(score, 70), "okay": int(np.clip(score, 40, 69)), "poor": min(score, 39)}[
        rating
    ]
    return replace(report, rating=rating, score=int(score), issues=issues)
