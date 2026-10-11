"""In-process background jobs.

One worker thread drains a FIFO queue, so only one job touches a model at a time (the
models are big and the M1 has one GPU). Progress is written to the `jobs` row (so a reload
can recover) and pushed to SSE subscribers through asyncio queues.

Handlers register by kind:  @job_handler("generate") def run(ctx, payload): ...
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Job

log = logging.getLogger("vaani.jobs")

TERMINAL = {"succeeded", "failed"}
Handler = Callable[["JobContext", dict[str, Any]], dict[str, Any] | None]
_handlers: dict[str, Handler] = {}


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _handlers[kind] = fn
        return fn

    return deco


def job_event(
    job: Job, type_: str = "progress", data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": type_,
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": round(job.progress, 4),
        "step": job.step,
        "message": job.message,
        "voice_id": job.voice_id,
        "generation_id": job.generation_id,
        "result": job.result,
        "error": job.error,
        "data": data or {},
    }


class JobContext:
    """Handed to handlers to report progress. Writes are throttled except for step changes."""

    def __init__(self, runner: JobRunner, job_id: str) -> None:
        self.runner = runner
        self.job_id = job_id
        self._last_write = 0.0

    def session(self) -> Session:
        return self.runner.session_factory()

    def progress(
        self,
        fraction: float,
        step: str | None = None,
        message: str | None = None,
        *,
        event: str = "progress",
        **data: Any,
    ) -> None:
        with self.session() as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            step_changed = step is not None and step != job.step
            job.progress = max(0.0, min(1.0, fraction))
            if step is not None:
                job.step = step
            if message is not None:
                job.message = message
            now = time.monotonic()
            if step_changed or event != "progress" or now - self._last_write > 0.5:
                s.commit()
                self._last_write = now
            ev = job_event(job, event, data)
        self.runner.publish(self.job_id, ev)


class JobRunner:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._subs: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._subs_lock = threading.Lock()
        self.current_job: str | None = None

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        self._recover_interrupted()
        self._thread = threading.Thread(target=self._loop, name="vaani-jobs", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout)

    def _recover_interrupted(self) -> None:
        with self.session_factory() as s:
            stale = s.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
            for job in stale:
                job.status, job.error = "failed", "Interrupted: the app was restarted."
                _on_failure(s, job)
            s.commit()

    # -- submit / subscribe ------------------------------------------------
    def submit(
        self,
        session: Session,
        kind: str,
        payload: dict[str, Any],
        *,
        voice_id: str | None = None,
        generation_id: str | None = None,
    ) -> Job:
        if kind not in _handlers:
            raise ValueError(f"no handler for job kind {kind!r}")
        job = Job(
            kind=kind,
            payload=payload,
            voice_id=voice_id,
            generation_id=generation_id,
            message="Waiting in queue…",
        )
        session.add(job)
        session.commit()
        self._queue.put(job.id)
        return job

    def queue_position(self, job_id: str) -> int:
        with self._queue.mutex:
            items = list(self._queue.queue)
        return items.index(job_id) + 1 if job_id in items else 0

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._subs_lock:
            self._subs.setdefault(job_id, []).append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._subs_lock:
            subs = self._subs.get(job_id, [])
            self._subs[job_id] = [(lp, x) for lp, x in subs if x is not q]
            if not self._subs[job_id]:
                del self._subs[job_id]

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        with self._subs_lock:
            subs = list(self._subs.get(job_id, []))
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:  # loop closed (client went away)
                pass

    # -- worker -------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            self.current_job = job_id
            try:
                self.run_one(job_id)
            finally:
                self.current_job = None

    def run_one(self, job_id: str) -> None:
        with self.session_factory() as s:
            job = s.get(Job, job_id)
            if job is None or job.status in TERMINAL:
                return
            job.status, job.message = "running", "Starting…"
            s.commit()
            kind, payload = job.kind, dict(job.payload)
            self.publish(job_id, job_event(job))

        ctx = JobContext(self, job_id)
        try:
            result = _handlers[kind](ctx, payload) or {}
        except Exception as exc:  # noqa: BLE001 - any failure is reported to the UI
            log.exception("job %s (%s) failed", job_id, kind)
            with self.session_factory() as s:
                job = s.get(Job, job_id)
                if job is not None:
                    job.status, job.error = "failed", str(exc) or type(exc).__name__
                    job.message = "Failed"
                    _on_failure(s, job)
                    s.commit()
                    self.publish(job_id, job_event(job, "failed"))
            return

        with self.session_factory() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.status, job.progress, job.result = "succeeded", 1.0, result
                job.message = job.message if job.message != "Starting…" else "Done"
                s.commit()
                self.publish(job_id, job_event(job, "succeeded"))


_failure_hooks: dict[str, Callable[[Session, Job], None]] = {}


def on_job_failure(kind: str) -> Callable[[Callable[[Session, Job], None]], Callable]:
    """Let a feature mark its own rows failed (e.g. voice.status) when its job dies."""

    def deco(fn: Callable[[Session, Job], None]) -> Callable[[Session, Job], None]:
        _failure_hooks[kind] = fn
        return fn

    return deco


def _on_failure(session: Session, job: Job) -> None:
    hook = _failure_hooks.get(job.kind)
    if hook:
        try:
            hook(session, job)
        except Exception:  # noqa: BLE001
            log.exception("failure hook for %s raised", job.kind)


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        from app.db import SessionLocal

        _runner = JobRunner(SessionLocal)
    return _runner


def set_runner(runner: JobRunner | None) -> None:
    global _runner
    _runner = runner
