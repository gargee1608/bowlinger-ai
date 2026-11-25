"""Local video files and the per-user storage cap."""

from __future__ import annotations

from pathlib import Path

from bowlinger.config import Settings
from bowlinger.db import delete_session, list_user_sessions

ALLOWED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def normalised_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix in ALLOWED_SUFFIXES else ".mp4"


def video_path(settings: Settings, user_id: str, session_id: str, suffix: str) -> Path:
    safe_suffix = suffix if suffix in ALLOWED_SUFFIXES else ".mp4"
    return settings.data_dir / "videos" / user_id / f"{session_id}{safe_suffix}"


def save_bytes(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.stat().st_size


def delete_file(path: str | Path | None) -> None:
    if not path:
        return
    file = Path(path)
    if file.is_file():
        file.unlink()


class QuotaError(ValueError):
    """The upload does not fit in this user's cap."""


def used_bytes(settings: Settings, user_id: str) -> int:
    return sum(row["video_bytes"] for row in list_user_sessions(settings.db_path, user_id))


def enforce_quota(settings: Settings, user_id: str, incoming_bytes: int) -> list[str]:
    """Drop oldest sessions until `incoming_bytes` fits. Reject a file bigger than the cap."""
    if settings.flush_policy != "oldest_first":
        raise RuntimeError(f"Unsupported flush policy {settings.flush_policy!r}")
    if incoming_bytes > settings.quota_bytes:
        raise QuotaError("This video is larger than the 1 GB per-user storage cap")
    flushed: list[str] = []
    while used_bytes(settings, user_id) + incoming_bytes > settings.quota_bytes:
        oldest = list_user_sessions(settings.db_path, user_id)
        if not oldest:
            raise QuotaError("Not enough storage for this video")
        victim = oldest[0]
        delete_file(victim.get("video_path"))
        delete_session(settings.db_path, victim["id"])
        flushed.append(victim["id"])
    return flushed
