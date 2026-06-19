"""DB-backed job queue + worker.

Evolves the legacy in-memory JobManager into a durable, workspace-scoped queue
that survives restarts and supports multiple worker processes. Jobs are claimed
atomically (optimistic update), retried with backoff, and sent to a dead-letter
state after max attempts (with an alert hook).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Job

MAX_ATTEMPTS = 5

# type -> handler(db, job, progress_cb)
HANDLERS: dict[str, Callable[[Session, Job, Callable[[float, str], None]], Optional[dict]]] = {}
# alert hooks invoked when a job is dead-lettered
DLQ_HOOKS: list[Callable[[Job], None]] = []


def register(job_type: str):
    """Decorator: register a handler for a job type."""
    def deco(fn):
        HANDLERS[job_type] = fn
        return fn
    return deco


def enqueue(db: Session, workspace_id: int, job_type: str, payload: dict[str, Any] | None = None,
            run_after: Optional[datetime] = None) -> Job:
    job = Job(
        workspace_id=workspace_id,
        type=job_type,
        status="queued",
        payload=payload or {},
        run_after=run_after or datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next(db: Session) -> Optional[Job]:
    """Atomically claim one due, queued job. Returns None if none available."""
    now = datetime.utcnow()
    candidate = db.scalars(
        select(Job).where(Job.status == "queued", Job.run_after <= now).order_by(Job.run_after).limit(1)
    ).first()
    if candidate is None:
        return None
    # Optimistic claim: only succeeds if still queued (guards against double-claim).
    res = db.execute(
        update(Job).where(Job.id == candidate.id, Job.status == "queued").values(status="running", progress=0)
    )
    db.commit()
    if res.rowcount == 1:
        db.refresh(candidate)
        return candidate
    return None  # lost the race to another worker


def _progress_cb(db: Session, job: Job):
    def cb(percent: float, message: str = ""):
        job.progress = max(0, min(100, int(percent)))
        if message:
            job.message = message[:500]
        db.commit()
    return cb


def run_job(db: Session, job: Job) -> None:
    """Execute a claimed job through its handler, with retry/backoff and DLQ."""
    handler = HANDLERS.get(job.type)
    if handler is None:
        job.status = "failed"
        job.error = f"No handler registered for job type '{job.type}'"
        db.commit()
        _fire_dlq(job)
        return

    job.attempts += 1
    db.commit()
    try:
        result = handler(db, job, _progress_cb(db, job))
        job.status = "done"
        job.progress = 100
        job.result = result if isinstance(result, dict) else {"ok": True}
        job.error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 — handlers may raise anything
        db.rollback()
        job = db.get(Job, job.id)
        job.error = str(exc)
        if job.attempts >= MAX_ATTEMPTS:
            job.status = "failed"
            db.commit()
            _fire_dlq(job)
        else:
            backoff = min(300, 2 ** job.attempts)
            job.status = "queued"
            job.run_after = datetime.utcnow() + timedelta(seconds=backoff)
            db.commit()


def _fire_dlq(job: Job) -> None:
    for hook in DLQ_HOOKS:
        try:
            hook(job)
        except Exception:  # noqa: BLE001 — alert hooks must never break the worker
            pass


def run_worker(poll_interval: float = 1.0, max_idle_loops: Optional[int] = None,
               on_idle: Optional[Callable[[Session], None]] = None) -> None:
    """Worker loop: claim and run jobs until interrupted (or idle limit hit, for tests).

    `on_idle(db)` runs on idle cycles — used to advance time-based work (automation
    journeys) without an external scheduler.
    """
    idle = 0
    while True:
        db = SessionLocal()
        try:
            job = claim_next(db)
            if job is None:
                if on_idle is not None:
                    try:
                        on_idle(db)
                    except Exception:  # noqa: BLE001 — never let a tick kill the worker
                        db.rollback()
                idle += 1
                if max_idle_loops is not None and idle >= max_idle_loops:
                    return
                time.sleep(poll_interval)
                continue
            idle = 0
            run_job(db, job)
        finally:
            db.close()


def _worker_kwargs_from_env() -> dict:
    """Optional knobs for tests/ops, read from the environment."""
    import os

    kwargs: dict[str, Any] = {}
    if (mi := os.environ.get("ICEREACH_WORKER_MAX_IDLE")):
        kwargs["max_idle_loops"] = int(mi)
    if (pi := os.environ.get("ICEREACH_WORKER_POLL")):
        kwargs["poll_interval"] = float(pi)
    return kwargs


def main() -> None:
    """Worker entrypoint: import handler modules so they register, then loop.

    Handlers register into THIS module's ``HANDLERS`` dict via ``@register``.
    Crucially this must run inside the canonical ``icereach.services.queue``
    module — see the ``__main__`` guard below for why.
    """
    from . import dsn, importer, sender  # noqa: F401 — register handlers on import
    from . import automation

    # Dev convenience, mirroring the API: ensure the schema exists so the worker
    # doesn't crash with "no such table: jobs" when it starts before the API (or
    # against a fresh DB). Production uses Alembic; create_all is a no-op once the
    # tables are there. Importing the handlers above pulls in every model first.
    from ..db import Base, engine
    Base.metadata.create_all(engine)

    # Advance automation journeys at most every ~30s on idle cycles.
    _last = [0.0]

    def _tick(db):
        now = time.monotonic()
        if now - _last[0] >= 30:
            _last[0] = now
            automation.advance_due_runs(db)

    print("iceReach worker starting... (send_campaign, import_contacts, poll_dsn, +automation ticks)")
    run_worker(on_idle=_tick, **_worker_kwargs_from_env())


if __name__ == "__main__":  # pragma: no cover
    # `python -m icereach.services.queue` loads this file as `__main__`. Handler
    # modules, however, register into `icereach.services.queue.HANDLERS` (a
    # SEPARATE module object created when they do `from .queue import register`).
    # If we called run_worker() from here, its run_job() would consult the empty
    # `__main__.HANDLERS` and fail every job with "No handler registered".
    # Delegate to the canonical module so registrations and the loop share one
    # HANDLERS dict.
    from icereach.services.queue import main as _main

    _main()
