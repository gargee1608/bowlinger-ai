"""Read container metadata with ffprobe, falling back to OpenCV."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np


def _rate(text: str | None) -> float:
    if not text or text in {"0/0", "N/A"}:
        return 0.0
    if "/" not in text:
        try:
            return float(text)
        except ValueError:
            return 0.0
    num, den = text.split("/", 1)
    try:
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except ValueError:
        return 0.0


def _count_frames(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    try:
        reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if reported > 0:
            return reported
        count = 0
        while True:
            ok, _frame = cap.read()
            if not ok:
                break
            count += 1
        return count
    finally:
        cap.release()


def probe(path: Path) -> dict:
    """Return fps, size, frame count, duration, and whether an audio stream exists."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")

    payload = json.loads(proc.stdout or "{}")
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("no video stream")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    fps = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    nb = video.get("nb_frames")
    try:
        frame_count = int(nb) if nb not in (None, "N/A") else 0
    except (TypeError, ValueError):
        frame_count = 0
    if frame_count <= 0:
        frame_count = _count_frames(path)

    duration = 0.0
    raw_duration = video.get("duration") or (payload.get("format") or {}).get("duration")
    if raw_duration not in (None, "N/A"):
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = 0.0
    if duration <= 0 and fps > 0 and frame_count > 0:
        duration = frame_count / fps

    if fps <= 0 or width <= 0 or height <= 0 or frame_count <= 0:
        cap = cv2.VideoCapture(str(path))
        try:
            if fps <= 0:
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            if width <= 0:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            if height <= 0:
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            cap.release()

    return {
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_s": duration,
        "has_audio_stream": has_audio,
    }


def load_audio(path: Path, sample_rate: int = 22050) -> tuple[np.ndarray, int] | None:
    """Decode the audio track to mono float32. None when the file has no audio stream.

    librosa/soundfile do not read AAC inside mp4, so ffmpeg does the decode.
    """
    if not probe(path)["has_audio_stream"]:
        return None
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "audio decode failed")
    samples = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    return samples, sample_rate
