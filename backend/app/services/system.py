"""Environment probes: ffmpeg, compute device. Pure functions, no HTTP."""

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class FfmpegInfo:
    available: bool
    version: str | None


@dataclass(frozen=True)
class DeviceInfo:
    torch_installed: bool
    torch_version: str | None
    mps_available: bool
    preferred: str  # what engines will try first: "mps" | "cpu"


def ffmpeg_info() -> FfmpegInfo:
    path = shutil.which("ffmpeg")
    if not path:
        return FfmpegInfo(False, None)
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return FfmpegInfo(False, None)
    first = out.splitlines()[0] if out else ""
    # "ffmpeg version 9.0.2 Copyright ..." -> "9.0.2"
    parts = first.split()
    return FfmpegInfo(True, parts[2] if len(parts) > 2 else first)


def device_info(preference: str = "auto") -> DeviceInfo:
    if importlib.util.find_spec("torch") is None:
        return DeviceInfo(False, None, False, "cpu")
    import torch

    mps = bool(torch.backends.mps.is_available())
    if preference == "cpu":
        preferred = "cpu"
    else:
        preferred = "mps" if mps else "cpu"
    return DeviceInfo(True, torch.__version__, mps, preferred)
