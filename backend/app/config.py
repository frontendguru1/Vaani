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
    )

    data_dir: Path = Path("data")
    # DATABASE_URL is conventionally unprefixed.
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    device: Literal["auto", "mps", "cpu"] = "auto"
    default_engine: str = "xtts"
    # Per-engine device override (XTTS on MPS has known hangs; benchmark decides).
    xtts_device: Literal["auto", "mps", "cpu"] | None = None
    pause_sentence_ms: int = 350
    pause_paragraph_ms: int = 800
    features: set[str] = set()
    host: str = "127.0.0.1"
    port: int = 8000

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
