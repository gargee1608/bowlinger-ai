"""Greedy ball tracker. One id survives a short gap; a longer gap starts a new id."""

from __future__ import annotations

from collections import defaultdict


def _hypot(x: float, y: float) -> float:
    return (x * x + y * y) ** 0.5


def _predict(track: dict, frame: int) -> tuple[float, float]:
    last = track["points"][-1]
    step = frame - last["frame"]
    return last["x"] + track["vx"] * step, last["y"] + track["vy"] * step


def _gate(track: dict) -> float:
    # A defensive or lofted shot can turn the ball through more than a frame of the old velocity.
    if not track["has_velocity"]:
        return 260.0
    speed = _hypot(track["vx"], track["vy"])
    return max(180.0, 50.0 + speed * 3.0) * (1.0 + 0.35 * track["misses"])


def _remember(track: dict, det: dict) -> None:
    previous = next((point for point in reversed(track["points"]) if not point["predicted"]), None)
    if previous is not None:
        step = det["frame"] - previous["frame"]
        if step > 0:
            track["vx"] = (det["x"] - previous["x"]) / step
            track["vy"] = (det["y"] - previous["y"]) / step
            track["has_velocity"] = True
    track["points"].append(
        {
            "frame": det["frame"],
            "x": det["x"],
            "y": det["y"],
            "r": det["r"],
            "color": det["color"],
            "lofted": bool(det.get("lofted")),
            "predicted": False,
        }
    )
    track["misses"] = 0


def _drop_trailing_predictions(track: dict) -> None:
    while track["points"] and track["points"][-1]["predicted"]:
        track["points"].pop()


def track_balls(balls: list[dict], frame_count: int, fps: float, max_gap_s: float) -> list[dict]:
    by_frame: dict[int, list[dict]] = defaultdict(list)
    for ball in balls:
        by_frame[int(ball["frame"])].append(ball)
    max_gap = max(2, int(round(max_gap_s * fps)))
    active: list[dict] = []
    finished: list[dict] = []
    next_id = 1

    for frame in range(frame_count):
        detections = by_frame.get(frame, [])
        used: set[int] = set()
        for track in active:
            prediction = _predict(track, frame)
            best_index = None
            best_distance = 1e9
            limit = _gate(track)
            for index, det in enumerate(detections):
                if index in used:
                    continue
                distance = _hypot(det["x"] - prediction[0], det["y"] - prediction[1])
                if distance < best_distance:
                    best_distance = distance
                    best_index = index
            if best_index is not None and best_distance <= limit:
                _remember(track, detections[best_index])
                used.add(best_index)
            else:
                track["misses"] += 1
                last = track["points"][-1]
                track["points"].append(
                    {
                        "frame": frame,
                        "x": prediction[0],
                        "y": prediction[1],
                        "r": last["r"],
                        "color": last["color"],
                        "lofted": False,
                        "predicted": True,
                    }
                )
        still = []
        for track in active:
            if track["misses"] > max_gap:
                _drop_trailing_predictions(track)
                finished.append(track)
            else:
                still.append(track)
        active = still
        for index, det in enumerate(detections):
            if index in used:
                continue
            track = {
                "id": f"ball-{next_id}",
                "points": [],
                "misses": 0,
                "vx": 0.0,
                "vy": 0.0,
                "has_velocity": False,
            }
            next_id += 1
            _remember(track, det)
            active.append(track)

    for track in active:
        _drop_trailing_predictions(track)
        finished.append(track)

    kept = []
    max_span = max(8, int(round(fps * 2.5)))
    for track in finished:
        real = [point for point in track["points"] if not point["predicted"]]
        if len(real) < 5:
            continue
        travel = _hypot(real[-1]["x"] - real[0]["x"], real[-1]["y"] - real[0]["y"])
        span = real[-1]["frame"] - real[0]["frame"]
        # One bowling flight is short. A speck that drifts for most of a clip is not the ball.
        if travel < 15 or span <= 0 or span > max_span:
            continue
        steps = []
        for earlier, later in zip(real, real[1:]):
            step = later["frame"] - earlier["frame"]
            if step > 0:
                steps.append(_hypot(later["x"] - earlier["x"], later["y"] - earlier["y"]) / step)
        if not steps:
            continue
        ordered = sorted(steps)
        median_speed = ordered[len(ordered) // 2]
        if median_speed < 2.5:
            continue
        kept.append(track)
    kept.sort(key=lambda track: track["points"][0]["frame"])
    return kept
