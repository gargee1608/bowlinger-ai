"""Local video files. Quota flushing is added with GD; this module only stores bytes."""

from __future__ import annotations

from pathlib import Path

from bowlinger.config import Settings

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
