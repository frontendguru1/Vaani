from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db import get_session
from app.schemas.health import HealthResponse
from app.services import system, transcription

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(session: Session = Depends(get_session)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 - health must never raise
        db_ok = False
    ffmpeg = system.ffmpeg_info()
    try:
        from app.cli import schema_is_current

        schema_ok = schema_is_current()[0]
    except Exception:  # noqa: BLE001
        schema_ok = False
    return HealthResponse(
        status="ok" if db_ok and ffmpeg.available and schema_ok else "degraded",
        schema_current=schema_ok,
        app="vaani",
        version=__version__,
        database=db_ok,
        ffmpeg=asdict(ffmpeg),
        device=asdict(system.device_info(get_settings().device)),
        transcription=transcription.status(),
    )
