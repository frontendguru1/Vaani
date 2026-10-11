import logging
import os

# Must be set before torch is ever imported (engines import it lazily).
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app import __version__  # noqa: E402
from app.api.v1 import api_router  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.engines import registry  # noqa: E402
from app.engines.base import EngineError  # noqa: E402
from app.security import install as install_security  # noqa: E402
from app.services.audio import AudioError  # noqa: E402
from app.services.errors import ServiceError  # noqa: E402
from app.services.jobs import get_runner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vaani")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    log.info("Vaani %s | data=%s | db=%s", __version__, settings.data_dir, settings.db_url)
    runner = get_runner()
    runner.start()
    yield
    runner.stop()
    for eng in registry.all_engines():
        if eng.is_loaded:
            eng.unload()


app = FastAPI(title="Vaani", version=__version__, lifespan=lifespan)
install_security(app)
app.include_router(api_router)


@app.exception_handler(ServiceError)
async def _service_error(_req: Request, exc: ServiceError):
    return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status_code)


@app.exception_handler(EngineError)
async def _engine_error(_req: Request, exc: EngineError):
    return JSONResponse({"detail": str(exc), "code": "engine_error"}, status_code=422)


@app.exception_handler(AudioError)
async def _audio_error(_req: Request, exc: AudioError):
    return JSONResponse({"detail": str(exc), "code": "audio_error"}, status_code=422)
