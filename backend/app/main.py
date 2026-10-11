import logging
import os

# Must be set before torch is ever imported (engines import it lazily).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402

from app import __version__  # noqa: E402
from app.api.v1 import api_router  # noqa: E402
from app.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vaani")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    log.info("Vaani %s | data=%s | db=%s", __version__, settings.data_dir, settings.db_url)
    yield


app = FastAPI(title="Vaani", version=__version__, lifespan=lifespan)
app.include_router(api_router)
