"""Runtime settings.

Values below are documented defaults. They are pending approval — see
Open Decisions in BOWLINGER_V1_GOALS.md. Environment variables override them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else float(raw)


@dataclass
class Settings:
    db_path: Path
    data_dir: Path
    # 1 GB per user key. Oldest session is removed first when this is exceeded.
    quota_bytes: int = 1_073_741_824
    # Quality warnings. A clip at the threshold is accepted without a warning.
    # min_height applies to the shorter side, so a tall portrait phone clip still warns.
    min_fps: float = 50.0
    min_height: int = 720
    flush_policy: str = "oldest_first"
    # Audio onset within this many seconds of the video contact counts as confirmation.
    audio_confirm_window_s: float = 0.15
    # A ball track survives a gap this long before a new id is issued.
    occlusion_max_gap_s: float = 0.35
    # Official stump height and pitch length, used only as scale references.
    stump_height_m: float = 0.711
    pitch_length_m: float = 20.12
    # Virtual-run model: the ball is assumed to carry in a straight line at the
    # measured post-contact speed for this long, then the distance is bucketed.
    carry_seconds: float = 2.0
    boundary_m: float = 60.0
    defence_max_mps: float = 6.0
    sync_jobs: bool = False
    host: str = "0.0.0.0"
    port: int = 8741

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.environ.get("BOWLINGER_DATA", "data")).expanduser()
        db_path = Path(os.environ.get("BOWLINGER_DB", str(data_dir / "bowlinger.db"))).expanduser()
        return cls(
            db_path=db_path,
            data_dir=data_dir,
            quota_bytes=_int("BOWLINGER_QUOTA_BYTES", 1_073_741_824),
            min_fps=_float("BOWLINGER_MIN_FPS", 50.0),
            min_height=_int("BOWLINGER_MIN_HEIGHT", 720),
            flush_policy=os.environ.get("BOWLINGER_FLUSH_POLICY", "oldest_first"),
            audio_confirm_window_s=_float("BOWLINGER_AUDIO_WINDOW_S", 0.15),
            occlusion_max_gap_s=_float("BOWLINGER_OCCLUSION_GAP_S", 0.35),
            carry_seconds=_float("BOWLINGER_CARRY_SECONDS", 2.0),
            boundary_m=_float("BOWLINGER_BOUNDARY_M", 60.0),
            defence_max_mps=_float("BOWLINGER_DEFENCE_MAX_MPS", 6.0),
            sync_jobs=_flag("BOWLINGER_SYNC_JOBS", False),
            host=os.environ.get("BOWLINGER_HOST", "0.0.0.0"),
            port=_int("BOWLINGER_PORT", 8741),
        )
