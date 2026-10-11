"""Preprocessing pipeline for one uploaded/recorded sample.

1. decode to mono WAV at the target rate (kept as `raw` only long enough to analyse)
2. quality analysis on the raw decode (so clipping/noise reflect the real recording)
3. clean: high-pass (rumble), optional denoise (ffmpeg afftdn), trim leading/trailing
   silence, EBU R128 loudness normalisation
4. split long recordings into clean speech segments (<= MAX_SEGMENT seconds)

Uses only ffmpeg's built-in filters — no extra ML dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services import audio
from app.services.analysis import speech_segments
from app.services.quality import QualityReport, analyze

TARGET_SR = 24_000
MAX_SEGMENT = 14.0
LOUDNESS_LUFS = -20

_TRIM = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.15"


@dataclass
class Segment:
    path: Path
    start: float
    end: float

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class ProcessedSample:
    processed: Path
    duration: float
    quality: QualityReport
    segments: list[Segment]


def clean_filters(denoise: bool) -> str:
    chain = ["highpass=f=70"]
    if denoise:
        chain.append("afftdn=nr=12:nf=-40")
    # Trim the start, reverse, trim the (old) end, reverse back.
    chain += [_TRIM, "areverse", _TRIM, "areverse"]
    chain.append(f"loudnorm=I={LOUDNESS_LUFS}:TP=-1.5:LRA=11")
    return ",".join(chain)


def _ffmpeg_clean(src: Path, dst: Path, sr: int, denoise: bool) -> None:
    cmd = [
        audio.ffmpeg_bin(),
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(src),
        "-af",
        clean_filters(denoise),
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    audio.run_ffmpeg(cmd, "Cleaning")


def process_sample(
    original: Path, out_dir: Path, stem: str, *, denoise: bool = False, sr: int = TARGET_SR
) -> ProcessedSample:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f".{stem}.raw.wav"
    try:
        audio.convert_to_wav(original, raw, sr)
        raw_audio, _ = audio.read_mono(raw)
        report = analyze(raw_audio, sr)
    finally:
        raw.unlink(missing_ok=True)

    processed = out_dir / f"{stem}.wav"
    _ffmpeg_clean(original, processed, sr, denoise)
    clean, _ = audio.read_mono(processed)
    duration = len(clean) / sr
    if duration < 0.3:
        # Trimming ate everything: the clip is silence. Keep the file; the report says why.
        return ProcessedSample(processed, round(duration, 3), report, [])

    segments: list[Segment] = []
    if duration <= MAX_SEGMENT:
        segments.append(Segment(processed, 0.0, round(duration, 3)))
    else:
        for i, (s, e) in enumerate(speech_segments(clean, sr, max_segment=MAX_SEGMENT)):
            seg_path = out_dir / f"{stem}_seg{i:02d}.wav"
            audio.write_wav(seg_path, clean[int(s * sr) : int(e * sr)], sr)
            segments.append(Segment(seg_path, s, e))
    return ProcessedSample(processed, round(duration, 3), report, segments)
