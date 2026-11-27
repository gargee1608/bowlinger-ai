"""Phone-nets analyzer: a person detector plus motion and impact sound.

YOLO11n supplies people. The striker is the small figure at the far crease.
A delivery is a bat swing (motion around that box) that lines up with an
impact onset, or a swing that follows the bowler's run-up. The ball is only
kept when frame-difference blobs actually travel toward the striker.

This is the ``footage`` analyzer. Flat synthetic clips stay on ``classic``.
Swap the weights or the analyzer name; see the README extension points.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import librosa
import numpy as np

from bowlinger.config import Settings
from bowlinger.media import load_audio
from bowlinger.pipeline.areas import (
    attach_delivery_rules,
    batsman_confirmed_before,
    classify_roles,
    lock_stump_box,
    movement_summary,
)
from bowlinger.pipeline.audio import inspect_audio
from bowlinger.pipeline.detect import detect_stumps, iter_frames
from bowlinger.pipeline.preanalysis import wicket_uprights
from bowlinger.pipeline.quality import assess_quality
from bowlinger.pipeline.registry import register_analyzer
from bowlinger.pipeline.yolo_model import YoloDetector

# Release is a fraction of a second after the bowler's fastest approach,
# which is the visible stride rather than a resolved ball leaving the hand.
RELEASE_AFTER_STRIDE_S = 0.25


def footage_texture(path: Path) -> float:
    """High on a real camera frame, low on the flat synthetic pitch."""
    for index, frame in iter_frames(path):
        if index < 15:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return 0.0


def _boxes(detections) -> list[tuple[float, float, float, float]]:
    return [item.box for item in detections]


def _is_striker(box, width: int, height: int) -> bool:
    x1, y1, x2, y2 = box
    box_h = y2 - y1
    center_x = (x1 + x2) / 2
    return 35 < box_h < 140 and 0.50 * height < y2 < 0.78 * height and 0.28 * width < center_x < 0.92 * width


def _is_bowler(box, height: int) -> bool:
    x1, y1, x2, y2 = box
    return (y2 - y1) > 130 and y2 > 0.70 * height


def _motion_series(path: Path, settings: Settings):
    detector = YoloDetector.for_settings(settings)
    capture = cv2.VideoCapture(str(path))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    grays: list[np.ndarray] = []
    boxes_at: dict[int, dict[str, list[tuple[float, float, float, float]]]] = {}
    role_points: dict[str, list[dict]] = {"ball": [], "bat": [], "stumps": []}
    early_stumps: list[dict] = []
    role_samples: dict[str, list[dict]] = {
        "batsman": [],
        "bowler": [],
        "fielder": [],
        "wicketkeeper": [],
        "pads": [],
        "gloves": [],
    }
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        grays.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if index % 2 == 0:
            grouped = detector.detect(frame)
            # Even a dedicated batsman class can also fire on the bowler. Keep the
            # small figure at the far crease, and the large figure at the near end.
            people = _boxes(grouped.get("person", []))
            striker_pool = _boxes(grouped.get("batsman", [])) + people
            bowler_pool = _boxes(grouped.get("bowler", [])) + people
            strikers = [box for box in striker_pool if _is_striker(box, width, height)]
            bowlers = [box for box in bowler_pool if _is_bowler(box, height)]
            boxes_at[index] = {"striker": strikers, "bowler": bowlers}
            for role in ("ball", "bat", "stumps"):
                for box in _boxes(grouped.get(role, [])):
                    role_points[role].append(
                        {
                            "frame": index,
                            "x": (box[0] + box[2]) / 2,
                            "y": (box[1] + box[3]) / 2,
                            "w": box[2] - box[0],
                            "h": box[3] - box[1],
                            "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                        }
                    )
            if index < 5:
                stump_boxes = _boxes(grouped.get("stumps", []))
                if not stump_boxes:
                    for stump in detect_stumps(frame):
                        stump_boxes.append(
                            (
                                stump["x"] - stump["w"] / 2,
                                stump["y"] - stump["h"] / 2,
                                stump["x"] + stump["w"] / 2,
                                stump["y"] + stump["h"] / 2,
                            )
                        )
                for box in stump_boxes:
                    early_stumps.append(
                        {"frame": index, "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])]}
                    )
            for role in role_samples:
                for box in _boxes(grouped.get(role, []))[:2]:
                    if len(role_samples[role]) < 8:
                        role_samples[role].append(
                            {"frame": index, "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])]}
                        )
        elif index < 5:
            # The tracker samples every second frame. Stumps still use all of the first five.
            grouped_odd = detector.detect(frame)
            for box in _boxes(grouped_odd.get("stumps", [])):
                early_stumps.append({"frame": index, "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])]})
            if not grouped_odd.get("stumps"):
                for stump in detect_stumps(frame):
                    early_stumps.append(
                        {
                            "frame": index,
                            "box": [
                                stump["x"] - stump["w"] / 2,
                                stump["y"] - stump["h"] / 2,
                                stump["x"] + stump["w"] / 2,
                                stump["y"] + stump["h"] / 2,
                            ],
                        }
                    )
        index += 1
    capture.release()

    last_striker = None
    last_bowler = None
    striker_motion: list[tuple[float, float, float]] = []
    bowler_speed: list[tuple[float, float]] = []
    striker_boxes: list[tuple[float, float, float, float, float]] = []
    for frame_index in range(0, index, 2):
        grouped_boxes = boxes_at.get(frame_index, {"striker": [], "bowler": []})
        strikers = grouped_boxes["striker"]
        bowlers = grouped_boxes["bowler"]
        if strikers:
            if last_striker is not None:
                anchor = (last_striker[0] + last_striker[2]) / 2
                chosen = min(strikers, key=lambda box: abs((box[0] + box[2]) / 2 - anchor))
            else:
                # The striker is the smaller of the crease figures, not the bowler.
                chosen = min(strikers, key=lambda box: box[3] - box[1])
            # Ignore a person who has walked into the shot far from the crease.
            if last_striker is not None:
                jump = abs((chosen[0] + chosen[2]) / 2 - (last_striker[0] + last_striker[2]) / 2)
                if jump > 90:
                    chosen = None
            if chosen is not None:
                last_striker = chosen
                striker_boxes.append((frame_index / fps, *chosen))
                x1, y1, x2, y2 = (int(chosen[0] - 40), int(chosen[1] - 60), int(chosen[2] + 55), int(chosen[3] + 10))
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width - 1, x2), min(height - 1, y2)
                if frame_index >= 2 and x2 > x1 and y2 > y1:
                    current = grays[frame_index][y1:y2, x1:x2]
                    previous = grays[frame_index - 2][y1:y2, x1:x2]
                    if current.shape == previous.shape and current.size:
                        diff = cv2.absdiff(current, previous)
                        top = diff[: max(1, diff.shape[0] // 3)]
                        top_ratio = float(top.mean()) / (float(diff.mean()) + 1e-6)
                        striker_motion.append((frame_index / fps, float(diff.mean()), top_ratio))
        if bowlers:
            if last_bowler is not None:
                anchor = (last_bowler[0] + last_bowler[2]) / 2
                bowler = min(bowlers, key=lambda box: abs((box[0] + box[2]) / 2 - anchor))
                speed = (
                    ((bowler[0] + bowler[2]) / 2 - (last_bowler[0] + last_bowler[2]) / 2) ** 2
                    + ((bowler[1] + bowler[3]) / 2 - (last_bowler[1] + last_bowler[3]) / 2) ** 2
                ) ** 0.5
                bowler_speed.append((frame_index / fps, speed))
            last_bowler = bowlers[0] if last_bowler is None else bowler
    return (
        fps,
        width,
        height,
        index,
        striker_motion,
        bowler_speed,
        striker_boxes,
        grays,
        role_points,
        detector.spec,
        early_stumps,
        role_samples,
    )


def _local_peaks(series: list[tuple[float, float]], gap_s: float, percentile: float) -> list[tuple[float, float]]:
    if not series:
        return []
    values = np.array([value for _, value in series])
    threshold = float(np.percentile(values, percentile))
    peaks = []
    for index, (time_s, value) in enumerate(series):
        if value < threshold:
            continue
        window = [series[other][1] for other in range(max(0, index - 3), min(len(series), index + 4))]
        if value >= max(window) and (not peaks or time_s - peaks[-1][0] > gap_s):
            peaks.append((time_s, value))
    return peaks


def _keep_isolated_peaks(peaks: list[tuple[float, float]]) -> list[float]:
    """A cluster of similar swings is practice. One swing that stands out is a shot."""
    if not peaks:
        return []
    ordered = sorted(peaks)
    clusters: list[list[tuple[float, float]]] = [[ordered[0]]]
    for peak in ordered[1:]:
        if peak[0] - clusters[-1][-1][0] <= 6.5:
            clusters[-1].append(peak)
        else:
            clusters.append([peak])
    kept = []
    for cluster in clusters:
        cluster.sort(key=lambda item: item[1], reverse=True)
        if len(cluster) >= 3 and cluster[0][1] < cluster[1][1] * 1.25:
            continue
        kept.append(cluster[0][0])
    return kept


def _contacts(motion, bowler_peaks, onsets) -> list[dict]:
    times = np.array([item[0] for item in motion]) if motion else np.array([])
    values = np.array([item[1] for item in motion]) if motion else np.array([])
    ratios = {round(item[0], 2): item[2] for item in motion}
    candidates: list[tuple[float, str, float]] = []
    motion_peaks = _local_peaks([(item[0], item[1]) for item in motion], 2.0, 88)
    # A real run-up moves the bowler a long way. Walking past the camera does not.
    strides = [(peak, speed) for peak, speed in bowler_peaks if speed >= 30]
    # One fast person in frame is not a bowler who delivers every ball.
    gate_on_stride = len(strides) >= 3
    for onset in onsets:
        if onset < 3.0 or times.size == 0:
            continue
        nearby = values[np.abs(times - onset) < 0.45]
        if not nearby.size or float(nearby.max()) < 3.2:
            continue
        if gate_on_stride and not any(abs(onset - peak) < 2.2 for peak, _speed in strides):
            continue
        candidates.append((float(onset), "audio", float(nearby.max())))
    for time_s, value in motion_peaks:
        if any(0.05 <= time_s - peak <= 1.8 for peak, _speed in strides):
            candidates.append((time_s, "stride", value))
        elif value >= 7.5 or (not gate_on_stride and value >= 5.0):
            # A sharp isolated swing still counts when the bowler is out of frame.
            candidates.append((time_s, "motion", value))
    candidates.sort()
    merged: list[tuple[float, str, float]] = []
    for time_s, source, score in candidates:
        if merged and time_s - merged[-1][0] < 1.6:
            # The impact onset is a sharper clock than the motion peak. Keep it.
            previous_source = merged[-1][1]
            if source == "audio" and previous_source != "audio":
                merged[-1] = (time_s, source, score)
            elif previous_source != "audio" and score > merged[-1][2]:
                merged[-1] = (time_s, source, score)
            continue
        merged.append((time_s, source, score))
    shots = []
    for time_s, source, score in merged:
        if time_s < 3.0:
            continue
        ratio = ratios.get(round(time_s, 2), 0.0)
        # nearest ratio sample
        if times.size:
            ratio = float(motion[int(np.argmin(np.abs(times - time_s)))][2])
        if ratio >= 0.42:
            family = "pull"
        elif ratio >= 0.30:
            family = "drive"
        else:
            family = "defence"
        shots.append({"time_s": time_s, "source": source, "top_ratio": ratio, "shot": family, "score": score})
    return shots


def _bowler_peaks(speed: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return _local_peaks(speed, 2.0, 90)


def _release_for(contact_s: float, bowler_peaks: list[tuple[float, float]]) -> float | None:
    best = None
    best_delay = None
    for peak, _speed in bowler_peaks:
        release = peak + RELEASE_AFTER_STRIDE_S
        delay = contact_s - release
        if 0.05 <= delay <= 1.5 and (best_delay is None or delay < best_delay):
            best = release
            best_delay = delay
    return best


def _ball_track(grays, fps, contact_s, striker_box, width, height) -> list[dict]:
    if striker_box is None:
        return []
    start = max(0, int((contact_s - 0.85) * fps))
    end = min(len(grays) - 1, int((contact_s + 0.1) * fps))
    sx = (striker_box[0] + striker_box[2]) / 2
    sy = (striker_box[1] + striker_box[3]) / 2
    points = []
    for frame_index in range(start + 1, end):
        diff = cv2.absdiff(grays[frame_index], grays[frame_index - 1])
        mask = (diff > 28).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 6 or area > 120:
                continue
            moment = cv2.moments(contour)
            if moment["m00"] == 0:
                continue
            x = moment["m10"] / moment["m00"]
            y = moment["m01"] / moment["m00"]
            # Corridor from the bowler (lower frame) toward the striker.
            if y < sy - 30 or y > height * 0.9 or x < 20 or x > width - 20:
                continue
            distance = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
            if best is None or distance < best[0]:
                best = (distance, x, y)
        if best is not None:
            points.append({"frame": frame_index, "x": best[1], "y": best[2], "predicted": False, "toward": best[0]})
    if len(points) < 5:
        return []
    # Keep a run that gets closer to the striker.
    closing = sum(1 for earlier, later in zip(points, points[1:]) if later["toward"] < earlier["toward"] - 1)
    if closing < 3:
        return []
    return points


def _window(points: list[dict], fps: float, time_s: float, before: float, after: float) -> list[dict]:
    start = (time_s - before) * fps
    end = (time_s + after) * fps
    return [point for point in points if start <= point["frame"] <= end]


def _bat_near(points: list[dict], fps: float, time_s: float, box) -> bool:
    if box is None:
        return False
    center_x = (box[0] + box[2]) / 2
    center_y = (box[1] + box[3]) / 2
    return any((point["x"] - center_x) ** 2 + (point["y"] - center_y) ** 2 < 160**2 for point in _window(points, fps, time_s, 0.45, 0.45))


def _shot_from_bat(points: list[dict], fps: float, time_s: float, box) -> str | None:
    """Rough shot from how the bat moves around the striker. None if the bat is not seen."""
    seen = _window(points, fps, time_s, 0.15, 0.35)
    if len(seen) < 2:
        return None
    seen.sort(key=lambda point: point["frame"])
    dx = seen[-1]["x"] - seen[0]["x"]
    dy = seen[-1]["y"] - seen[0]["y"]
    if abs(dx) < 14 and abs(dy) < 14:
        return "defence"
    if abs(dx) > max(18, abs(dy) * 1.15):
        return "pull"
    return "drive"


def _ball_from_model(points: list[dict], fps: float, time_s: float, box) -> list[dict]:
    window = _window(points, fps, time_s, 0.9, 0.2)
    if len(window) < 4:
        return []
    window.sort(key=lambda point: point["frame"])
    return [{"frame": point["frame"], "x": point["x"], "y": point["y"], "predicted": False} for point in window]


def _stumps_from_model(points: list[dict], fps: float) -> list[dict]:
    buckets: list[dict] = []
    for point in points:
        for bucket in buckets:
            if abs(point["x"] - bucket["x"]) <= 30 and abs(point["y"] - bucket["y"]) <= 36:
                count = bucket["n"] + 1
                bucket["x"] = (bucket["x"] * bucket["n"] + point["x"]) / count
                bucket["y"] = (bucket["y"] * bucket["n"] + point["y"]) / count
                bucket["h"] = (bucket["h"] * bucket["n"] + point["h"]) / count
                bucket["n"] = count
                break
        else:
            buckets.append({"x": point["x"], "y": point["y"], "h": point["h"], "n": 1})
    return [bucket for bucket in buckets if bucket["n"] >= 8]


def _sample_stumps(path: Path) -> list[dict]:
    seen = []
    for index, frame in iter_frames(path):
        if index % 20:
            continue
        seen.extend(detect_stumps(frame))
        if index > 400:
            break
    # Reuse the wicket grouping by pretending each sighting was repeated.
    buckets: list[dict] = []
    for stump in seen:
        for bucket in buckets:
            if abs(stump["x"] - bucket["x"]) <= 18 and abs(stump["y"] - bucket["y"]) <= 24:
                count = bucket["n"] + 1
                bucket["x"] = (bucket["x"] * bucket["n"] + stump["x"]) / count
                bucket["y"] = (bucket["y"] * bucket["n"] + stump["y"]) / count
                bucket["h"] = (bucket["h"] * bucket["n"] + stump["h"]) / count
                bucket["n"] = count
                break
        else:
            buckets.append({"x": stump["x"], "y": stump["y"], "h": stump["h"], "n": 1})
    return [bucket for bucket in buckets if bucket["n"] >= 4]


@register_analyzer("footage")
def analyze_footage(path: Path, settings: Settings, info: dict, audio: dict) -> dict:
    from bowlinger import __version__

    (
        fps,
        _width,
        _height,
        frame_count,
        motion,
        bowler_speed,
        striker_boxes,
        grays,
        role_points,
        model_spec,
        early_stumps,
        role_samples,
    ) = _motion_series(path, settings)
    samples, sample_rate = load_audio(path) or (np.zeros(1, dtype=np.float32), 22050)
    onset_times = []
    if samples.size > sample_rate:
        strength = librosa.onset.onset_strength(y=samples, sr=sample_rate)
        times = librosa.times_like(strength, sr=sample_rate)
        for onset in librosa.onset.onset_detect(y=samples, sr=sample_rate, units="time"):
            index = int(np.argmin(np.abs(times - onset)))
            if float(strength[index]) >= 5.5:
                onset_times.append(float(onset))
    strides = _bowler_peaks(bowler_speed)
    contacts = _contacts(motion, strides, onset_times)
    if model_spec.provides("bat") and role_points["bat"]:
        kept_contacts = []
        for contact in contacts:
            box = None
            if striker_boxes:
                box = min(striker_boxes, key=lambda item: abs(item[0] - contact["time_s"]))[1:]
            # A run-up or an impact keeps the event. A bare motion blip needs a bat in frame.
            if contact["source"] in {"audio", "stride"} or contact["score"] >= 7.5 or _bat_near(
                role_points["bat"], fps, contact["time_s"], box
            ):
                kept_contacts.append(contact)
        if kept_contacts:
            contacts = kept_contacts
    uprights = _stumps_from_model(role_points["stumps"], fps) if model_spec.provides("stumps") else []
    if len(uprights) < 2:
        uprights = _sample_stumps(path)
    grouped = wicket_uprights(
        [{"x": item["x"], "y": item["y"], "h": item["h"], "n": max(8, item["n"] * 5)} for item in uprights],
        frame_count=40,
    )
    # wicket_uprights wants repeated sightings. The sample above already filtered.
    stump_count = len(uprights) if len(uprights) >= 2 else len(grouped)
    if len(uprights) >= 2:
        stump_members = uprights
    else:
        stump_members = grouped
    striker_seen = len(striker_boxes) >= 30
    deliveries = []
    for number, contact in enumerate(contacts, start=1):
        release = _release_for(contact["time_s"], strides)
        box = None
        if striker_boxes:
            box = min(striker_boxes, key=lambda item: abs(item[0] - contact["time_s"]))[1:]
        track = _ball_from_model(role_points["ball"], fps, contact["time_s"], box)
        if len(track) < 4:
            track = _ball_track(grays, fps, contact["time_s"], box, _width, _height)
        shot_name = _shot_from_bat(role_points["bat"], fps, contact["time_s"], box) or contact["shot"]
        shot = "straight drive" if shot_name == "drive" else shot_name
        if shot_name == "defence":
            shot = "defence"
        bat_seen = _bat_near(role_points["bat"], fps, contact["time_s"], box) or not model_spec.provides("bat")
        release_frame = None if release is None else int(round(release * fps))
        batsman_frames = [int(round(item[0] * fps)) for item in striker_boxes]
        deliveries.append(
            {
                "index": number,
                "ball_track_id": f"ball-{number}" if track else None,
                "ball_color": "unknown",
                "release_frame": release_frame,
                "release_time_s": None if release is None else round(release, 3),
                "track_point_count": len(track),
                "ball_points": track[:40],
                "batsman_confirmed_before_release": batsman_confirmed_before(batsman_frames, release_frame),
                "predicted_point_count": 0,
                "occlusion_gaps": [],
                "batsman_detected": striker_seen,
                "bat_detected": bat_seen,
                "contact": {
                    "video_detected": True,
                    "frame": int(round(contact["time_s"] * fps)),
                    "time_s": round(contact["time_s"], 3),
                    "audio_confirmation": "confirmed" if contact["source"] == "audio" else "not confirmed",
                    "audio_onset_time_s": round(contact["time_s"], 3) if contact["source"] == "audio" else None,
                },
                "shot": shot,
                "virtual_runs": 0 if shot == "defence" else None,
                "virtual_runs_detail": {
                    "estimated_distance_m": None,
                    "exit_speed_mps": None,
                    "angle_deg": None,
                    "lofted": contact["shot"] == "pull",
                    "note": "Runs are not estimated: the ball's travel is not resolved in this phone clip.",
                },
                "detector": "footage",
            }
        )
    preanalysis = {
        "stumps_detected": len(stump_members) >= 2,
        "stump_count": len(stump_members),
        "ball_type": "unknown",
        "batsman_on_crease": striker_seen,
        "audio_present": bool(audio["present"]),
        "striker_samples": len(striker_boxes),
        "analyzer": "yolo",
        "model": model_spec.name,
        "weights": model_spec.weights.name,
        "classic_fallback": model_spec.fallback_roles(),
    }
    return {
        "pipeline_version": __version__,
        "detector": "yolo",
        "model": model_spec.name,
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
        "calibration": {"method": "none", "meters_per_pixel": None, "stump_height_px": None},
        "deliveries": deliveries,
        "geometry": _footage_geometry(
            early_stumps,
            role_samples,
            role_points,
            strides,
            grays,
            fps,
            _width,
            _height,
            deliveries,
            bool(audio["present"]),
        ),
    }


def _movement_times(grays, fps: float, outer: list[float]) -> list[float]:
    times: list[float] = []
    step = 8
    x1, y1, x2, y2 = (int(value) for value in outer)
    for index in range(step, len(grays), step):
        diff = cv2.absdiff(grays[index], grays[index - step])
        roi = diff[max(0, y1) : max(0, y2), max(0, x1) : max(0, x2)]
        if roi.size == 0 or float(roi.mean()) < 6.0:
            continue
        times.append(index / fps)
        if len(times) >= 12:
            break
    return times


def _footage_geometry(early_stumps, role_samples, role_points, strides, grays, fps, width, height, deliveries, audio_present):
    stumps = lock_stump_box(early_stumps, width, height)
    people = []
    for sample in role_samples.get("batsman", [])[:1]:
        people.append({"label": "batsman", "box": sample["box"], "frame": sample["frame"], "has_pads": False, "has_gloves": False})
    bowling = bool(strides)
    for sample in role_samples.get("bowler", [])[:1]:
        people.append(
            {
                "label": "bowler",
                "box": sample["box"],
                "frame": sample["frame"],
                "bowling_action": bowling,
                "has_pads": False,
                "has_gloves": False,
            }
        )
    for sample in role_samples.get("fielder", [])[:4]:
        people.append({"label": "fielder", "box": sample["box"], "frame": sample["frame"], "has_pads": False, "has_gloves": False})
    glove_boxes = [sample["box"] for sample in role_samples.get("gloves", [])]
    for sample in role_samples.get("wicketkeeper", [])[:1]:
        gloves = any(
            abs((sample["box"][0] + sample["box"][2]) / 2 - (box[0] + box[2]) / 2) < 80 for box in glove_boxes
        )
        people.append(
            {
                "label": "wicketkeeper",
                "box": sample["box"],
                "frame": sample["frame"],
                "has_gloves": gloves or True,
                "has_pads": False,
            }
        )
    bat_boxes = [point["box"] for point in role_points.get("bat", [])[:6] if point.get("box")]
    roles = classify_roles(people, stumps.get("box"), bat_boxes)
    movement = {"samples": 0, "active_frames": 0, "times_s": []}
    if stumps.get("expanded_box"):
        movement = movement_summary(_movement_times(grays, fps, stumps["expanded_box"]))
    batsman_frame = None if roles.get("batsman") is None else roles["batsman"].get("frame")
    for delivery in deliveries:
        release_frame = delivery.get("release_frame")
        if roles.get("batsman_confirmed") and batsman_frame is not None and release_frame is not None:
            delivery["batsman_confirmed_before_release"] = batsman_frame < release_frame
        else:
            delivery["batsman_confirmed_before_release"] = bool(roles.get("batsman_confirmed") and release_frame is None)
        attach_delivery_rules(delivery, stumps.get("box"), None, audio_present)
    return {
        "width": width,
        "height": height,
        "stumps": stumps,
        "pitch": {"source": "unset", "box": None, "rechecked": False},
        "movement": movement,
        "roles": roles,
    }
