"""HTTP application. Routes grow with each platform goal; G0 exposes health and defaults."""

from __future__ import annotations

from fastapi import FastAPI

from bowlinger import __version__
from bowlinger.config import Settings
from bowlinger.db import init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    app = FastAPI(title="BOWLINGER", version=__version__)
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "service": "bowlinger", "version": __version__}

    @app.get("/api/config")
    def config() -> dict:
        return {
            "quota_bytes": settings.quota_bytes,
            "min_fps": settings.min_fps,
            "min_height": settings.min_height,
            "flush_policy": settings.flush_policy,
            "audio_confirm_window_s": settings.audio_confirm_window_s,
            "occlusion_max_gap_s": settings.occlusion_max_gap_s,
            "carry_seconds": settings.carry_seconds,
            "boundary_m": settings.boundary_m,
            "defence_max_mps": settings.defence_max_mps,
            "defaults_pending_approval": True,
        }

    return app
