import logging

from app.config import get_settings

log = logging.getLogger("vaani.device")


def pick_torch_device(engine: str, override: str | None = None) -> str:
    """Resolve 'auto' to mps or cpu. Engines still fall back to cpu if mps fails at load."""
    import torch

    pref = override or get_settings().device
    if pref == "cpu":
        return "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if pref == "mps":
        log.warning("%s: MPS requested but unavailable; using CPU", engine)
    return "cpu"
