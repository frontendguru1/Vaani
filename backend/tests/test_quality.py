import numpy as np
import pytest

from app.services.analysis import energy_vad, speech_segments
from app.services.quality import analyze, summarize

SR = 16_000
rng = np.random.default_rng(0)


def tone_speech(seconds: float, f0: float = 140.0, amp: float = 0.3) -> np.ndarray:
    """Speech-like signal: harmonic tone with syllable-rate amplitude modulation."""
    t = np.arange(int(seconds * SR)) / SR
    sig = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)
    return (amp * sig / 2.3 * envelope).astype(np.float32)


def silence(seconds: float, noise: float = 0.0005) -> np.ndarray:
    return (noise * rng.standard_normal(int(seconds * SR))).astype(np.float32)


def test_clean_long_speech_is_good():
    audio = np.concatenate([silence(0.5), tone_speech(20), silence(0.5)])
    audio += silence(len(audio) / SR)
    r = analyze(audio, SR, check_pitch=False)
    assert r.rating == "good", r.issues
    assert 19 < r.speech_seconds < 21.5
    assert r.snr_db > 30
    assert r.score >= 70


def test_too_little_speech_is_poor():
    audio = np.concatenate([silence(3), tone_speech(1.5), silence(3)])
    r = analyze(audio, SR, check_pitch=False)
    assert r.rating == "poor"
    assert any(i.code == "too_little_speech" for i in r.issues)
    assert r.score < 40


def test_moderate_noise_is_okay_with_reason():
    speech = np.concatenate([silence(1), tone_speech(20, amp=0.3), silence(2)])
    noisy = speech + 0.006 * rng.standard_normal(len(speech)).astype(np.float32)
    r = analyze(noisy, SR, check_pitch=False)
    assert r.snr_db is not None and 12 <= r.snr_db < 22, r.snr_db
    assert [i.code for i in r.issues] == ["some_noise"]
    assert r.rating == "okay"


def test_speech_buried_in_noise_is_poor_and_says_why():
    speech = np.concatenate([tone_speech(10, amp=0.1), silence(2)])
    noisy = speech + 0.03 * rng.standard_normal(len(speech)).astype(np.float32)
    r = analyze(noisy, SR, check_pitch=False)
    assert r.rating == "poor"
    assert r.issues[0].code == "noisy"


def test_clipping_is_detected():
    audio = np.clip(tone_speech(20, amp=2.0), -1, 1)
    r = analyze(audio, SR, check_pitch=False)
    assert any(i.code == "clipping" for i in r.issues)
    assert r.rating == "poor"


def test_mostly_silence_is_reported():
    audio = np.concatenate([silence(20), tone_speech(8), silence(20)])
    r = analyze(audio, SR, check_pitch=False)
    assert r.silence_ratio > 0.6
    assert any(i.code == "mostly_silence" for i in r.issues)


def test_two_different_pitches_hint_multiple_speakers():
    pytest.importorskip("librosa")
    audio = np.concatenate([tone_speech(8, f0=100), silence(0.3), tone_speech(8, f0=240)])
    r = analyze(audio, SR)
    assert r.pitch_spread is not None and r.pitch_spread > 6.5
    assert any(i.code == "multiple_speakers" for i in r.issues)


def test_single_speaker_has_low_pitch_spread():
    pytest.importorskip("librosa")
    r = analyze(tone_speech(12, f0=150), SR)
    assert r.pitch_spread is not None and r.pitch_spread < 3


def test_empty_audio():
    r = analyze(np.zeros(0, dtype=np.float32), SR)
    assert r.rating == "poor" and r.issues[0].code == "empty"


def test_vad_finds_speech_region():
    audio = np.concatenate([silence(1), tone_speech(2), silence(1)])
    vad = energy_vad(audio, SR)
    speech_frames = np.flatnonzero(vad.speech_mask)
    start, end = speech_frames[0] * vad.frame_seconds, speech_frames[-1] * vad.frame_seconds
    assert 0.85 < start < 1.15 and 2.8 < end < 3.15


def test_segments_split_at_pauses_and_respect_max_length():
    audio = np.concatenate(
        [tone_speech(4), silence(1.0), tone_speech(5), silence(1.0), tone_speech(30)]
    )
    segs = speech_segments(audio, SR, max_segment=12)
    assert len(segs) >= 4
    assert all(e - s <= 12 + 0.3 for s, e in segs)  # + padding
    assert segs[0][0] < 0.2


def test_summary_ignores_one_bad_clip_but_needs_enough_total_speech():
    good = analyze(tone_speech(20) + silence(20), SR, check_pitch=False)
    bad = analyze(np.concatenate([silence(3), tone_speech(1), silence(3)]), SR, check_pitch=False)
    s = summarize([good, bad])
    assert s["rating"] == "good"
    assert s["sample_ratings"] == ["good", "poor"]

    short = analyze(tone_speech(9) + silence(9), SR, check_pitch=False)
    s2 = summarize([short])
    assert s2["rating"] == "okay"
    assert s2["issues"][0]["code"] == "total_short"
