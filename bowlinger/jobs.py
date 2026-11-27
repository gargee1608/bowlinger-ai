"""SQLite-backed background job queue.

The API enqueues a row and returns. A daemon thread claims rows and runs the
handler. Tests set sync=True so the handler runs before enqueue returns.

The thread is started when the app is created, not only from the ASGI lifespan.
Uvicorn's default lifespan mode keeps serving if startup is skipped, and a
thread that dies on an uncaught error never comes back. Either one leaves
every later upload at 'queued' with no error on the session.
"""

from __future__ import annotations

import logging
import threading
import traceback
from pathlib import Path
from typing import Callable

from bowlinger.db import (
    claim_next_job,
    create_job,
    finish_job,
    get_session,
    requeue_interrupted_jobs,
    set_session_status,
    surface_orphaned_session_failures,
)

logger = logging.getLogger("uvicorn.error")

JobHandler = Callable[[dict], None]


class JobQueue:
    def __init__(
        self,
        db_path: Path,
        handler: JobHandler,
        sync: bool = False,
        poll_s: float = 0.25,
    ) -> None:
        self.db_path = db_path
        self.handler = handler
        self.sync = sync
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def alive(self) -> bool:
        if self.sync:
            return True
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.sync or (self._thread is not None and self._thread.is_alive()):
            return
        requeue_interrupted_jobs(self.db_path)
        surface_orphaned_session_failures(self.db_path)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bowlinger-jobs", daemon=True)
        self._thread.start()
        logger.info("bowlinger job worker started")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
            self._thread = None

    def enqueue(self, session_id: str) -> str:
        if not self.sync and not self.alive():
            self.start()
        job_id = create_job(self.db_path, session_id)
        if self.sync:
            while self.run_once():
                pass
        return job_id

    def run_once(self) -> bool:
        try:
            job = claim_next_job(self.db_path)
        except Exception:
            logger.exception("bowlinger job worker could not claim a job")
            return False
        if job is None:
            return False
        try:
            self.handler(job)
        except Exception as exc:
            message = f"{exc}\n{traceback.format_exc()}"
            logger.error("bowlinger job %s failed: %s", job["id"], exc)
            self._finish(job["id"], "failed", message)
            self._fail_session(job["session_id"], exc)
        else:
            self._finish(job["id"], "completed", None)
        return True

    def _finish(self, job_id: str, status: str, error: str | None) -> None:
        try:
            finish_job(self.db_path, job_id, status, error=error)
        except Exception:
            logger.exception("bowlinger job worker could not record job %s as %s", job_id, status)

    def _fail_session(self, session_id: str, exc: BaseException) -> None:
        try:
            row = get_session(self.db_path, session_id)
            if row is None or row["status"] not in {"queued", "running"}:
                return
            set_session_status(self.db_path, session_id, "failed", error=str(exc)[:500])
        except Exception:
            logger.exception("bowlinger job worker could not mark session %s failed", session_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("bowlinger job worker iteration failed")
                worked = False
            if not worked:
                self._stop.wait(self.poll_s)
