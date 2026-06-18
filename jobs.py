"""
Lightweight in-memory background-job manager for iceReach.

Heavy operations (sending, filtering, scraping) are long-running and blocking.
Running them inside the request/response cycle freezes the event loop and risks
HTTP timeouts. This module lets the API launch such work off the event loop,
return a job id immediately, and expose progress/status for polling.

State is in-memory and intentionally simple: it does not survive a process
restart (e.g. uvicorn --reload). For multi-process or persistent needs, swap
this for a real task queue (Celery/RQ/arq) + shared store.
"""

import os
import time
import uuid
import threading
from typing import Any, Callable, Dict, List, Optional


# Job lifecycle states
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
ERROR = "error"


class JobManager:
    def __init__(self, output_dir: str = "generated_files", retention_seconds: int = 6 * 3600):
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self.output_dir = output_dir
        self.retention_seconds = retention_seconds
        os.makedirs(self.output_dir, exist_ok=True)

    # ---- lifecycle ----------------------------------------------------------
    def create(self, job_type: str, message: str = "Queued") -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "type": job_type,
                "status": QUEUED,
                "progress": 0,
                "message": message,
                "result": None,      # JSON-serializable payload returned to the client
                "files": {},         # key -> absolute path of a downloadable artifact
                "error": None,
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        return job_id

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(fields)
                job["updated_at"] = time.time()

    def set_progress(self, job_id: str, percent: float, message: Optional[str] = None) -> None:
        fields: Dict[str, Any] = {"progress": max(0, min(100, int(percent)))}
        if message is not None:
            fields["message"] = message
        self.update(job_id, **fields)

    def attach_file(self, job_id: str, key: str, path: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job["files"][key] = path
                job["updated_at"] = time.time()

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return _copy_job(job) if job else None

    def get_file(self, job_id: str, key: str) -> Optional[str]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return job["files"].get(key)

    # ---- public view (hide internal-only fields) ----------------------------
    def public_view(self, job_id: str) -> Optional[dict]:
        job = self.get(job_id)
        if not job:
            return None
        view = {
            "id": job["id"],
            "type": job["type"],
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
            "result": job["result"],
            "error": job["error"],
            # expose which artifacts are downloadable, not their server paths
            "downloads": sorted(job["files"].keys()),
        }
        return view

    # ---- cleanup ------------------------------------------------------------
    def cleanup_old(self) -> None:
        """Drop jobs (and their generated files) older than the retention window."""
        now = time.time()
        stale_paths: List[str] = []
        with self._lock:
            stale_ids = [jid for jid, j in self._jobs.items()
                         if now - j["created_at"] > self.retention_seconds]
            for jid in stale_ids:
                job = self._jobs.pop(jid)
                stale_paths.extend(job["files"].values())
        for path in stale_paths:
            _safe_remove(path)


def _copy_job(job: dict) -> dict:
    clone = dict(job)
    clone["files"] = dict(job["files"])
    return clone


def _safe_remove(path: Optional[str]) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def make_progress_callback(manager: JobManager, job_id: str) -> Callable[[float, Optional[str]], None]:
    """Return a (percent, message) callback bound to a job, safe to call from a worker thread."""
    def _cb(percent: float, message: Optional[str] = None) -> None:
        manager.set_progress(job_id, percent, message)
    return _cb
