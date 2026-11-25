"""SQLite-backed background job queue.

The API enqueues a row and returns. A daemon thread claims rows and runs the
handler. Tests set sync=True so the handler runs before enqueue returns.
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable

from bowlinger.db import claim_next_job, create_job, finish_job

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

    def start(self) -> None:
        if self.sync or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="bowlinger-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
            self._thread = None

    def enqueue(self, session_id: str) -> str:
        job_id = create_job(self.db_path, session_id)
        if self.sync:
            while self.run_once():
                pass
        return job_id

    def run_once(self) -> bool:
        job = claim_next_job(self.db_path)
        if job is None:
            return False
        try:
            self.handler(job)
        except Exception as exc:
            finish_job(self.db_path, job["id"], "failed", error=f"{exc}\n{traceback.format_exc()}")
        else:
            finish_job(self.db_path, job["id"], "completed")
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            worked = self.run_once()
            if not worked:
                self._stop.wait(self.poll_s)
