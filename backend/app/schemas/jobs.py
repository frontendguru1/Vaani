from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: str
    progress: float
    step: str | None
    message: str | None
    voice_id: str | None
    generation_id: str | None
    result: dict[str, Any] | None
    error: str | None
    queue_position: int = 0
    created_at: datetime
    updated_at: datetime


class EngineOut(BaseModel):
    name: str
    label: str
    languages: list[str]
    available: bool
    reason: str
    loaded: bool
    device: str | None
    needs_transcript: bool
    license: str
    default: bool
