"""HTTP application."""

from __future__ import annotations

import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from bowlinger import __version__
from bowlinger.auth import COOKIE_NAME, admin_configured, cookie_matches, cookie_token, password_matches
from bowlinger.config import Settings
from bowlinger.db import (
    get_annotation,
    get_session,
    init_db,
    insert_annotation,
    list_annotations,
    list_sessions,
    list_user_sessions,
    set_session_overrides,
    set_session_progress,
    set_session_status,
)
from bowlinger.jobs import JobQueue
from bowlinger.pipeline.analyze import process_job
from bowlinger.pipeline.areas import apply_marks
from bowlinger.sessions import accept_demo, accept_video, public_session
from bowlinger.spectrogram import spectrogram_png, waveform_peaks
from bowlinger.storage import QuotaError, used_bytes
from bowlinger.train_export import export_zip
from bowlinger.youtube import download_youtube, validate_youtube_url

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
    # Start here as well as in lifespan. A skipped ASGI lifespan still serves
    # HTTP, and uploads would stay queued with nobody claiming jobs.
    queue.start()

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
        return {
            "status": "ok",
            "service": "bowlinger",
            "version": __version__,
            "worker": queue.alive(),
        }

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
            "pages": {
                "home": "/",
                "session": "/s/{session_id}",
                "admin": "/admin/history",
                "train": "/train",
                "audio_train": "/train/audio",
            },
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
        except QuotaError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        queue.enqueue(row["id"])
        fresh = get_session(settings.db_path, row["id"])
        return public_session(fresh or row)

    @app.post("/api/demo", status_code=201)
    def create_demo(user_key: str | None = Form(None), shot: str = Form("cover drive")) -> dict:
        try:
            row = accept_demo(settings, user_key=user_key, shot=shot)
        except QuotaError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
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

    @app.get("/api/users/{user_key}")
    def read_user(user_key: str) -> dict:
        sessions = list_user_sessions(settings.db_path, user_key)
        return {
            "user_key": user_key,
            "quota_bytes": settings.quota_bytes,
            "used_bytes": used_bytes(settings, user_key),
            "flush_policy": settings.flush_policy,
            "sessions": [
                {
                    "session_id": row["id"],
                    "status": row["status"],
                    "source": row["source"],
                    "original_name": row["original_name"],
                    "video_bytes": row["video_bytes"],
                    "created_at": row["created_at"],
                }
                for row in sessions
            ],
        }

    @app.post("/api/sessions/youtube", status_code=201)
    def create_youtube_session(url: str = Form(...), user_key: str | None = Form(None)) -> dict:
        try:
            validate_youtube_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            with tempfile.TemporaryDirectory(prefix="bowlinger-yt-") as directory:
                video_path, title = download_youtube(url, Path(directory))
                data = video_path.read_bytes()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not download that YouTube video") from exc
        try:
            row = accept_video(
                settings,
                filename=f"{title}.mp4",
                data=data,
                user_key=user_key,
                source="youtube",
            )
        except QuotaError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        queue.enqueue(row["id"])
        fresh = get_session(settings.db_path, row["id"])
        return public_session(fresh or row)

    @app.post("/api/sessions/{session_id}/marks")
    def save_marks(session_id: str, payload: dict) -> dict:
        row = get_session(settings.db_path, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if not row.get("result_json"):
            raise HTTPException(status_code=409, detail="Analysis has not finished")
        result = json.loads(row["result_json"])
        marks = _marks_from_payload(payload)
        apply_marks(result, marks)
        set_session_overrides(settings.db_path, session_id, _merged_overrides(row.get("overrides_json"), marks))
        set_session_status(
            settings.db_path,
            session_id,
            row["status"],
            error=row.get("error"),
            result_json=json.dumps(result),
        )
        fresh = get_session(settings.db_path, session_id)
        return public_session(fresh or row)

    @app.post("/api/sessions/{session_id}/analyse")
    def analyse_with_areas(session_id: str, payload: dict) -> dict:
        row = get_session(settings.db_path, session_id)
        if row is None or not row.get("video_path"):
            raise HTTPException(status_code=404, detail="Session not found")
        marks = _marks_from_payload(payload)
        set_session_overrides(settings.db_path, session_id, _merged_overrides(row.get("overrides_json"), marks))
        set_session_status(settings.db_path, session_id, "queued", error=None, clear_result=True)
        set_session_progress(settings.db_path, session_id, "Starting", 0)
        queue.enqueue(session_id)
        fresh = get_session(settings.db_path, session_id)
        return public_session(fresh or row)

    @app.get("/api/sessions/{session_id}/video")
    def session_video(session_id: str) -> FileResponse:
        row = _ready_session(settings, session_id)
        path = Path(row["video_path"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Video file is missing")
        return FileResponse(path, media_type="video/mp4", filename=path.name)

    @app.get("/api/sessions/{session_id}/frames/{frame_index}")
    def session_frame(session_id: str, frame_index: int) -> Response:
        row = _ready_session(settings, session_id)
        encoded = _jpeg_frame(Path(row["video_path"]), frame_index)
        return Response(content=encoded, media_type="image/jpeg")

    @app.post("/api/admin/login")
    def admin_login(response: Response, password: str = Form(...)) -> dict:
        if not admin_configured(settings):
            return {"ok": True, "open": True}
        if not password_matches(settings, password):
            raise HTTPException(status_code=401, detail="Wrong password")
        response.set_cookie(
            COOKIE_NAME,
            cookie_token(settings),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 12,
            path="/",
        )
        return {"ok": True}

    @app.get("/api/admin/sessions")
    def admin_sessions(request: Request) -> dict:
        _require_admin(settings, request)
        rows = []
        for row in list_sessions(settings.db_path):
            public = public_session(row)
            rows.append(
                {
                    "session_id": public["session_id"],
                    "status": public["status"],
                    "source": public["source"],
                    "original_name": public["original_name"],
                    "created_at": public["created_at"],
                    "video_bytes": public["video_bytes"],
                    "path": f"/s/{public['session_id']}",
                    "video": f"/api/sessions/{public['session_id']}/video",
                }
            )
        return {"sessions": rows}

    @app.post("/api/train/annotations", status_code=201)
    def save_annotation(request: Request, payload: dict) -> dict:
        _require_admin(settings, request)
        kind = str(payload.get("kind") or "video")
        if kind not in {"video", "audio"}:
            raise HTTPException(status_code=400, detail="kind must be video or audio")
        video_ref = payload.get("video_ref")
        if video_ref is not None:
            video_ref = str(video_ref)[:200]
        annotation_id = insert_annotation(
            settings.db_path,
            kind=kind,
            video_ref=video_ref,
            payload_json=json.dumps(payload),
        )
        return {"id": annotation_id, "kind": kind}

    @app.get("/api/train/annotations")
    def read_annotations(request: Request, kind: str | None = None) -> dict:
        _require_admin(settings, request)
        items = []
        for row in list_annotations(settings.db_path, kind):
            items.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "video_ref": row["video_ref"],
                    "created_at": row["created_at"],
                }
            )
        return {"annotations": items}

    @app.get("/api/train/annotations/{annotation_id}")
    def read_annotation(annotation_id: str, request: Request) -> dict:
        _require_admin(settings, request)
        row = get_annotation(settings.db_path, annotation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Annotation not found")
        return {
            "id": row["id"],
            "kind": row["kind"],
            "video_ref": row["video_ref"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }

    @app.get("/api/train/annotations/{annotation_id}/yolo")
    def download_yolo(annotation_id: str, request: Request) -> Response:
        _require_admin(settings, request)
        row = get_annotation(settings.db_path, annotation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Annotation not found")
        payload = json.loads(row["payload_json"])
        body = export_zip(payload)
        return Response(
            content=body,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{annotation_id}.zip"'},
        )

    @app.get("/api/train/waveform")
    def train_waveform(request: Request, session_id: str) -> dict:
        _require_admin(settings, request)
        row = _ready_session(settings, session_id)
        return waveform_peaks(Path(row["video_path"]))

    @app.get("/api/train/spectrogram")
    def train_spectrogram(request: Request, session_id: str) -> Response:
        _require_admin(settings, request)
        row = _ready_session(settings, session_id)
        return Response(content=spectrogram_png(Path(row["video_path"])), media_type="image/png")

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/s/{session_id}")
    def session_page(session_id: str) -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/admin")
    def admin_home(request: Request):
        return _gated_page(settings, request, "admin.html")

    @app.get("/admin/history")
    def admin_history(request: Request):
        return _gated_page(settings, request, "admin.html")

    @app.get("/train")
    def train_page(request: Request):
        return _gated_page(settings, request, "train.html")

    @app.get("/train/audio")
    def audio_train_page(request: Request):
        return _gated_page(settings, request, "audio.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _require_admin(settings: Settings, request: Request) -> None:
    if not admin_configured(settings):
        return
    if not cookie_matches(settings, request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Admin password required")


def _gated_page(settings: Settings, request: Request, filename: str):
    if admin_configured(settings) and not cookie_matches(settings, request.cookies.get(COOKIE_NAME)):
        return FileResponse(STATIC_DIR / "login.html")
    return FileResponse(STATIC_DIR / filename)


def _ready_session(settings: Settings, session_id: str) -> dict:
    row = get_session(settings.db_path, session_id)
    if row is None or not row.get("video_path"):
        raise HTTPException(status_code=404, detail="Session not found")
    return row


def _marks_from_payload(payload: dict) -> dict:
    box, polygon = _pitch_parts(payload)
    return {
        "stumps": _box(payload.get("stumps")),
        "pitch": box,
        "pitch_polygon": polygon,
        "release_frame": _optional_int(payload.get("release_frame")),
        "contact_frame": _optional_int(payload.get("contact_frame")),
    }


def _merged_overrides(existing: str | None, marks: dict) -> str:
    current = json.loads(existing) if existing else {}
    if marks.get("stumps"):
        current["stumps"] = marks["stumps"]
    if marks.get("pitch_polygon"):
        current["pitch_polygon"] = marks["pitch_polygon"]
        current.pop("pitch", None)
    elif marks.get("pitch"):
        current["pitch"] = marks["pitch"]
        current.pop("pitch_polygon", None)
    if marks.get("release_frame") is not None:
        current["release_frame"] = marks["release_frame"]
    if marks.get("contact_frame") is not None:
        current["contact_frame"] = marks["contact_frame"]
    return json.dumps(current)


def _pitch_parts(payload: dict) -> tuple[list[float] | None, list | None]:
    polygon = _polygon(payload.get("pitch_polygon"))
    raw = payload.get("pitch")
    box = None
    if raw not in (None, ""):
        if _looks_like_box(raw):
            box = _box(raw)
        elif polygon is None:
            polygon = _polygon(raw)
    return box, polygon


def _looks_like_box(value) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(isinstance(item, (int, float)) for item in value)


def _polygon(value) -> list | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list) or len(value) < 3:
        raise HTTPException(status_code=400, detail="A pitch polygon needs at least three points")
    points = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise HTTPException(status_code=400, detail="Each pitch point needs x and y")
        try:
            points.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Each pitch point needs x and y") from exc
    return points


def _box(value) -> list[float] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise HTTPException(status_code=400, detail="A box needs four numbers: x1, y1, x2, y2")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="A box needs four numbers") from exc


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="A frame number must be an integer") from exc


def _jpeg_frame(path: Path, frame_index: int) -> bytes:
    if frame_index < 0:
        raise HTTPException(status_code=400, detail="Frame index cannot be negative")
    capture = cv2.VideoCapture(str(path))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise HTTPException(status_code=404, detail="That frame is not in the video")
    success, encoded = cv2.imencode(".jpg", frame)
    if not success:
        raise HTTPException(status_code=500, detail="Could not encode the frame")
    return encoded.tobytes()
