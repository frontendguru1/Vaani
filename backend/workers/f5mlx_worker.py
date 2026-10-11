"""F5-TTS MLX worker. Mirrors f5_tts_mlx.generate.generate() but keeps one model loaded.
(We don't import f5_tts_mlx.generate: it pulls in sounddevice/PortAudio for playback.)"""

import importlib.metadata
import time

import mlx.core as mx
import numpy as np
import soundfile as sf
from _protocol import serve
from f5_tts_mlx.cfm import F5TTS
from f5_tts_mlx.utils import convert_char_to_pinyin

# Compat shim: f5-tts-mlx 0.2.6 calls mx.random.normal((channels, dur)) where `dur` is an
# mx.array scalar (from iterating an array). mlx >= 0.32 only accepts ints in shapes.
_mx_normal = mx.random.normal


def _normal_int_shape(shape=(), *args, **kwargs):
    if isinstance(shape, (tuple, list)):
        shape = tuple(int(s) for s in shape)
    return _mx_normal(shape, *args, **kwargs)


mx.random.normal = _normal_int_shape

SAMPLE_RATE = 24_000
TARGET_RMS = 0.1  # same as f5_tts_mlx.generate
MODEL = "lucasnewman/f5-tts-mlx"

model = None


def load(req):
    global model
    if model is None:
        q = req.get("options", {}).get("quantization_bits")
        model = F5TTS.from_pretrained(MODEL, quantization_bits=q)
    return {
        "device": "mlx-gpu",
        "version": f"f5-tts-mlx {importlib.metadata.version('f5-tts-mlx')}",
    }


def synthesize(req):
    opts = req.get("options", {})
    ref, sr = sf.read(req["ref_audio"], dtype="float32")
    if sr != SAMPLE_RATE:
        raise ValueError(f"reference must be {SAMPLE_RATE} Hz, got {sr}")
    if ref.ndim > 1:
        ref = ref.mean(axis=1)
    ref = mx.array(ref)
    rms = mx.sqrt(mx.mean(mx.square(ref)))
    if rms < TARGET_RMS:
        ref = ref * TARGET_RMS / rms
    text = convert_char_to_pinyin([req["ref_text"] + " " + req["text"]])
    t0 = time.perf_counter()
    wave, _ = model.sample(
        mx.expand_dims(ref, axis=0),
        text=text,
        duration=None,
        steps=int(opts.get("steps", 8)),
        method="rk4",
        speed=float(opts.get("speed", 1.0)),
        cfg_strength=2.0,
        sway_sampling_coef=-1.0,
        seed=opts.get("seed"),
    )
    wave = wave[ref.shape[0] :]
    mx.eval(wave)
    out = np.array(wave)
    sf.write(req["out"], out, SAMPLE_RATE)
    return {
        "sample_rate": SAMPLE_RATE,
        "seconds": len(out) / SAMPLE_RATE,
        "compute": time.perf_counter() - t0,
    }


if __name__ == "__main__":
    serve({"load": load, "synthesize": synthesize})
