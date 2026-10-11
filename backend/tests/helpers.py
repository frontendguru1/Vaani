import io

import numpy as np
import soundfile as sf

SR = 22_050


def speech_wav_bytes(seconds: float = 6.0, f0: float = 150.0, lead: float = 0.5) -> bytes:
    t = np.arange(int(seconds * SR)) / SR
    sig = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6)) / 2.3
    sig = 0.3 * sig * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    pad = np.zeros(int(lead * SR))
    buf = io.BytesIO()
    sf.write(buf, np.concatenate([pad, sig, pad]).astype(np.float32), SR, format="WAV")
    return buf.getvalue()
