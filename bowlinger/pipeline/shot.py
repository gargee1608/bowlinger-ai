"""Shot name from the exit angle, and virtual runs from a straight-line carry.

Angle 0 points back toward where the ball came from. Positive is to image-right
of that axis. The buckets are the documented defaults, not a trained model.
"""

from __future__ import annotations

import math

from bowlinger.config import Settings


def _unit(vx: float, vy: float) -> tuple[float, float]:
    mag = math.hypot(vx, vy)
    if mag < 1e-6:
        return 0.0, 0.0
    return vx / mag, vy / mag


def exit_angle_deg(incoming: tuple[float, float], outgoing: tuple[float, float]) -> float:
    # Toward the bowler is back along the incoming path.
    axis = _unit(-incoming[0], -incoming[1])
    right = (axis[1], -axis[0])
    along = outgoing[0] * axis[0] + outgoing[1] * axis[1]
    across = outgoing[0] * right[0] + outgoing[1] * right[1]
    return math.degrees(math.atan2(across, along))


def shot_name(angle_deg: float, speed_mps: float | None, settings: Settings) -> str:
    if speed_mps is not None and speed_mps < settings.defence_max_mps:
        return "defence"
    angle = angle_deg
    if abs(angle) < 20:
        return "straight drive"
    if 20 <= angle < 55:
        return "cover drive"
    if 55 <= angle <= 120:
        return "cut"
    if -55 < angle <= -20:
        return "on drive"
    if -120 <= angle <= -55:
        return "pull"
    return "other"


def virtual_runs(speed_mps: float | None, lofted: bool, settings: Settings) -> tuple[int, float | None]:
    if speed_mps is None:
        return 0, None
    distance = speed_mps * settings.carry_seconds
    if speed_mps < settings.defence_max_mps:
        runs = 0
    elif lofted and distance >= settings.boundary_m:
        runs = 6
    elif distance >= settings.boundary_m:
        runs = 4
    elif distance >= 42:
        runs = 3
    elif distance >= 25:
        runs = 2
    elif distance >= 12:
        runs = 1
    else:
        runs = 0
    return runs, distance
