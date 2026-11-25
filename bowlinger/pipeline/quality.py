"""Frame-rate and resolution warnings. Thresholds come from Settings."""

from __future__ import annotations

from bowlinger.config import Settings


def assess_quality(info: dict, settings: Settings) -> dict:
    warnings: list[str] = []
    fps = float(info["fps"])
    height = int(info["height"])
    if fps < settings.min_fps:
        warnings.append(f"Frame rate {fps:.2f} is below {settings.min_fps:g} FPS")
    if height < settings.min_height:
        warnings.append(f"Vertical resolution {height}px is below {settings.min_height}p")
    return {
        "fps": fps,
        "width": int(info["width"]),
        "height": height,
        "frame_count": int(info["frame_count"]),
        "duration_s": round(float(info["duration_s"]), 3),
        "warnings": warnings,
        "passes": not warnings,
    }
