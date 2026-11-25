"""HTTP application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bowlinger import __version__
from bowlinger.config import Settings
from bowlinger.db import get_session, init_db
from bowlinger.jobs import JobQueue
from bowlinger.pipeline.analyze import process_job
from bowlinger.sessions import accept_video, public_session

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)

    queue = JobQueue(
        settings.db_path,
        lambda job: process_job(settings, job),
        sync=settings.sync_jobs,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        queue.start()
        yield
        queue.stop()

    app = FastAPI(title="BOWLINGER", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.queue = queue

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

    @app.post("/api/sessions", status_code=201)
    async def create_session(
        video: UploadFile = File(...),
        user_key: str | None = Form(None),
    ) -> dict:
        data = await video.read()
        try:
            row = accept_video(
                settings,
                filename=video.filename,
                data=data,
                user_key=user_key,
                source="upload",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        queue.enqueue(row["id"])
        fresh = get_session(settings.db_path, row["id"])
        return public_session(fresh or row)

    @app.get("/api/sessions/{session_id}")
    def read_session(session_id: str) -> dict:
        row = get_session(settings.db_path, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return public_session(row)

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
