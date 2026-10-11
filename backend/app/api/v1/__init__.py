"""The one place feature routers are registered. Add a module, append it here."""

from fastapi import APIRouter

from app.api.v1 import batches, engines, generations, health, jobs, pronunciation, voices

api_router = APIRouter(prefix="/api/v1")

for module in (health, engines, voices, generations, batches, jobs, pronunciation):
    api_router.include_router(module.router)
