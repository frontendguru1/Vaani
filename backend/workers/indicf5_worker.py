"""IndicF5 worker (AI4Bharat). Loaded through transformers AutoModel with the model's
own remote code, exactly as the Hugging Face model card shows."""

import importlib.metadata
import time

import numpy as np
import soundfile as sf
from _protocol import serve

REPO = "ai4bharat/IndicF5"
# trust_remote_code runs the repo's own model.py. Pin the commit we reviewed (2026-10-11:
# it only loads the vocoder, vocab and weights; its upload code is under __main__) so a
# later push to the repo can't change what executes here.
REVISION = "fb652a96e508091045890dae5bb99fe511facbcf"
SAMPLE_RATE = 24_000
model = None


def load(_req):
    global model
    if model is None:
        from transformers import AutoModel

        # model.py picks CUDA or CPU itself and torch.compile()s its modules; moving them
        # to MPS afterwards is fragile, so IndicF5 runs on CPU on a Mac.
        model = AutoModel.from_pretrained(REPO, trust_remote_code=True, revision=REVISION)
    version = importlib.metadata.version("transformers")
    return {"device": "cpu", "version": f"IndicF5@{REVISION[:7]} (transformers {version})"}


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
