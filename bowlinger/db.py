"""SQLite access. Each call opens its own connection so the job thread is safe."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    is_public INTEGER NOT NULL DEFAULT 1,
    original_name TEXT,
    video_path TEXT,
    video_bytes INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_created ON sessions (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs (status, created_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None is autocommit so claim_next_job can own its BEGIN.
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def create_job(db_path: Path, session_id: str) -> str:
    job_id = str(uuid4())
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (id, session_id, status, created_at) VALUES (?, ?, 'queued', ?)",
            (job_id, session_id, utcnow()),
        )
    return job_id


def claim_next_job(db_path: Path) -> dict | None:
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, session_id FROM jobs WHERE status = 'queued' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
            (utcnow(), row["id"]),
        )
        if cur.rowcount != 1:
            return None
        return {"id": row["id"], "session_id": row["session_id"]}


def finish_job(db_path: Path, job_id: str, status: str, error: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
            (status, error, utcnow(), job_id),
        )


def get_job(db_path: Path, job_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None
