"""GB — an upload becomes a background job that can be read back by session id."""

import time

from fastapi.testclient import TestClient

from bowlinger.api import create_app
from bowlinger.synthetic import ClipSpec, write_clip


def _upload(client: TestClient, path, user_key="coach_1"):
    with path.open("rb") as handle:
        return client.post(
            "/api/sessions",
            files={"video": (path.name, handle, "video/mp4")},
            data={"user_key": user_key},
        )


def test_upload_completes_and_a_second_client_can_read_it(settings, tmp_path):
    clip = tmp_path / "bowl.mp4"
    truth = write_clip(clip, ClipSpec(shot="straight drive"))
    with TestClient(create_app(settings)) as client:
        response = _upload(client, clip)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["user_key"] == "coach_1"
    assert body["is_public"] is True
    assert body["result"]["video"]["frame_count"] == truth.frame_count
    assert body["result"]["video"]["fps"] == 50
    assert body["result"]["deliveries"] == []
    with TestClient(create_app(settings)) as other:
        again = other.get(f"/api/sessions/{body['session_id']}")
    assert again.status_code == 200
    assert again.json()["result"]["video"]["width"] == 640


def test_unreadable_video_fails_the_job(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/sessions",
            files={"video": ("bad.mp4", b"this is not a video", "video/mp4")},
            data={"user_key": "coach_1"},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]
    assert body["result"] is None


def test_missing_session_is_404(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404


def test_empty_upload_is_rejected(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/sessions",
            files={"video": ("empty.mp4", b"", "video/mp4")},
            data={"user_key": "coach_1"},
        )
    assert response.status_code == 400


def test_upload_returns_before_a_slow_job_finishes(settings, tmp_path):
    settings.sync_jobs = False
    clip = tmp_path / "slow.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=6, post_frames=4))
    app = create_app(settings)
    original = app.state.queue.handler

    def slow(job):
        time.sleep(1.4)
        original(job)

    app.state.queue.handler = slow
    with TestClient(app) as client:
        started = time.perf_counter()
        response = _upload(client, clip, user_key="coach_slow")
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0
        body = response.json()
        assert body["status"] in {"queued", "running"}
        session_id = body["session_id"]
        deadline = time.time() + 6
        status = body["status"]
        while time.time() < deadline and status not in {"completed", "failed"}:
            time.sleep(0.15)
            status = client.get(f"/api/sessions/{session_id}").json()["status"]
        assert status == "completed"


def test_home_page_offers_upload(settings):
    with TestClient(create_app(settings)) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert "BOWLINGER" in page.text
    assert 'id="video"' in page.text
    assert "/static/app.js" in page.text
