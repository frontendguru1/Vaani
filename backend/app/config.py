"""Single source of configuration. Values come from env vars / the repo-root .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="VAANI_",
        extra="ignore",
        # A copied .env.example has blank lines like `VAANI_XTTS_DEVICE=`; treat them as unset.
        env_ignore_empty=True,
    )

    data_dir: Path = Path("data")
    # DATABASE_URL is conventionally unprefixed.
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    device: Literal["auto", "mps", "cpu"] = "auto"
    default_engine: str = "xtts"
    # Per-engine device override (XTTS on MPS has known hangs; benchmark decides).
    xtts_device: Literal["auto", "mps", "cpu"] | None = None
    # F5-TTS MLX weights: None = full precision, 4 or 8 = quantized (smaller, slightly worse).
    f5mlx_quant: Literal[4, 8] | None = None
    pause_sentence_ms: int = 350
    pause_paragraph_ms: int = 800
    pause_turn_ms: int = 500  # between speakers in a dialogue
    features: set[str] = set()
    host: str = "127.0.0.1"
    port: int = 8000
    # Security: only these Host headers are served (blocks DNS rebinding), and browsers may
    # only send state-changing requests from these origins (blocks cross-site form posts).
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    # Auto-transcription (mlx-whisper). Weights live in data/models/whisper/<name>.
    transcribe_model: str = "mlx-community/whisper-large-v3-turbo"
    transcribe_on_create: bool = True
    max_upload_mb: int = 1024  # whole request; each file is also capped at 200 MB

    @field_validator("data_dir")
    @classmethod
    def _absolute_data_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (REPO_ROOT / v).resolve()

    @field_validator("features", mode="before")
    @classmethod
    def _split_features(cls, v: object) -> object:
        if isinstance(v, str):
            return {f.strip() for f in v.split(",") if f.strip()}
        return v

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'vaani.db'}"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    def feature_enabled(self, name: str) -> bool:
        return name in self.features

    def ensure_dirs(self) -> None:
        for sub in ("", "voices", "generations", "models", "benchmarks"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
