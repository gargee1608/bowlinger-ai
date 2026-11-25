"""Turn a scan into one result row per delivery."""

from __future__ import annotations

import math

from bowlinger.config import Settings
from bowlinger.pipeline.contact import audio_confirmation, find_contact
from bowlinger.pipeline.release import release_frame
from bowlinger.pipeline.shot import exit_angle_deg, shot_name, virtual_runs
from bowlinger.pipeline.track import track_balls


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def calibration(stumps: list[dict], settings: Settings) -> dict:
    usable = [stump for stump in stumps if stump["n"] >= 2 and stump["h"] >= 18]
    if not usable:
        return {"method": "none", "meters_per_pixel": None, "stump_height_px": None}
    height = _median([stump["h"] for stump in usable])
    ys = sorted(stump["y"] for stump in usable)
    if len(usable) >= 4 and ys[-1] - ys[0] > height * 4:
        span = ys[-1] - ys[0]
        return {
            "method": "pitch_length",
            "meters_per_pixel": settings.pitch_length_m / span,
            "stump_height_px": height,
        }
    return {
        "method": "stump_height",
        "meters_per_pixel": settings.stump_height_m / height,
        "stump_height_px": height,
    }


def _center(clusters: list[dict]) -> tuple[float, float] | None:
    if not clusters:
        return None
    chosen = max(clusters, key=lambda item: item["n"])
    return float(chosen["x"]), float(chosen["y"])


def _occlusion_gaps(points: list[dict]) -> list[dict]:
    gaps = []
    start = None
    for point in points:
        if point["predicted"] and start is None:
            start = point["frame"]
        elif not point["predicted"] and start is not None:
            gaps.append({"start_frame": start, "end_frame": point["frame"] - 1})
            start = None
    return gaps


def _mean_step(points: list[dict], start_frame: int, end_frame: int) -> tuple[float, float] | None:
    window = [point for point in points if not point["predicted"] and start_frame <= point["frame"] <= end_frame]
    if len(window) < 2:
        return None
    vxs = []
    vys = []
    for earlier, later in zip(window, window[1:]):
        step = later["frame"] - earlier["frame"]
        if step <= 0:
            continue
        vxs.append((later["x"] - earlier["x"]) / step)
        vys.append((later["y"] - earlier["y"]) / step)
    if not vxs:
        return None
    return sum(vxs) / len(vxs), sum(vys) / len(vys)


def build_deliveries(scan: dict, audio: dict, fps: float, settings: Settings) -> tuple[list[dict], dict]:
    scale = calibration(scan["stumps"], settings)
    tracks = track_balls(scan["balls"], scan["frame_count"], fps, settings.occlusion_max_gap_s)
    bat_xy = _center(scan["bats"])
    batter_xy = _center(scan["batsmen"])
    deliveries = []
    for index, track in enumerate(tracks, start=1):
        points = track["points"]
        real = [point for point in points if not point["predicted"]]
        released = release_frame(points)
        contact = find_contact(points, bat_xy, batter_xy)
        contact_time = None if contact is None else round(contact["frame"] / fps, 3)
        confirmation, onset = audio_confirmation(
            contact is not None,
            contact_time,
            audio,
            settings.audio_confirm_window_s,
        )
        lofted = False
        shot = "no shot"
        runs = 0
        distance = None
        speed = None
        angle = None
        note = None
        if contact is not None:
            incoming = _mean_step(points, contact["frame"] - 3, contact["frame"])
            outgoing = _mean_step(points, contact["frame"], contact["frame"] + 4)
            post = [point for point in real if point["frame"] > contact["frame"]][:6]
            if post:
                lofted = sum(1 for point in post if point["lofted"]) >= max(1, len(post) / 2)
            if incoming and outgoing and scale["meters_per_pixel"]:
                angle = exit_angle_deg(incoming, outgoing)
                speed = math.hypot(*outgoing) * fps * scale["meters_per_pixel"]
                shot = shot_name(angle, speed, settings)
                runs, distance = virtual_runs(speed, lofted, settings)
            elif incoming and outgoing:
                angle = exit_angle_deg(incoming, outgoing)
                shot = shot_name(angle, None, settings)
                note = "No stump scale, so the run estimate is 0"
            else:
                note = "Exit direction was not measured"
        deliveries.append(
            {
                "index": index,
                "ball_track_id": track["id"],
                "release_frame": released,
                "release_time_s": None if released is None else round(released / fps, 3),
                "track_point_count": len(points),
                "predicted_point_count": sum(1 for point in points if point["predicted"]),
                "occlusion_gaps": _occlusion_gaps(points),
                "batsman_detected": batter_xy is not None,
                "bat_detected": bat_xy is not None,
                "contact": {
                    "video_detected": contact is not None,
                    "frame": None if contact is None else contact["frame"],
                    "time_s": contact_time,
                    "audio_confirmation": confirmation,
                    "audio_onset_time_s": None if onset is None else round(onset, 3),
                },
                "shot": shot,
                "virtual_runs": runs,
                "virtual_runs_detail": {
                    "estimated_distance_m": None if distance is None else round(distance, 2),
                    "exit_speed_mps": None if speed is None else round(speed, 2),
                    "angle_deg": None if angle is None else round(angle, 1),
                    "lofted": lofted,
                    "note": note,
                },
            }
        )
    return deliveries, scale
