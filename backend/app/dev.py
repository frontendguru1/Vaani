"""`uv run vaani-dev` — the one command to start the backend (auto-migrates, hot-reloads)."""

import uvicorn

from app.cli import upgrade_to_head
from app.config import get_settings


def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    upgrade_to_head()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
