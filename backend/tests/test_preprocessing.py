import shutil
import subprocess

import numpy as np
import pytest

from app.services import audio
from app.services.preprocessing import TARGET_SR, process_sample

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

SR = 44_100


def speechy(seconds, f0=150.0, amp=0.05):
    t = np.arange(int(seconds * SR)) / SR
    sig = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6)) / 2.3
    return (amp * sig * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def quiet(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def write_stereo_mp3(path, mono):
    wav = path.with_suffix(".src.wav")
    audio.write_wav(wav, mono, SR)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "2", str(path)], check=True
    )
    return path


def test_converts_trims_and_normalises(tmp_path):
    src = write_stereo_mp3(
        tmp_path / "in.mp3", np.concatenate([quiet(1.5), speechy(6), quiet(2.0)])
    )
    res = process_sample(src, tmp_path / "out", "s1")
    info = audio.sf.info(str(res.processed))
    assert info.channels == 1 and info.samplerate == TARGET_SR
    # Leading/trailing silence trimmed (allowing for mp3 padding and filter tails).
    assert 5.5 < res.duration < 7.0
    clean, _ = audio.read_mono(res.processed)
    rms_db = 20 * np.log10(np.sqrt(np.mean(clean**2)))
    assert -26 < rms_db < -14  # loudness-normalised up from a quiet (-30 dB-ish) input
    assert len(res.segments) == 1 and res.segments[0].path == res.processed
    assert not list((tmp_path / "out").glob(".*raw.wav"))  # temp decode removed


def test_long_recording_is_split_into_segments(tmp_path):
    parts = []
    for _ in range(4):
        parts += [speechy(8), quiet(0.8)]
    src = tmp_path / "long.wav"
    audio.write_wav(src, np.concatenate(parts), SR)
    res = process_sample(src, tmp_path / "out", "long")
    assert res.duration > 30
    assert len(res.segments) >= 3
    for seg in res.segments:
        assert seg.path.is_file()
        assert seg.duration <= 14.5


def test_quality_reflects_the_raw_recording(tmp_path):
    clipped = np.clip(speechy(20, amp=3.0), -1, 1)
    src = tmp_path / "clip.wav"
    audio.write_wav(src, clipped, SR)
    res = process_sample(src, tmp_path / "out", "c")
    assert any(i.code == "clipping" for i in res.quality.issues)


def test_denoise_option_runs(tmp_path):
    rng = np.random.default_rng(1)
    noisy = speechy(6, amp=0.2) + 0.01 * rng.standard_normal(6 * SR).astype(np.float32)
    src = tmp_path / "n.wav"
    audio.write_wav(src, noisy, SR)
    res = process_sample(src, tmp_path / "out", "n", denoise=True)
    assert res.processed.is_file() and res.duration > 5


def test_undecodable_file_raises(tmp_path):
    bad = tmp_path / "bad.m4a"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(audio.AudioError):
        process_sample(bad, tmp_path / "out", "bad")
