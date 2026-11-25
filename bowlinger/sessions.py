"""Create a session from an uploaded video and shape the public JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from bowlinger.config import Settings
from bowlinger.db import ensure_user, get_session, insert_session
from bowlinger.storage import delete_file, normalised_suffix, save_bytes, video_path

USER_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


def new_user_key() -> str:
    return "anon_" + uuid4().hex[:12]


def resolve_user_key(user_key: str | None) -> str:
    if user_key is None or user_key.strip() == "":
        return new_user_key()
    cleaned = user_key.strip()
    if not USER_KEY_RE.match(cleaned):
        raise ValueError("user_key must be 4–64 letters, numbers, underscores, or hyphens")
    return cleaned


def public_session(row: dict) -> dict:
    result = json.loads(row["result_json"]) if row.get("result_json") else None
    return {
        "session_id": row["id"],
        "user_key": row["user_id"],
        "status": row["status"],
        "source": row["source"],
        "is_public": bool(row["is_public"]),
        "original_name": row["original_name"],
        "video_bytes": row["video_bytes"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "result": result,
    }


def accept_video(
    settings: Settings,
    *,
    filename: str | None,
    data: bytes,
    user_key: str | None,
    source: str = "upload",
) -> dict:
    if not data:
        raise ValueError("The video file is empty")
    owner = resolve_user_key(user_key)
    ensure_user(settings.db_path, owner)
    session_id = str(uuid4())
    suffix = normalised_suffix(filename)
    path = video_path(settings, owner, session_id, suffix)
    original = Path(filename or "video.mp4").name
    try:
        nbytes = save_bytes(path, data)
        insert_session(
            settings.db_path,
            session_id=session_id,
            user_id=owner,
            source=source,
            original_name=original,
            video_path=str(path),
            video_bytes=nbytes,
        )
    except Exception:
        delete_file(path)
        raise
    row = get_session(settings.db_path, session_id)
    if row is None:
        raise RuntimeError("session was not stored")
    return row
