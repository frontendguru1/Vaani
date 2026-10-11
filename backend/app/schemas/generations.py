from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenerationSettings(BaseModel):
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    temperature: float | None = Field(default=None, ge=0.1, le=1.0)
    sentence_pause_ms: int | None = Field(default=None, ge=0, le=5000)
    paragraph_pause_ms: int | None = Field(default=None, ge=0, le=5000)


class GenerationCreate(BaseModel):
    voice_id: str
    script: str = Field(min_length=1, max_length=20_000)
    language: str
    engine: str | None = None
    settings: GenerationSettings = GenerationSettings()


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    idx: int
    text: str
    voice_id: str | None = None  # speaker, in a dialogue (None = the generation's voice)
    spoken_text: str | None = None
    char_start: int
    char_end: int
    pause_after_ms: int
    status: str
    duration_seconds: float | None
    compute_seconds: float | None
    offset_seconds: float | None


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    voice_id: str
    voice_name: str | None = None
    speakers: list[str] = []  # names of everyone who speaks, for dialogues
    engine: str
    engine_version: str | None
    language: str
    script: str
    settings: dict[str, Any]
    status: str
    error: str | None
    device: str | None
    duration_seconds: float | None
    compute_seconds: float | None
    chunk_count: int
    created_at: datetime


class GenerationDetail(GenerationOut):
    chunks: list[ChunkOut]


class GenerationCreated(BaseModel):
    generation: GenerationDetail
    job_id: str
