"""Download one YouTube video for analysis.

The URL is checked and passed to yt-dlp. It is not written into the session
row or into a sidecar file. The stored name is the video title.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def validate_youtube_url(url: str) -> str:
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if parsed.scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError("Paste a YouTube link (youtube.com or youtu.be)")
    if not parsed.path or parsed.path == "/":
        raise ValueError("That YouTube link does not point at a video")
    return cleaned


def _safe_title(info: dict | None) -> str:
    raw = str((info or {}).get("title") or "youtube video")
    cleaned = "".join(ch if ch.isalnum() or ch in " ._-()" else " " for ch in raw)
    collapsed = " ".join(cleaned.split())
    return (collapsed or "youtube video")[:80]


def download_youtube(url: str, dest_dir: Path) -> tuple[Path, str]:
    """Return the downloaded file and a title. The URL is not written to disk."""
    import yt_dlp

    checked = validate_youtube_url(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best[ext=mp4]/best",
        "outtmpl": str(dest_dir / "clip.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": 200 * 1024 * 1024,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(checked, download=True)
    files = sorted(dest_dir.glob("clip.*"))
    videos = [path for path in files if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    chosen = videos[0] if videos else (files[0] if files else None)
    if chosen is None or not chosen.is_file() or chosen.stat().st_size == 0:
        raise ValueError("YouTube did not return a video file")
    return chosen, _safe_title(info)
