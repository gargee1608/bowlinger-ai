"""Fixed stump box, pitch area, role labels, and the ball-release rule.

These helpers do not replace the existing delivery clock. ``release_time_s``,
``virtual_runs`` and the contact timestamp stay as they are. The new fields
say whether a ball release is accepted, and whether the outcome is a hit,
a miss, or a dead ball.
"""

from __future__ import annotations

import math

STUMP_FRAMES = 5
MIN_BALL_POINTS = 3
YOLO_LABELS = ("ball", "bat", "batsman", "bowler", "fielder", "wicketkeeper", "stumps")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def box_from_center(x: float, y: float, width: float, height: float) -> list[float]:
    return [x - width / 2, y - height / 2, x + width / 2, y + height / 2]


def expand_box(box: list[float], width: int, height: int, fraction: float) -> list[float]:
    """Grow a box by ``fraction`` of its own size on every side, then clamp."""
    x1, y1, x2, y2 = box
    grow_x = max(1.0, (x2 - x1) * fraction)
    grow_y = max(1.0, (y2 - y1) * fraction)
    return [
        max(0.0, x1 - grow_x),
        max(0.0, y1 - grow_y),
        min(float(width), x2 + grow_x),
        min(float(height), y2 + grow_y),
    ]


def point_in_box(x: float, y: float, box: list[float] | None) -> bool:
    if box is None:
        return True
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def box_to_polygon(box: list[float]) -> list[list[float]]:
    """A rectangle is a four-point polygon, clockwise from the top left."""
    x1, y1, x2, y2 = box
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def point_in_polygon(x: float, y: float, polygon: list) -> bool:
    """Even-odd rule. Fewer than three points is not a boundary."""
    if polygon is None or len(polygon) < 3:
        return True
    inside = False
    previous = len(polygon) - 1
    for index, point in enumerate(polygon):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[previous][0]), float(polygon[previous][1])
        if (yi > y) != (yj > y):
            cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < cross:
                inside = not inside
        previous = index
    return inside


def as_polygon(area) -> list[list[float]] | None:
    """Accept a rectangle, a list of points, or a pitch dict with either."""
    if area is None:
        return None
    if isinstance(area, dict):
        if area.get("polygon"):
            return [[float(point[0]), float(point[1])] for point in area["polygon"]]
        if area.get("box"):
            return box_to_polygon(area["box"])
        return None
    if len(area) == 4 and all(isinstance(value, (int, float)) for value in area):
        return box_to_polygon([float(value) for value in area])
    if area and isinstance(area[0], (list, tuple)):
        return [[float(point[0]), float(point[1])] for point in area]
    return None


def _same_as_box(polygon: list[list[float]], box: list[float] | None) -> bool:
    """True when the polygon is just the four corners of that rectangle."""
    if not box or len(polygon) != 4:
        return False
    corners = {(round(point[0], 2), round(point[1], 2)) for point in box_to_polygon(box)}
    return {(round(point[0], 2), round(point[1], 2)) for point in polygon} == corners


def _bounds(polygon: list[list[float]]) -> list[float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def expand_polygon(polygon: list[list[float]], width: int, height: int, fraction: float = 0.15) -> list[list[float]]:
    """Grow every vertex away from the centroid. Used only when events are missing."""
    count = len(polygon)
    cx = sum(point[0] for point in polygon) / count
    cy = sum(point[1] for point in polygon) / count
    grown = []
    for x, y in polygon:
        nx = cx + (x - cx) * (1 + fraction)
        ny = cy + (y - cy) * (1 + fraction)
        if width:
            nx = min(max(0.0, nx), float(width))
        if height:
            ny = min(max(0.0, ny), float(height))
        grown.append([nx, ny])
    return grown


def lock_stump_box(sightings: list[dict], width: int, height: int) -> dict:
    """One stump box from the first five frames. Later sightings cannot move it."""
    early = [item for item in sightings if int(item.get("frame", 0)) < STUMP_FRAMES and "box" in item]
    if not early:
        return {
            "locked": False,
            "fixed": False,
            "source": "missing",
            "manual_required": True,
            "frames_used": STUMP_FRAMES,
            "box": None,
            "expanded_box": None,
            "sightings": 0,
        }
    box = [
        _median([item["box"][0] for item in early]),
        _median([item["box"][1] for item in early]),
        _median([item["box"][2] for item in early]),
        _median([item["box"][3] for item in early]),
    ]
    return {
        "locked": True,
        "fixed": True,
        "source": "detected",
        "manual_required": False,
        "frames_used": STUMP_FRAMES,
        "box": [round(value, 2) for value in box],
        "expanded_box": [round(value, 2) for value in expand_box(box, width, height, 0.5)],
        "sightings": len(early),
    }


def manual_stump_box(box: list[float], width: int, height: int) -> dict:
    clamped = [
        max(0.0, min(float(width), box[0])),
        max(0.0, min(float(height), box[1])),
        max(0.0, min(float(width), box[2])),
        max(0.0, min(float(height), box[3])),
    ]
    ordered = [min(clamped[0], clamped[2]), min(clamped[1], clamped[3]), max(clamped[0], clamped[2]), max(clamped[1], clamped[3])]
    return {
        "locked": True,
        "fixed": True,
        "source": "manual",
        "manual_required": False,
        "frames_used": STUMP_FRAMES,
        "box": [round(value, 2) for value in ordered],
        "expanded_box": [round(value, 2) for value in expand_box(ordered, width, height, 0.5)],
        "sightings": 0,
    }


def box_center(box: list[float] | None) -> tuple[float, float] | None:
    if not box:
        return None
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _distance(point: dict, target: tuple[float, float]) -> float:
    return math.hypot(point["x"] - target[0], point["y"] - target[1])


def _near(box_a: list[float], box_b: list[float], limit: float) -> bool:
    center_a = box_center(box_a)
    center_b = box_center(box_b)
    if center_a is None or center_b is None:
        return False
    ax, ay = center_a
    bx, by = center_b
    gap_x = max(0.0, max(box_a[0], box_b[0]) - min(box_a[2], box_b[2]))
    gap_y = max(0.0, max(box_a[1], box_b[1]) - min(box_a[3], box_b[3]))
    if gap_x == 0 and gap_y == 0:
        return True
    return math.hypot(gap_x, gap_y) <= limit or math.hypot(ax - bx, ay - by) <= limit


def _behind_stumps(person_box: list[float], stump_box: list[float]) -> bool:
    """Behind means just beyond the stump box, still in its horizontal lane."""
    px = (person_box[0] + person_box[2]) / 2
    py = (person_box[1] + person_box[3]) / 2
    stump_h = max(1.0, stump_box[3] - stump_box[1])
    overlaps_x = person_box[0] <= stump_box[2] and person_box[2] >= stump_box[0]
    above = stump_box[1] - 1.8 * stump_h <= py <= stump_box[1]
    below = stump_box[3] <= py <= stump_box[3] + 1.8 * stump_h
    return overlaps_x and (above or below) and stump_box[0] - stump_h <= px <= stump_box[2] + stump_h


def classify_roles(people: list[dict], stump_box: list[float] | None, bat_boxes: list[list[float]]) -> dict:
    """Apply the labelling rules. Model classes are used when they are present.

    ``people`` items: ``label``, ``box``, optional ``has_pads``, ``has_gloves``,
    ``bowling_action``, ``frame``.
    """
    batsman = None
    bowler = None
    keeper = None
    fielders: list[dict] = []
    for person in people:
        label = person.get("label") or "person"
        box = person["box"]
        pads = bool(person.get("has_pads"))
        gloves = bool(person.get("has_gloves"))
        near_stumps = stump_box is not None and _near(box, stump_box, 120)
        with_bat = any(_near(box, bat, 80) for bat in bat_boxes)
        keeper_look = label in {"wicketkeeper", "wicket-keeper"} or gloves
        if keeper is None and stump_box is not None and keeper_look and _behind_stumps(box, stump_box):
            keeper = person
            continue
        if batsman is None and (label == "batsman" or label == "person") and with_bat and near_stumps:
            batsman = person
            continue
        if bowler is None and (label == "bowler" or person.get("bowling_action")) and person.get("bowling_action"):
            bowler = person
            continue
        if label == "bowler" and bowler is None and person.get("bowling_action"):
            bowler = person
            continue
    for person in people:
        if person in (batsman, bowler, keeper):
            continue
        pads = bool(person.get("has_pads"))
        gloves = bool(person.get("has_gloves"))
        label = person.get("label") or "person"
        if pads or gloves:
            continue
        if label in {"fielder", "person"}:
            fielders.append(person)
    return {
        "batsman": _role_row(batsman),
        "bowler": _role_row(bowler),
        "fielder": [_role_row(person) for person in fielders],
        "wicketkeeper": _role_row(keeper),
        "batsman_confirmed": batsman is not None,
    }


def _role_row(person: dict | None) -> dict | None:
    if person is None:
        return None
    return {
        "label": person.get("label"),
        "frame": person.get("frame"),
        "box": person.get("box"),
    }


def batsman_confirmed_before(batsman_frames: list[int], release_frame: int | None) -> bool:
    """The batsman has to be named before a release is looked for."""
    if not batsman_frames:
        return False
    if release_frame is None:
        return True
    return any(frame < release_frame for frame in batsman_frames)


def fill_trajectory(points: list[dict]) -> list[dict]:
    """Fill gaps between detections. A missing frame uses the points on both sides."""
    real = sorted((point for point in points if not point.get("predicted")), key=lambda item: item["frame"])
    if len(real) < 2:
        return [dict(point, predicted=False) for point in real]
    filled: list[dict] = []
    for earlier, later in zip(real, real[1:]):
        filled.append(dict(earlier, predicted=False))
        gap = int(later["frame"]) - int(earlier["frame"])
        for step in range(1, gap):
            mix = step / gap
            filled.append(
                {
                    "frame": int(earlier["frame"]) + step,
                    "x": earlier["x"] + (later["x"] - earlier["x"]) * mix,
                    "y": earlier["y"] + (later["y"] - earlier["y"]) * mix,
                    "predicted": True,
                }
            )
    filled.append(dict(real[-1], predicted=False))
    return filled


def moves_toward(points: list[dict], target: tuple[float, float] | None) -> bool:
    usable = [point for point in points if point.get("x") is not None]
    if target is None or len(usable) < 2:
        return False
    return _distance(usable[-1], target) < _distance(usable[0], target) - 1.0


def assess_release(
    points: list[dict],
    stump_box: list[float] | None,
    *,
    manual_frame: int | None = None,
) -> dict:
    """A release counts only when the ball's path closes on the stumps.

    A manual frame is the release when the model cannot see one. The outcome
    still waits for three ball points after that frame.
    """
    filled = fill_trajectory(points)
    start = manual_frame
    if start is None and filled:
        start = int(filled[0]["frame"])
    after = [point for point in filled if start is not None and point["frame"] >= start]
    real_after = [point for point in after if not point.get("predicted")]
    toward = moves_toward(after, box_center(stump_box))
    enough = len(after) >= MIN_BALL_POINTS
    if manual_frame is not None:
        accepted = True
        source = "manual"
    else:
        accepted = bool(toward and enough and real_after)
        source = "trajectory" if accepted else "none"
    return {
        "accepted": accepted,
        "source": source,
        "manual_required": not accepted and manual_frame is None,
        "frame": start,
        "toward_stumps": toward,
        "points_after_release": len(after),
        "real_points_after_release": len(real_after),
        "min_points": MIN_BALL_POINTS,
        "outcome_ready": enough,
        "identity": "ball-1" if after else None,
        "predicted_points": sum(1 for point in after if point.get("predicted")),
        "points": [{"frame": point["frame"], "x": round(point["x"], 2), "y": round(point["y"], 2), "predicted": bool(point.get("predicted"))} for point in after[:80]],
    }


def ball_outside_pitch(points: list[dict], pitch_area) -> bool:
    """True when any ball point leaves the pitch. A rectangle is a 4-point polygon."""
    polygon = as_polygon(pitch_area)
    if not polygon or len(polygon) < 3:
        return False
    return any(not point_in_polygon(point["x"], point["y"], polygon) for point in points)


def _row_inside(row: dict | None, polygon: list[list[float]] | None) -> dict | None:
    if row is None or not polygon or not row.get("box"):
        return row
    box = row["box"]
    x = (box[0] + box[2]) / 2
    y = (box[1] + box[3]) / 2
    return row if point_in_polygon(x, y, polygon) else None


def filter_roles_to_pitch(roles: dict, polygon: list[list[float]] | None) -> dict:
    """Drop people whose box centre is outside the pitch. Tracking itself is unchanged."""
    if not polygon or len(polygon) < 3:
        return roles
    roles = dict(roles)
    for key in ("batsman", "bowler", "wicketkeeper"):
        roles[key] = _row_inside(roles.get(key), polygon)
    roles["fielder"] = [row for row in (roles.get("fielder") or []) if _row_inside(row, polygon)]
    roles["batsman_confirmed"] = roles.get("batsman") is not None
    return roles


def recheck_pitch(pitch_box: list[float] | None, width: int, height: int, events_found: bool) -> tuple[list[float] | None, bool]:
    """If bowling events are missing, expand the pitch once and look again."""
    if pitch_box is None or events_found:
        return pitch_box, False
    return expand_box(pitch_box, width, height, 0.15), True


def contact_outcome(*, video_hit: bool, dead_ball: bool) -> tuple[str, int]:
    """Hit is 1 virtual outcome run. A miss and a dead ball are 0.

    This is separate from the carry-based ``virtual_runs`` number.
    """
    if dead_ball:
        return "dead_ball", 0
    if video_hit:
        return "hit", 1
    return "miss", 0


def empty_geometry(width: int, height: int) -> dict:
    return {
        "width": width,
        "height": height,
        "stumps": lock_stump_box([], width, height),
        "pitch": {"source": "unset", "box": None, "polygon": None, "fixed": False, "rechecked": False},
        "movement": {"samples": 0, "active_frames": 0, "times_s": []},
        "roles": {
            "batsman": None,
            "bowler": None,
            "fielder": [],
            "wicketkeeper": None,
            "batsman_confirmed": False,
        },
    }


def movement_summary(times_s: list[float]) -> dict:
    return {
        "samples": len(times_s),
        "active_frames": len(times_s),
        "times_s": [round(value, 3) for value in times_s[:12]],
    }


def attach_delivery_rules(delivery: dict, stump_box: list[float] | None, pitch_area, audio_present: bool) -> None:
    """Add release, outcome and area fields. Existing keys are left as they are.

    The pitch only decides the dead-ball flag. Release, contact and
    ``virtual_runs`` still use the track the analyzer already built.
    """
    points = list(delivery.get("ball_points") or [])
    manual_frame = delivery.get("manual_release_frame")
    release = assess_release(points, stump_box, manual_frame=manual_frame)
    if delivery.get("release_frame") is not None and manual_frame is None and not points:
        release["frame"] = delivery["release_frame"]
    polygon = as_polygon(pitch_area)
    inside = [point for point in points if polygon and point_in_polygon(point["x"], point["y"], polygon)]
    delivery["ball_points_inside"] = len(inside) if polygon else None
    if delivery.get("bat_box") and polygon:
        box = delivery["bat_box"]
        delivery["bat_inside_pitch"] = point_in_polygon((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, polygon)
    dead = ball_outside_pitch(points, pitch_area) if release["accepted"] or points else False
    video_hit = bool((delivery.get("contact") or {}).get("video_detected"))
    outcome, outcome_runs = contact_outcome(video_hit=video_hit, dead_ball=dead)
    if release["source"] != "manual" and not release["outcome_ready"] and points:
        delivery["trajectory_outcome"] = "undecided"
    elif not points:
        delivery["trajectory_outcome"] = "undecided"
    else:
        delivery["trajectory_outcome"] = outcome if release["outcome_ready"] or release["source"] == "manual" else "undecided"
    if dead:
        outcome, outcome_runs = "dead_ball", 0
    delivery["ball_release"] = release
    delivery["outcome"] = outcome
    delivery["outcome_runs"] = outcome_runs
    delivery["dead_ball"] = dead
    delivery["audio_analysed"] = bool(audio_present and (video_hit or release["accepted"] or delivery.get("release_time_s") is not None))
    delivery["batsman_confirmed_before_release"] = bool(delivery.get("batsman_confirmed_before_release", False))


def apply_marks(result: dict, marks: dict) -> dict:
    """Use a drawn stump box, pitch box, or a manual release as the reference."""
    video = result.get("video") or {}
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    geometry = result.setdefault("geometry", empty_geometry(width, height))
    if marks.get("stumps"):
        geometry["stumps"] = manual_stump_box([float(value) for value in marks["stumps"]], width, height)
    pitch = geometry.setdefault("pitch", {"source": "unset", "box": None, "polygon": None, "fixed": False, "rechecked": False})
    polygon = None
    if marks.get("pitch_polygon"):
        polygon = [[round(float(point[0]), 2), round(float(point[1]), 2)] for point in marks["pitch_polygon"]]
    elif marks.get("pitch"):
        box = [float(value) for value in marks["pitch"]]
        pitch["box"] = [round(value, 2) for value in box]
        polygon = box_to_polygon(pitch["box"])
    if polygon and len(polygon) >= 3:
        pitch["polygon"] = polygon
        pitch["box"] = [round(value, 2) for value in _bounds(polygon)]
        pitch["source"] = "manual"
        pitch["fixed"] = True
    stump_box = (geometry.get("stumps") or {}).get("box")
    events_found = any(
        (row.get("contact") or {}).get("video_detected") or (row.get("ball_release") or {}).get("accepted")
        for row in result.get("deliveries") or []
    )
    if pitch.get("polygon") and not events_found and not _same_as_box(pitch["polygon"], pitch.get("box")):
        grown = expand_polygon(pitch["polygon"], width, height, 0.15)
        pitch["polygon"] = [[round(point[0], 2), round(point[1], 2)] for point in grown]
        pitch["box"] = [round(value, 2) for value in _bounds(pitch["polygon"])]
        pitch["rechecked"] = True
    else:
        checked, did = recheck_pitch(pitch.get("box"), width, height, events_found or not pitch.get("box"))
        if did and checked is not None:
            pitch["box"] = [round(value, 2) for value in checked]
            pitch["polygon"] = [[round(point[0], 2), round(point[1], 2)] for point in box_to_polygon(pitch["box"])]
            pitch["rechecked"] = True
    if pitch.get("polygon"):
        geometry["roles"] = filter_roles_to_pitch(geometry.get("roles") or {}, pitch["polygon"])
    pitch_area = pitch.get("polygon") or pitch.get("box")
    manual_release = marks.get("release_frame")
    manual_contact = marks.get("contact_frame")
    audio_present = bool((result.get("preanalysis") or {}).get("audio_present"))
    for delivery in result.get("deliveries") or []:
        if manual_release is not None:
            delivery["manual_release_frame"] = int(manual_release)
        if manual_contact is not None:
            contact = delivery.setdefault("contact", {})
            contact["manual_frame"] = int(manual_contact)
            contact["manual_time_s"] = None if not video.get("fps") else round(int(manual_contact) / float(video["fps"]), 3)
        attach_delivery_rules(delivery, stump_box, pitch_area, audio_present)
    result["geometry"] = geometry
    return result
