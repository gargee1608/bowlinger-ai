"""SQLite access. Each call opens its own connection so the job thread is safe."""

from __future__ import annotations

import json
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

CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    video_ref TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_created ON annotations (created_at);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "overrides_json" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN overrides_json TEXT")
        if "progress_json" not in columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN progress_json TEXT")


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


def requeue_interrupted_jobs(db_path: Path) -> int:
    """Jobs left 'running' by a dead process will never be claimed again."""
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'queued', started_at = NULL WHERE status = 'running'"
        )
        return cur.rowcount


def surface_orphaned_session_failures(db_path: Path) -> int:
    """A failed job used to leave its session at queued, which the page shows forever."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.id, j.error
            FROM sessions s
            JOIN jobs j ON j.session_id = s.id
            WHERE s.status = 'queued'
              AND j.status = 'failed'
              AND NOT EXISTS (
                SELECT 1 FROM jobs q
                WHERE q.session_id = s.id AND q.status IN ('queued', 'running')
              )
            ORDER BY j.finished_at DESC
            """
        ).fetchall()
        seen: set[str] = set()
        updated = 0
        now = utcnow()
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            error = ((row["error"] or "The analysis job failed.").splitlines() or ["The analysis job failed."])[0][:500]
            cur = conn.execute(
                "UPDATE sessions SET status = 'failed', error = ?, updated_at = ? WHERE id = ? AND status = 'queued'",
                (error, now, row["id"]),
            )
            updated += cur.rowcount
        return updated


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


def ensure_user(db_path: Path, user_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, created_at) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
            (user_id, utcnow()),
        )


def insert_session(
    db_path: Path,
    *,
    session_id: str,
    user_id: str,
    source: str,
    original_name: str,
    video_path: str,
    video_bytes: int,
) -> None:
    now = utcnow()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                id, user_id, status, source, is_public, original_name,
                video_path, video_bytes, created_at, updated_at
            ) VALUES (?, ?, 'queued', ?, 1, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, source, original_name, video_path, video_bytes, now, now),
        )


def list_sessions(db_path: Path, limit: int = 200) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def insert_annotation(db_path: Path, *, kind: str, video_ref: str | None, payload_json: str) -> str:
    annotation_id = str(uuid4())
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO annotations (id, kind, video_ref, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (annotation_id, kind, video_ref, payload_json, utcnow()),
        )
    return annotation_id


def list_annotations(db_path: Path, kind: str | None = None) -> list[dict]:
    with connect(db_path) as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM annotations WHERE kind = ? ORDER BY created_at DESC",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM annotations ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_annotation(db_path: Path, annotation_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)).fetchone()
    return dict(row) if row else None


def list_user_sessions(db_path: Path, user_id: str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at ASC, rowid ASC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_session(db_path: Path, session_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def set_session_overrides(db_path: Path, session_id: str, overrides_json: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE sessions SET overrides_json = ?, updated_at = ? WHERE id = ?",
            (overrides_json, utcnow(), session_id),
        )


def get_session(db_path: Path, session_id: str) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def set_session_progress(db_path: Path, session_id: str, stage: str | None, percent: int | None) -> None:
    payload = None if stage is None else json.dumps({"stage": stage, "percent": int(percent or 0)})
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE sessions SET progress_json = ?, updated_at = ? WHERE id = ?",
            (payload, utcnow(), session_id),
        )


def set_session_status(
    db_path: Path,
    session_id: str,
    status: str,
    *,
    error: str | None = None,
    result_json: str | None = None,
    clear_result: bool = False,
) -> None:
    with connect(db_path) as conn:
        if clear_result:
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, error = ?, result_json = NULL, updated_at = ?
                WHERE id = ?
                """,
                (status, error, utcnow(), session_id),
            )
            return
        conn.execute(
            """
            UPDATE sessions
            SET status = ?, error = ?, result_json = COALESCE(?, result_json), updated_at = ?
            WHERE id = ?
            """,
            (status, error, result_json, utcnow(), session_id),
        )
