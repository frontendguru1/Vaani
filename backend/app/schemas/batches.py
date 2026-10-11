from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.generations import GenerationOut, GenerationSettings


class BatchItemIn(BaseModel):
    title: str = Field(default="", max_length=200)
    script: str = Field(max_length=20_000)


class BatchCreate(BaseModel):
    voice_id: str
    language: str
    title: str = Field(default="", max_length=200)
    engine: str | None = None
    settings: GenerationSettings = GenerationSettings()
    items: list[BatchItemIn] = Field(max_length=50)


class BatchOut(BaseModel):
    id: str
    title: str
    voice_id: str
    voice_name: str | None
    language: str
    engine: str
    created_at: datetime
    progress: float
    finished: bool
    counts: dict[str, int]
    items: list[GenerationOut]
    done_chunks: dict[str, int] = {}
    extra: dict[str, Any] = {}
