"""Video contact is a sharp change in ball direction beside the bat."""

from __future__ import annotations

import math

NO_AUDIO = "no audio second confirmation"


def _angle_between(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def find_contact(points: list[dict], bat_xy: tuple[float, float] | None, batsman_xy: tuple[float, float] | None) -> dict | None:
    real = [point for point in points if not point["predicted"]]
    best = None
    for index in range(1, len(real) - 1):
        if real[index]["frame"] - real[index - 1]["frame"] > 2:
            continue
        if real[index + 1]["frame"] - real[index]["frame"] > 2:
            continue
        incoming = (
            real[index]["x"] - real[index - 1]["x"],
            real[index]["y"] - real[index - 1]["y"],
        )
        outgoing = (
            real[index + 1]["x"] - real[index]["x"],
            real[index + 1]["y"] - real[index]["y"],
        )
        turn = _angle_between(incoming, outgoing)
        if turn < 28:
            continue
        point = real[index]
        near_bat = bat_xy is not None and math.hypot(point["x"] - bat_xy[0], point["y"] - bat_xy[1]) <= 80
        near_batter = (
            batsman_xy is not None and math.hypot(point["x"] - batsman_xy[0], point["y"] - batsman_xy[1]) <= 110
        )
        if bat_xy is None and batsman_xy is None:
            near = turn >= 45
        else:
            near = near_bat or near_batter
        if not near:
            continue
        if best is None or turn > best["turn_deg"]:
            best = {"frame": int(point["frame"]), "turn_deg": turn, "x": point["x"], "y": point["y"]}
    return best


def audio_confirmation(video_detected: bool, contact_time_s: float | None, audio: dict, window_s: float) -> tuple[str, float | None]:
    if not audio.get("present"):
        return NO_AUDIO, None
    if not video_detected or contact_time_s is None:
        return "not confirmed", None
    onsets = audio.get("onsets_s") or []
    if not onsets:
        return "not confirmed", None
    nearest = min(onsets, key=lambda onset: abs(onset - contact_time_s))
    if abs(nearest - contact_time_s) <= window_s:
        return "confirmed", float(nearest)
    return "not confirmed", float(nearest)
