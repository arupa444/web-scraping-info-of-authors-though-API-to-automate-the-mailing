"""Regression: the `python -m icereach.services.queue` worker entrypoint must
register handlers into the SAME HANDLERS dict its loop consults.

Running the module with `-m` loads it twice: once as `icereach.services.queue`
(where @register populates HANDLERS) and once as `__main__` (which runs the
loop). If the loop reads the `__main__` copy's HANDLERS, it stays empty and
every job dies with "No handler registered" — which is exactly what bit the
send-campaign and import-contacts jobs. This test reproduces that by importing
the canonical module and then running the module body under run_name="__main__"
in a subprocess, asserting a queued job reaches its real handler.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_worker_entrypoint_registers_handlers(tmp_path):
    db_file = (tmp_path / "worker.db").as_posix()
    script = textwrap.dedent(
        f"""
        import os, runpy
        os.environ["DATABASE_URL"] = "sqlite:///{db_file}"
        os.environ["SECRET_KEY"] = "x"
        os.environ["ICEREACH_WORKER_MAX_IDLE"] = "3"
        os.environ["ICEREACH_WORKER_POLL"] = "0.02"

        from icereach.db import Base, engine, SessionLocal
        import icereach.models  # noqa: F401  (populate metadata)
        Base.metadata.create_all(engine)

        from icereach.services.queue import enqueue
        s = SessionLocal()
        # Missing 'file_path' makes the handler raise ValueError — proving the
        # handler was FOUND (a missing handler gives a different error).
        job = enqueue(s, 1, "import_contacts", {{}})
        jid = job.id
        s.close()

        # Faithful equivalent of `python -m icereach.services.queue`.
        runpy.run_module("icereach.services.queue", run_name="__main__")

        from icereach.models import Job
        s = SessionLocal()
        j = s.get(Job, jid)
        err = j.error or ""
        print("FINAL status=%r error=%r" % (j.status, err))
        assert "No handler registered" not in err, err
        assert "file_path" in err, err
        s.close()
        """
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
