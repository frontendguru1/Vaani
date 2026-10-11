"""IndicF5 worker (AI4Bharat). Loaded through transformers AutoModel with the model's
own remote code, exactly as the Hugging Face model card shows."""

import importlib.metadata
import os
import time

import numpy as np
import soundfile as sf
from _protocol import serve

REPO = "ai4bharat/IndicF5"
SAMPLE_RATE = 24_000
model = None
device = "cpu"


def load(_req):
    global model, device
    if model is None:
        import torch
        from transformers import AutoModel

        model = AutoModel.from_pretrained(REPO, trust_remote_code=True)
        want = os.environ.get("VAANI_DEVICE", "auto")
        if want != "cpu" and torch.backends.mps.is_available():
            try:
                model = model.to("mps")
                device = "mps"
            except Exception as exc:  # noqa: BLE001
                print(f"IndicF5: MPS move failed ({exc}); using CPU")
                device = "cpu"
    return {
        "device": device,
        "version": f"IndicF5 (transformers {importlib.metadata.version('transformers')})",
    }


def synthesize(req):
    t0 = time.perf_counter()
    audio = model(req["text"], ref_audio_path=req["ref_audio"], ref_text=req["ref_text"])
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    audio = audio.astype(np.float32)
    sf.write(req["out"], audio, SAMPLE_RATE)
    return {
        "sample_rate": SAMPLE_RATE,
        "seconds": len(audio) / SAMPLE_RATE,
        "compute": time.perf_counter() - t0,
    }


if __name__ == "__main__":
    serve({"load": load, "synthesize": synthesize})
