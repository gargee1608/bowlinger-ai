"""Synthetic cricket clips for tests and the anonymous demo.

The scene is a frontal zoom on the striker's stumps. Colours are flat on
purpose so classic detectors have a known signal. It is not labelled match
footage, and nothing here is imported by the analysis pipeline.

Scale convention: stump uprights are drawn 71px tall, matching the 0.711 m
official stump at 1 cm per pixel. The pipeline is expected to measure that
height itself rather than trust this module.
"""

from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# BGR. Chosen to be separable by broad thresholds, not to match a kit.
OUTFIELD = (45, 120, 40)
PITCH = (170, 195, 205)
STUMP = (245, 245, 245)
JERSEY = (210, 50, 40)
BAT = (35, 85, 165)
BALL_RED = (25, 25, 215)
BALL_WHITE = (245, 245, 245)
SHADOW = (20, 20, 20)

# Shot labels and exit speeds assume the default run model in Settings:
# carry 2.0 s, boundary 60 m, defence under 6 m/s.
#   3.5 m/s -> 7 m  -> 0 (defence)
#   16 m/s  -> 32 m -> 2
#   40 m/s  -> 80 m -> 4, or 6 when lofted
SHOT_CATALOG: dict[str, dict] = {
    "defence": {"speed_mps": 3.5, "angle_deg": 4.0, "lofted": False, "runs": 0, "contact": True, "label": "defence"},
    "straight drive": {"speed_mps": 16.0, "angle_deg": 0.0, "lofted": False, "runs": 2, "contact": True, "label": "straight drive"},
    "cover drive": {"speed_mps": 16.0, "angle_deg": 32.0, "lofted": False, "runs": 2, "contact": True, "label": "cover drive"},
    "cut": {"speed_mps": 16.0, "angle_deg": 75.0, "lofted": False, "runs": 2, "contact": True, "label": "cut"},
    "on drive": {"speed_mps": 16.0, "angle_deg": -32.0, "lofted": False, "runs": 2, "contact": True, "label": "on drive"},
    "pull": {"speed_mps": 16.0, "angle_deg": -80.0, "lofted": False, "runs": 2, "contact": True, "label": "pull"},
    "lofted drive": {"speed_mps": 40.0, "angle_deg": 6.0, "lofted": True, "runs": 6, "contact": True, "label": "straight drive"},
    "ground four": {"speed_mps": 40.0, "angle_deg": 8.0, "lofted": False, "runs": 4, "contact": True, "label": "straight drive"},
    "no shot": {"speed_mps": 0.0, "angle_deg": 0.0, "lofted": False, "runs": 0, "contact": False, "label": "no shot"},
}

STUMP_HEIGHT_PX = 71
BALL_RADIUS = 7
LOFT_PX = 36


@dataclass
class DeliveryTruth:
    release_frame: int
    contact_frame: int | None
    shot: str
    virtual_runs: int
    lofted: bool
    ball_color: str
    occlusion: tuple[int, int] | None
    speed_mps: float
    angle_deg: float


@dataclass
class ClipTruth:
    fps: int
    width: int
    height: int
    frame_count: int
    has_audio: bool
    click_times_s: list[float]
    stump_height_px: int
    deliveries: list[DeliveryTruth]


@dataclass
class _Delivery:
    hold_start: int
    release_frame: int
    contact_frame: int | None
    end_frame: int
    start_xy: tuple[float, float]
    contact_xy: tuple[float, float]
    pre_velocity: tuple[float, float]
    post_velocity: tuple[float, float]
    color: str
    lofted: bool
    occlusion: tuple[int, int] | None
    shot: str
    runs: int
    speed_mps: float
    angle_deg: float


@dataclass
class ClipSpec:
    width: int = 640
    height: int = 480
    fps: int = 50
    shot: str = "cover drive"
    ball_color: str = "red"
    include_audio: bool = False
    audio_offset_s: float = 0.0
    hold_frames: int = 4
    pre_frames: int = 14
    post_frames: int = 8
    occlusion: tuple[int, int] | None = None
    draw_stumps: bool = True
    draw_batsman: bool = True
    draw_bat: bool = True
    sample_rate: int = 22050
    # When set, these shots are laid out one after another with `gap_frames` between them.
    shots: list[str] | None = None
    gap_frames: int = 40
    deliveries: list[_Delivery] = field(default_factory=list)


def _even(value: int) -> int:
    return value if value % 2 == 0 else value + 1


def _layout(width: int, height: int) -> dict:
    stump_h = STUMP_HEIGHT_PX if height >= STUMP_HEIGHT_PX + 40 else max(24, height // 5)
    base_y = int(height * 0.36)
    if base_y - stump_h < 8:
        base_y = stump_h + 8
    cx = width // 2
    return {"cx": cx, "base_y": base_y, "stump_h": stump_h}


def _post_velocity(speed_mps: float, angle_deg: float, fps: int, stump_h: int) -> tuple[float, float]:
    px_per_m = stump_h / 0.711
    mag = speed_mps * px_per_m / fps
    rad = np.deg2rad(angle_deg)
    # angle 0 is back toward the bowler, which is +y in this frontal view.
    return float(mag * np.sin(rad)), float(mag * np.cos(rad))


def _build_delivery(
    spec: ClipSpec,
    shot: str,
    hold_start: int,
    layout: dict,
    occlusion: tuple[int, int] | None,
) -> _Delivery:
    if shot not in SHOT_CATALOG:
        raise KeyError(f"unknown shot {shot!r}")
    info = SHOT_CATALOG[shot]
    start = (float(layout["cx"] - 8), float(spec.height - 28 - BALL_RADIUS))
    contact = (
        float(layout["cx"] + 34),
        float(layout["base_y"] - int(layout["stump_h"] * 0.22)),
    )
    release = hold_start + spec.hold_frames
    pre = max(2, spec.pre_frames)
    # One step per frame, so the ball is already displaced on the release frame.
    pre_velocity = ((contact[0] - start[0]) / pre, (contact[1] - start[1]) / pre)
    contact_frame = release + pre - 1
    if info["contact"]:
        post_velocity = _post_velocity(info["speed_mps"], info["angle_deg"], spec.fps, layout["stump_h"])
        end_frame = contact_frame + spec.post_frames
        drawn_contact = contact_frame
    else:
        post_velocity = pre_velocity
        end_frame = contact_frame + spec.post_frames
        drawn_contact = None
    return _Delivery(
        hold_start=hold_start,
        release_frame=release,
        contact_frame=drawn_contact,
        end_frame=end_frame,
        start_xy=start,
        contact_xy=contact,
        pre_velocity=pre_velocity,
        post_velocity=post_velocity,
        color=spec.ball_color,
        lofted=bool(info["lofted"]),
        occlusion=occlusion,
        shot=str(info["label"]),
        runs=int(info["runs"]),
        speed_mps=float(info["speed_mps"]),
        angle_deg=float(info["angle_deg"]),
    )


def _resolve_deliveries(spec: ClipSpec) -> tuple[list[_Delivery], dict]:
    if spec.width % 2 or spec.height % 2:
        raise ValueError("width and height must be even (yuv420)")
    layout = _layout(spec.width, spec.height)
    if spec.deliveries:
        return list(spec.deliveries), layout
    names = spec.shots or [spec.shot]
    built: list[_Delivery] = []
    cursor = 0
    for index, name in enumerate(names):
        occlusion = spec.occlusion if index == 0 else None
        delivery = _build_delivery(spec, name, cursor, layout, occlusion)
        built.append(delivery)
        cursor = delivery.end_frame + 1 + spec.gap_frames
    return built, layout


def _position(delivery: _Delivery, frame: int) -> tuple[float, float] | None:
    if frame < delivery.hold_start or frame > delivery.end_frame:
        return None
    if frame < delivery.release_frame:
        return delivery.start_xy
    if delivery.contact_frame is None or frame <= delivery.contact_frame:
        steps = frame - delivery.release_frame + 1
        return (
            delivery.start_xy[0] + delivery.pre_velocity[0] * steps,
            delivery.start_xy[1] + delivery.pre_velocity[1] * steps,
        )
    steps = frame - delivery.contact_frame
    return (
        delivery.contact_xy[0] + delivery.post_velocity[0] * steps,
        delivery.contact_xy[1] + delivery.post_velocity[1] * steps,
    )


def _inside(x: float, y: float, width: int, height: int) -> bool:
    return BALL_RADIUS < x < width - BALL_RADIUS and BALL_RADIUS < y < height - BALL_RADIUS


def _draw_stumps(frame: np.ndarray, layout: dict) -> None:
    stump_h = layout["stump_h"]
    base = layout["base_y"]
    cx = layout["cx"]
    width = max(4, stump_h // 14)
    gap = width * 3
    top = base - (stump_h - 1)
    for i in (-1, 0, 1):
        x = int(cx + i * gap - width // 2)
        cv2.rectangle(frame, (x, top), (x + width - 1, base), STUMP, -1, lineType=cv2.LINE_8)


def _draw_batsman(frame: np.ndarray, layout: dict) -> None:
    cx = layout["cx"]
    base = layout["base_y"]
    stump_h = layout["stump_h"]
    x0 = cx + 26
    y0 = base - stump_h + 8
    cv2.rectangle(frame, (x0, y0), (x0 + 30, base - 8), JERSEY, -1, lineType=cv2.LINE_8)
    cv2.rectangle(frame, (x0 + 4, base - 8), (x0 + 12, base + 16), JERSEY, -1, lineType=cv2.LINE_8)
    cv2.rectangle(frame, (x0 + 18, base - 8), (x0 + 26, base + 16), JERSEY, -1, lineType=cv2.LINE_8)


def _draw_bat(frame: np.ndarray, layout: dict) -> None:
    cx = layout["cx"]
    base = layout["base_y"]
    stump_h = layout["stump_h"]
    p1 = (cx + 28, base - int(stump_h * 0.48))
    p2 = (cx + 6, base - int(stump_h * 0.12))
    cv2.line(frame, p1, p2, BAT, 7, lineType=cv2.LINE_8)


def _ball_bgr(color: str) -> tuple[int, int, int]:
    if color == "red":
        return BALL_RED
    if color == "white":
        return BALL_WHITE
    raise ValueError(color)


def render_clip(spec: ClipSpec) -> tuple[list[np.ndarray], np.ndarray | None, ClipTruth]:
    deliveries, layout = _resolve_deliveries(spec)
    if not deliveries:
        raise ValueError("clip has no deliveries")
    frame_count = max(d.end_frame for d in deliveries) + 6
    frames: list[np.ndarray] = []
    for index in range(frame_count):
        frame = np.zeros((spec.height, spec.width, 3), dtype=np.uint8)
        frame[:] = OUTFIELD
        cx = layout["cx"]
        cv2.rectangle(
            frame,
            (cx - 80, layout["base_y"] - 6),
            (cx + 110, spec.height - 16),
            PITCH,
            -1,
            lineType=cv2.LINE_8,
        )
        if spec.draw_stumps:
            _draw_stumps(frame, layout)
        if spec.draw_batsman:
            _draw_batsman(frame, layout)
        if spec.draw_bat:
            _draw_bat(frame, layout)
        for delivery in deliveries:
            pos = _position(delivery, index)
            if pos is None:
                continue
            hidden = delivery.occlusion is not None and delivery.occlusion[0] <= index < delivery.occlusion[1]
            if hidden or not _inside(pos[0], pos[1], spec.width, spec.height):
                continue
            x, y = int(round(pos[0])), int(round(pos[1]))
            if delivery.lofted and delivery.contact_frame is not None and index > delivery.contact_frame:
                cv2.circle(frame, (x, y), 12, SHADOW, -1, lineType=cv2.LINE_8)
                y -= LOFT_PX
                if not _inside(x, y, spec.width, spec.height):
                    continue
            cv2.circle(frame, (x, y), BALL_RADIUS, _ball_bgr(delivery.color), -1, lineType=cv2.LINE_8)
        frames.append(frame)

    clicks: list[float] = []
    audio = None
    if spec.include_audio:
        duration = frame_count / spec.fps
        samples = int(round(duration * spec.sample_rate))
        rng = np.random.default_rng(1)
        audio = rng.normal(0, 0.002, samples).astype(np.float32)
        for delivery in deliveries:
            if delivery.contact_frame is None:
                continue
            when = delivery.contact_frame / spec.fps + spec.audio_offset_s
            if when < 0 or when >= duration:
                continue
            clicks.append(when)
            start = int(when * spec.sample_rate)
            length = int(0.03 * spec.sample_rate)
            end = min(samples, start + length)
            length = end - start
            if length <= 0:
                continue
            env = np.linspace(1.0, 0.0, length, dtype=np.float32)
            tone = np.sin(2 * np.pi * 1800 * np.arange(length) / spec.sample_rate).astype(np.float32)
            audio[start:end] += 0.9 * tone * env

    truth = ClipTruth(
        fps=spec.fps,
        width=spec.width,
        height=spec.height,
        frame_count=frame_count,
        has_audio=spec.include_audio,
        click_times_s=clicks,
        stump_height_px=layout["stump_h"],
        deliveries=[
            DeliveryTruth(
                release_frame=d.release_frame,
                contact_frame=d.contact_frame,
                shot=d.shot,
                virtual_runs=d.runs,
                lofted=d.lofted,
                ball_color=d.color,
                occlusion=d.occlusion,
                speed_mps=d.speed_mps,
                angle_deg=d.angle_deg,
            )
            for d in deliveries
        ],
    )
    return frames, audio, truth


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def write_clip(path: Path, spec: ClipSpec) -> ClipTruth:
    frames, audio, truth = render_clip(spec)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = frames[0].shape[:2]
    raw = b"".join(frame.tobytes() for frame in frames)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(spec.fps),
        "-i",
        "pipe:0",
    ]
    wav_path = None
    if audio is not None:
        wav_path = path.with_suffix(".wav")
        _write_wav(wav_path, audio, spec.sample_rate)
        cmd.extend(["-i", str(wav_path), "-c:a", "aac", "-shortest"])
    cmd.extend(
        [
            "-frames:v",
            str(len(frames)),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ]
    )
    try:
        subprocess.run(cmd, input=raw, check=True)
    finally:
        if wav_path is not None and wav_path.exists():
            wav_path.unlink()
    return truth
