import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_session
from app.models import Job
from app.schemas.jobs import JobOut
from app.services.errors import NotFound
from app.services.jobs import TERMINAL, get_runner, job_event

router = APIRouter(prefix="/jobs", tags=["jobs"])

HEARTBEAT_SECONDS = 15


def _job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found", code="job_not_found")
    return job


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = _job(session, job_id)
    return JobOut.model_validate(job).model_copy(
        update={"queue_position": get_runner().queue_position(job_id)}
    )


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request):
    """Server-Sent Events: the current state first, then every progress event until the job
    finishes. Clients reconnecting get the current state again, so nothing is lost."""
    with SessionLocal() as s:
        snapshot = job_event(_job(s, job_id), "snapshot")
    runner = get_runner()
    queue = runner.subscribe(job_id)

    def fmt(event: dict) -> str:
        return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"

    async def stream():
        try:
            snapshot["data"]["queue_position"] = runner.queue_position(job_id)
            yield fmt(snapshot)
            if snapshot["status"] in TERMINAL:
                return
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield fmt(event)
                if event["status"] in TERMINAL:
                    return
        finally:
            runner.unsubscribe(job_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
