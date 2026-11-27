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
from bowlinger.pipeline.areas import attach_delivery_rules, box_from_center, empty_geometry, lock_stump_box
from bowlinger.pipeline.audio import inspect_audio
from bowlinger.pipeline.deliveries import build_deliveries
from bowlinger.pipeline.detect import scan_video
from bowlinger.pipeline.footage import analyze_footage, footage_texture
from bowlinger.pipeline.preanalysis import summarise
from bowlinger.pipeline.quality import assess_quality
from bowlinger.pipeline.registry import register_analyzer


@register_analyzer("classic")
def analyze_classic(path: Path, settings: Settings, info: dict, audio: dict) -> dict:
    scan = scan_video(path)
    deliveries, scale = build_deliveries(scan, audio, info["fps"] or 1.0, settings)
    preanalysis = summarise(scan, audio)
    tracked_colors = [row["ball_color"] for row in deliveries if row.get("ball_color") in {"red", "white"}]
    if tracked_colors:
        preanalysis["ball_type"] = max(set(tracked_colors), key=tracked_colors.count)
    else:
        # Loose red and white specks are not a ball. Say so instead of voting on them.
        preanalysis["ball_type"] = "unknown"
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
        "preanalysis": preanalysis,
        "calibration": {
            "method": scale["method"],
            "meters_per_pixel": None if scale["meters_per_pixel"] is None else round(scale["meters_per_pixel"], 6),
            "stump_height_px": None if scale["stump_height_px"] is None else round(scale["stump_height_px"], 2),
        },
        "deliveries": deliveries,
        "geometry": _classic_geometry(scan, info, deliveries, audio),
    }


def _classic_geometry(scan: dict, info: dict, deliveries: list[dict], audio: dict) -> dict:
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    sightings = []
    for stump in scan["stumps"]:
        if stump.get("n", 0) < 2 or stump.get("h", 0) < 8:
            continue
        sightings.append(
            {
                "frame": 0,
                "box": box_from_center(stump["x"], stump["y"], max(6.0, float(stump.get("w", 8))), float(stump["h"])),
            }
        )
    stumps = lock_stump_box(sightings, width, height)
    for delivery in deliveries:
        attach_delivery_rules(delivery, stumps.get("box"), None, bool(audio.get("present")))
    geometry = empty_geometry(width, height)
    geometry["stumps"] = stumps
    return geometry


def _use_footage(path: Path, settings: Settings) -> bool:
    if settings.detector == "classic":
        return False
    if settings.detector == "footage":
        return True
    # One textured frame means a camera, not the flat synthetic pitch.
    return footage_texture(path) >= 300


def analyze_video(path: Path, settings: Settings) -> dict:
    info = probe(path)
    audio = inspect_audio(path)
    if _use_footage(path, settings):
        try:
            return analyze_footage(path, settings, info, audio)
        except FileNotFoundError:
            if settings.detector == "yolo":
                raise
            # The configured weights are not on disk. Classic CV is the fallback.
            return analyze_classic(path, settings, info, audio)
    return analyze_classic(path, settings, info, audio)


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
