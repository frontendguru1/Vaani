from pydantic import BaseModel


class FfmpegStatus(BaseModel):
    available: bool
    version: str | None


class DeviceStatus(BaseModel):
    torch_installed: bool
    torch_version: str | None
    mps_available: bool
    preferred: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    database: bool
    schema_current: bool = True  # False: run `uv run vaani migrate`
    ffmpeg: FfmpegStatus
    device: DeviceStatus
    transcription: dict = {}
