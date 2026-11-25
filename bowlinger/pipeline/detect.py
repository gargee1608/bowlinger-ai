"""Classic colour and shape detectors.

Thresholds are broad enough to survive H.264 colour shift on the synthetic
clips. They are not a model of a real broadcast, and real-footage accuracy
is unverified.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def iter_frames(path: Path):
    cap = cv2.VideoCapture(str(path))
    try:
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield index, frame
            index += 1
    finally:
        cap.release()


def _contours(mask: np.ndarray):
    image = np.ascontiguousarray(mask.astype(np.uint8) * 255)
    found = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return found[0]


def detect_stumps(frame: np.ndarray) -> list[dict]:
    blue, green, red = cv2.split(frame)
    white = (red > 210) & (green > 210) & (blue > 210)
    stumps = []
    for contour in _contours(white):
        x, y, width, height = cv2.boundingRect(contour)
        if height < 18 or width > 28 or height / max(width, 1) < 2.8:
            continue
        stumps.append(
            {
                "x": x + width / 2,
                "y": y + height / 2,
                "w": width,
                "h": height,
            }
        )
    return stumps


def _round_blobs(mask: np.ndarray, color: str) -> list[dict]:
    blobs = []
    for contour in _contours(mask):
        area = float(cv2.contourArea(contour))
        if area < 40 or area > 400:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        # H.264 rounds the synthetic ball off; 0.42 still rejects stumps and the bat.
        if circularity < 0.42:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius < 3.5 or radius > 14:
            continue
        blobs.append({"x": float(x), "y": float(y), "r": float(radius), "color": color})
    return blobs


def detect_balls(frame: np.ndarray) -> list[dict]:
    blue, green, red = cv2.split(frame)
    red_mask = (red > 140) & (red > green + 40) & (red > blue + 40)
    white_mask = (red > 210) & (green > 210) & (blue > 210)
    whites = _round_blobs(white_mask, "white")
    reds = []
    for ball in _round_blobs(red_mask, "red"):
        # A white ball picks up a red fringe from chroma subsampling. Keep the white hit.
        if any((ball["x"] - other["x"]) ** 2 + (ball["y"] - other["y"]) ** 2 < 16**2 for other in whites):
            continue
        reds.append(ball)
    # A stump broken by the bat can leave a small white disc. It shares the stump's x.
    stumps = detect_stumps(frame)
    return [ball for ball in reds + whites if not _on_stump(ball, stumps)]


def _on_stump(ball: dict, stumps: list[dict]) -> bool:
    for stump in stumps:
        if abs(ball["x"] - stump["x"]) > 12:
            continue
        top = stump["y"] - stump["h"] / 2 - 6
        bottom = stump["y"] + stump["h"] / 2 + 36
        if top <= ball["y"] <= bottom:
            return True
    return False


def detect_batsmen(frame: np.ndarray) -> list[dict]:
    blue, green, red = cv2.split(frame)
    # Reject near-white uprights. Compression can tint a stump slightly blue.
    jersey = (blue > 140) & (blue > green + 45) & (blue > red + 45) & (red < 150)
    people = []
    for contour in _contours(jersey):
        area = float(cv2.contourArea(contour))
        if area < 180:
            continue
        x, y, width, height = cv2.boundingRect(contour)
        people.append({"x": x + width / 2, "y": y + height / 2, "w": width, "h": height, "area": area})
    return people


def detect_bats(frame: np.ndarray) -> list[dict]:
    blue, green, red = cv2.split(frame)
    wood = (red > 100) & (red < 220) & (green > 40) & (green < 160) & (blue < 110) & (red > green + 15)
    bats = []
    for contour in _contours(wood):
        if len(contour) < 5:
            continue
        area = float(cv2.contourArea(contour))
        if area < 60:
            continue
        (cx, cy), (rw, rh), _angle = cv2.minAreaRect(contour)
        long_side = max(rw, rh)
        short_side = max(1.0, min(rw, rh))
        if long_side < 18 or long_side / short_side < 2.0:
            continue
        bats.append({"x": float(cx), "y": float(cy), "w": float(rw), "h": float(rh), "area": area})
    return bats


def shadow_below(frame: np.ndarray, x: float, y: float, radius: float) -> bool:
    """A lofted ball is drawn above a dark ground shadow. Compare with the local background."""
    height, width = frame.shape[:2]
    y1 = max(0, int(y + max(8, radius)))
    y2 = min(height, int(y + 70))
    x1 = max(0, int(x - 18))
    x2 = min(width, int(x + 18))
    if y2 - y1 < 8 or x2 - x1 < 8:
        return False
    roi = frame[y1:y2, x1:x2].mean(axis=2)
    background = float(np.median(roi))
    dark = roi < background - 35
    return float(dark.mean()) > 0.04


def _cluster(points: list[dict], radius: float) -> list[dict]:
    clusters: list[dict] = []
    for point in points:
        for cluster in clusters:
            if (point["x"] - cluster["x"]) ** 2 + (point["y"] - cluster["y"]) ** 2 <= radius**2:
                count = cluster["n"] + 1
                cluster["x"] = (cluster["x"] * cluster["n"] + point["x"]) / count
                cluster["y"] = (cluster["y"] * cluster["n"] + point["y"]) / count
                if "h" in point:
                    cluster["h"] = (cluster["h"] * cluster["n"] + point["h"]) / count
                cluster["n"] = count
                break
        else:
            clusters.append(
                {
                    "x": point["x"],
                    "y": point["y"],
                    "h": point.get("h", 0.0),
                    "n": 1,
                }
            )
    return clusters


def scan_video(path: Path) -> dict:
    balls: list[dict] = []
    stump_points: list[dict] = []
    people: list[dict] = []
    bats: list[dict] = []
    frame_count = 0
    for index, frame in iter_frames(path):
        frame_count = index + 1
        for ball in detect_balls(frame):
            ball["frame"] = index
            ball["lofted"] = shadow_below(frame, ball["x"], ball["y"], ball["r"])
            balls.append(ball)
        if index % 2 == 0:
            stump_points.extend(detect_stumps(frame))
            people.extend(detect_batsmen(frame))
            bats.extend(detect_bats(frame))
    return {
        "frame_count": frame_count,
        "balls": balls,
        "stumps": _cluster(stump_points, 14),
        "batsmen": _cluster(people, 30),
        "bats": _cluster(bats, 24),
    }
