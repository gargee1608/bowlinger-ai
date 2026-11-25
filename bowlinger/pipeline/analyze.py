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
from bowlinger.pipeline.audio import inspect_audio
from bowlinger.pipeline.deliveries import build_deliveries
from bowlinger.pipeline.detect import scan_video
from bowlinger.pipeline.preanalysis import summarise
from bowlinger.pipeline.quality import assess_quality


def analyze_video(path: Path, settings: Settings) -> dict:
    info = probe(path)
    audio = inspect_audio(path)
    scan = scan_video(path)
    deliveries, scale = build_deliveries(scan, audio, info["fps"] or 1.0, settings)
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
        "quality": assess_quality(info, settings),
        "preanalysis": summarise(scan, audio),
        "calibration": {
            "method": scale["method"],
            "meters_per_pixel": None if scale["meters_per_pixel"] is None else round(scale["meters_per_pixel"], 6),
            "stump_height_px": None if scale["stump_height_px"] is None else round(scale["stump_height_px"], 2),
        },
        "deliveries": deliveries,
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
