"""Release is the frame the ball is first moving, not the first frame it is visible."""

from __future__ import annotations


def _hypot(x: float, y: float) -> float:
    return (x * x + y * y) ** 0.5


def release_frame(points: list[dict]) -> int | None:
    real = [point for point in points if not point["predicted"]]
    if not real:
        return None
    if len(real) == 1:
        return int(real[0]["frame"])
    speeds = []
    for earlier, later in zip(real, real[1:]):
        step = max(1, later["frame"] - earlier["frame"])
        speeds.append(_hypot(later["x"] - earlier["x"], later["y"] - earlier["y"]) / step)
    moving = sorted(speed for speed in speeds if speed > 1.5)
    typical = moving[len(moving) // 2] if moving else 0.0
    threshold = max(2.0, 0.4 * typical)
    if speeds[0] >= threshold:
        return int(real[0]["frame"])
    for index, speed in enumerate(speeds):
        if speed >= threshold:
            return int(real[index + 1]["frame"])
    return int(real[0]["frame"])
