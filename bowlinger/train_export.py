"""Turn saved boxes into a YOLO label set."""

from __future__ import annotations

import io
import json
import zipfile

from bowlinger.pipeline.areas import YOLO_LABELS


def yolo_line(label: str, box: list[float], width: float, height: float) -> str | None:
    if label not in YOLO_LABELS or width <= 0 or height <= 0 or len(box) != 4:
        return None
    x1, y1, x2, y2 = box
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    box_w = max(0.0, right - left)
    box_h = max(0.0, bottom - top)
    if box_w <= 0 or box_h <= 0:
        return None
    cx = (left + box_w / 2) / width
    cy = (top + box_h / 2) / height
    class_id = YOLO_LABELS.index(label)
    return f"{class_id} {cx:.6f} {cy:.6f} {box_w / width:.6f} {box_h / height:.6f}"


def export_zip(payload: dict) -> bytes:
    width = float(payload.get("width") or 0)
    height = float(payload.get("height") or 0)
    frames: dict[int, list[str]] = {}
    for box in payload.get("boxes") or []:
        line = yolo_line(str(box.get("label")), list(box.get("box") or []), width, height)
        if line is None:
            continue
        frames.setdefault(int(box.get("frame") or 0), []).append(line)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("classes.txt", "\n".join(YOLO_LABELS) + "\n")
        archive.writestr(
            "events.json",
            json.dumps(
                {
                    "video_ref": payload.get("video_ref"),
                    "fps": payload.get("fps"),
                    "events": payload.get("events") or [],
                    "audio_marks": payload.get("audio_marks") or [],
                },
                indent=2,
            ),
        )
        for frame, lines in sorted(frames.items()):
            archive.writestr(f"labels/{frame:06d}.txt", "\n".join(lines) + "\n")
        if not frames:
            archive.writestr("labels/README.txt", "No boxes were stored with this annotation.\n")
    return buffer.getvalue()
