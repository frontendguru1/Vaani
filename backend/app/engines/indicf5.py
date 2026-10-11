from app.engines.base import Availability
from app.engines.registry import register
from app.engines.subprocess_engine import SubprocessEngine, hf_token_path


@register
class IndicF5Engine(SubprocessEngine):
    """AI4Bharat IndicF5 (F5-TTS fine-tuned on Indian languages). Gated on Hugging Face."""

    name = "indicf5"
    label = "IndicF5"
    supported_languages = frozenset(
        {"hi", "mr", "bn", "gu", "kn", "ml", "or", "pa", "ta", "te", "as"}
    )
    sample_rate = 24_000
    license = "MIT (gated: accept terms on Hugging Face)"
    venv = "indicf5"
    hf_repo = "ai4bharat/IndicF5"
    worker_script = "indicf5_worker.py"
    max_ref_seconds = 15.0

    def availability(self) -> Availability:
        base = super().availability()
        if not base.ok:
            return base
        if hf_token_path() is None:
            return Availability(
                False,
                "gated model: accept terms on huggingface.co/ai4bharat/IndicF5, then "
                "run `huggingface-cli login`",
            )
        return base
