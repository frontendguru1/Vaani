from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    original_filename: str
    size_bytes: int
    duration_seconds: float
    transcript: str | None
    transcript_source: str | None = None
    transcript_segments: list[dict[str, Any]] | None = None
    quality: dict[str, Any] | None
    segments: list[dict[str, Any]] | None
    has_audio: bool = False


class VoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    language: str
    description: str
    consent_note: str
    status: str
    error: str | None
    source: str = "user"
    gender: str | None = None
    quality_rating: str | None
    quality_report: dict[str, Any] | None
    speech_seconds: float
    has_preview: bool = False
    has_transcripts: bool = False
    sort_order: int
    generation_count: int = 0
    created_at: datetime
    updated_at: datetime


class VoiceDetail(VoiceOut):
    samples: list[SampleOut]
    engines_ready: list[str] = []


class VoiceCreated(BaseModel):
    voice: VoiceOut
    job_id: str


class VoiceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    language: str | None = None
    description: str | None = None
    consent_note: str | None = None
    sort_order: int | None = None


class SegmentTexts(BaseModel):
    texts: list[str] = Field(max_length=500)


class JobStarted(BaseModel):
    job_id: str


class DeleteResult(BaseModel):
    voice_id: str
    files_removed: int
    generations_removed: int
    leftover_paths: list[str]


class QualityCheck(BaseModel):
    filename: str
    duration: float
    report: dict[str, Any]
