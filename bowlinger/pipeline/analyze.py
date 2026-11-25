"""Run the analysis job for one session.

GB stores a readable-video result. Later goals add fields to the same dict.
"""

from __future__ import annotations

import json
from pathlib import Path

from bowlinger import __version__
from bowlinger.config import Settings
from bowlinger.db import get_session, set_session_status
from bowlinger.media import probe


def analyze_video(path: Path, settings: Settings) -> dict:
    info = probe(path)
    return {
        "pipeline_version": __version__,
        "video": {
            "fps": info["fps"],
            "width": info["width"],
            "height": info["height"],
            "frame_count": info["frame_count"],
            "duration_s": round(info["duration_s"], 3),
            "has_audio_stream": info["has_audio_stream"],
        },
        "deliveries": [],
    }


def process_job(settings: Settings, job: dict) -> None:
    session = get_session(settings.db_path, job["session_id"])
    if session is None:
        raise RuntimeError(f"session {job['session_id']} not found")
    set_session_status(settings.db_path, session["id"], "running", error=None)
    try:
        result = analyze_video(Path(session["video_path"]), settings)
    except Exception as exc:
        set_session_status(settings.db_path, session["id"], "failed", error=str(exc))
        raise
    set_session_status(
        settings.db_path,
        session["id"],
        "completed",
        error=None,
        result_json=json.dumps(result),
    )
