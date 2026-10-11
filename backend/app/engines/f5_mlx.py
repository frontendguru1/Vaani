import os
from typing import Any

from app.engines.registry import register
from app.engines.subprocess_engine import SubprocessEngine


@register
class F5MLXEngine(SubprocessEngine):
    """F5-TTS ported to Apple MLX (lucasnewman/f5-tts-mlx). English-centric."""

    name = "f5_mlx"
    label = "F5-TTS MLX"
    supported_languages = frozenset({"en"})
    sample_rate = 24_000
    license = "Code MIT; weights unstated (upstream F5-TTS weights CC-BY-NC)"
    venv = "f5mlx"
    worker_script = "f5mlx_worker.py"
    max_ref_seconds = 12.0

    def load_options(self) -> dict[str, Any]:
        q = os.environ.get("VAANI_F5MLX_QUANT", "").strip()  # "", "4" or "8"
        return {"quantization_bits": int(q) if q else None}
