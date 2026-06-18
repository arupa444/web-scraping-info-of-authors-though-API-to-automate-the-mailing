from icereach.models import Workspace
from icereach.services import queue


def _ws(db):
    ws = Workspace(name="W", slug="w-queue")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


def test_enqueue_creates_queued_job(db):
    ws = _ws(db)
    job = queue.enqueue(db, ws.id, "noop", {"x": 1})
    assert job.id is not None
    assert job.status == "queued"
    assert job.payload == {"x": 1}


def test_claim_next_is_atomic(db):
    ws = _ws(db)
    queue.enqueue(db, ws.id, "noop", {})
    first = queue.claim_next(db)
    assert first is not None and first.status == "running"
    second = queue.claim_next(db)
    assert second is None  # no double-claim


def test_successful_handler_marks_done_with_result(db):
    ws = _ws(db)

    @queue.register("ok_job")
    def _ok(db, job, progress):
        progress(50, "halfway")
        return {"answer": 42}

    job = queue.enqueue(db, ws.id, "ok_job", {})
    claimed = queue.claim_next(db)
    queue.run_job(db, claimed)
    db.refresh(job)
    assert job.status == "done"
    assert job.progress == 100
    assert job.result == {"answer": 42}


def test_failing_handler_retries_then_dead_letters(db):
    ws = _ws(db)
    dead = []
    queue.DLQ_HOOKS.append(lambda j: dead.append(j.id))

    @queue.register("boom")
    def _boom(db, job, progress):
        raise RuntimeError("nope")

    job = queue.enqueue(db, ws.id, "boom", {})
    for _ in range(queue.MAX_ATTEMPTS):
        current = db.get(type(job), job.id)
        queue.run_job(db, current)

    db.refresh(job)
    assert job.attempts == queue.MAX_ATTEMPTS
    assert job.status == "failed"
    assert "nope" in (job.error or "")
    assert job.id in dead
