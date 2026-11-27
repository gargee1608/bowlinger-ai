"""Uploads must leave the queue. A dead worker used to leave them queued forever."""

import time

from fastapi.testclient import TestClient

from bowlinger.api import create_app
from bowlinger.db import (
    create_job,
    finish_job,
    get_job,
    get_session,
    init_db,
    insert_session,
    requeue_interrupted_jobs,
    surface_orphaned_session_failures,
)
from bowlinger.sessions import accept_video
from bowlinger.synthetic import ClipSpec, write_clip


def _wait(settings, session_id: str, timeout: float = 6):
    deadline = time.time() + timeout
    row = get_session(settings.db_path, session_id)
    while time.time() < deadline:
        row = get_session(settings.db_path, session_id)
        if row and row["status"] in {"completed", "failed"}:
            return row
        time.sleep(0.05)
    return row


def test_background_upload_reaches_completed_without_a_pitch(settings, tmp_path):
    settings.sync_jobs = False
    clip = tmp_path / "bowl.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=4, post_frames=2))
    app = create_app(settings)
    assert app.state.queue.alive()
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.json()["worker"] is True
        with clip.open("rb") as handle:
            response = client.post(
                "/api/sessions",
                files={"video": ("bowl.mp4", handle, "video/mp4")},
                data={"user_key": "coach_1"},
            )
        assert response.status_code == 201
        session_id = response.json()["session_id"]
        deadline = time.time() + 6
        body = response.json()
        while time.time() < deadline and body["status"] not in {"completed", "failed"}:
            time.sleep(0.05)
            body = client.get(f"/api/sessions/{session_id}").json()
    assert body["status"] == "completed"
    assert body["result"]["deliveries"] is not None
    assert body["result"]["geometry"]["pitch"]["source"] == "unset"


def test_worker_failure_is_failed_not_queued_and_the_next_job_runs(settings, tmp_path):
    settings.sync_jobs = False
    clip = tmp_path / "bowl.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=4, post_frames=2))
    app = create_app(settings)
    queue = app.state.queue
    original = queue.handler
    state = {"fail": True}

    def handler(job):
        if state["fail"]:
            state["fail"] = False
            raise RuntimeError("worker exploded")
        original(job)

    queue.handler = handler
    try:
        first = accept_video(settings, filename="bowl.mp4", data=clip.read_bytes(), user_key="coach_1")
        queue.enqueue(first["id"])
        failed = _wait(settings, first["id"])
        assert failed["status"] == "failed"
        assert "worker exploded" in failed["error"]

        second = accept_video(settings, filename="bowl.mp4", data=clip.read_bytes(), user_key="coach_1")
        queue.enqueue(second["id"])
        done = _wait(settings, second["id"])
        assert done["status"] == "completed"
    finally:
        queue.stop()


def test_a_job_left_running_is_claimed_again(settings):
    init_db(settings.db_path)
    insert_session(
        settings.db_path,
        session_id="stuck",
        user_id="coach_1",
        source="upload",
        original_name="clip.mp4",
        video_path="/tmp/missing.mp4",
        video_bytes=1,
    )
    from bowlinger.db import ensure_user

    ensure_user(settings.db_path, "coach_1")
    job_id = create_job(settings.db_path, "stuck")
    from bowlinger.db import connect, utcnow

    with connect(settings.db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
            (utcnow(), job_id),
        )
    assert requeue_interrupted_jobs(settings.db_path) == 1
    assert get_job(settings.db_path, job_id)["status"] == "queued"
    assert get_session(settings.db_path, "stuck")["status"] == "queued"


def test_a_failed_job_no_longer_leaves_the_session_queued(settings):
    init_db(settings.db_path)
    from bowlinger.db import ensure_user

    ensure_user(settings.db_path, "coach_1")
    insert_session(
        settings.db_path,
        session_id="quiet",
        user_id="coach_1",
        source="upload",
        original_name="clip.mp4",
        video_path="/tmp/missing.mp4",
        video_bytes=1,
    )
    job_id = create_job(settings.db_path, "quiet")
    finish_job(settings.db_path, job_id, "failed", error="worker exploded\ntraceback")
    assert get_session(settings.db_path, "quiet")["status"] == "queued"
    assert surface_orphaned_session_failures(settings.db_path) == 1
    row = get_session(settings.db_path, "quiet")
    assert row["status"] == "failed"
    assert row["error"] == "worker exploded"
