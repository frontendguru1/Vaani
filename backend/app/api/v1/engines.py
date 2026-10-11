from fastapi import APIRouter

from app.config import get_settings
from app.engines import registry
from app.schemas.jobs import EngineOut

router = APIRouter(prefix="/engines", tags=["engines"])


@router.get("", response_model=list[EngineOut])
def list_engines():
    default = get_settings().default_engine
    default = "xtts" if default == "auto" else default
    out = []
    for eng in registry.all_engines():
        avail = eng.availability()
        out.append(
            EngineOut(
                name=eng.name,
                label=eng.label,
                languages=sorted(eng.supported_languages),
                available=avail.ok,
                reason=avail.reason,
                loaded=eng.is_loaded,
                device=eng.device,
                needs_transcript=eng.needs_transcript,
                max_ref_seconds=getattr(eng, "max_ref_seconds", None),
                license=eng.license,
                default=eng.name == default,
            )
        )
    return out
