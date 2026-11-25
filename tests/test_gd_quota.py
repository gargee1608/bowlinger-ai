"""GD — 1 GB cap, oldest session flushed first, other users left alone."""

from fastapi.testclient import TestClient

from bowlinger.api import create_app
from bowlinger.synthetic import ClipSpec, write_clip


def _post(client, data: bytes, name: str, user_key: str):
    return client.post(
        "/api/sessions",
        files={"video": (name, data, "video/mp4")},
        data={"user_key": user_key},
    )


def test_oldest_session_is_flushed_and_other_user_is_kept(settings, tmp_path):
    clip = tmp_path / "same.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=6, post_frames=4))
    payload = clip.read_bytes()
    settings.quota_bytes = len(payload) * 2
    with TestClient(create_app(settings)) as client:
        other = _post(client, payload, "other.mp4", "other_user")
        assert other.status_code == 201
        first = _post(client, payload, "one.mp4", "keeper")
        second = _post(client, payload, "two.mp4", "keeper")
        third = _post(client, payload, "three.mp4", "keeper")
        assert first.status_code == second.status_code == third.status_code == 201
        assert client.get(f"/api/sessions/{first.json()['session_id']}").status_code == 404
        assert client.get(f"/api/sessions/{second.json()['session_id']}").status_code == 200
        assert client.get(f"/api/sessions/{third.json()['session_id']}").status_code == 200
        assert client.get(f"/api/sessions/{other.json()['session_id']}").status_code == 200
        usage = client.get("/api/users/keeper").json()
        assert usage["used_bytes"] == len(payload) * 2
        assert usage["quota_bytes"] == len(payload) * 2
        assert usage["flush_policy"] == "oldest_first"
        assert [row["original_name"] for row in usage["sessions"]] == ["two.mp4", "three.mp4"]
        page = client.get("/")
        assert "storage-line" in page.text


def test_file_larger_than_the_cap_is_rejected_without_deleting(settings, tmp_path):
    clip = tmp_path / "kept.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=6, post_frames=4))
    payload = clip.read_bytes()
    settings.quota_bytes = len(payload)
    with TestClient(create_app(settings)) as client:
        kept = _post(client, payload, "kept.mp4", "keeper")
        assert kept.status_code == 201
        too_big = _post(client, payload + b"x", "big.mp4", "keeper")
        assert too_big.status_code == 413
        assert "1 GB" in too_big.json()["detail"]
        assert client.get(f"/api/sessions/{kept.json()['session_id']}").status_code == 200
        usage = client.get("/api/users/keeper").json()
        assert usage["used_bytes"] == len(payload)
        assert usage["sessions"][0]["session_id"] == kept.json()["session_id"]
