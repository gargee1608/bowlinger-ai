"""GC — anonymous demo sessions are public and can be opened again by id."""

from fastapi.testclient import TestClient

from bowlinger.api import create_app


def test_upload_without_a_user_key_mints_one_and_is_public(settings, tmp_path):
    from bowlinger.synthetic import ClipSpec, write_clip

    clip = tmp_path / "anon.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=6, post_frames=4))
    with TestClient(create_app(settings)) as client:
        with clip.open("rb") as handle:
            created = client.post("/api/sessions", files={"video": ("anon.mp4", handle, "video/mp4")})
        assert created.status_code == 201
        body = created.json()
        assert body["user_key"].startswith("anon_")
        assert body["is_public"] is True
        opened = client.get(f"/api/sessions/{body['session_id']}")
        assert opened.status_code == 200
        assert opened.json()["user_key"] == body["user_key"]


def test_demo_session_can_be_retrieved_by_id_only(settings):
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/demo", data={"shot": "straight drive"})
        assert created.status_code == 201
        body = created.json()
        assert body["source"] == "demo"
        assert body["status"] == "completed"
        assert body["user_key"].startswith("anon_")
        assert body["result"]["video"]["frame_count"] > 0
        again = client.get(f"/api/sessions/{body['session_id']}")
        assert again.status_code == 200
        assert again.json()["original_name"].startswith("demo-")
        page = client.get(f"/s/{body['session_id']}")
        assert page.status_code == 200
        assert "lookup-id" in page.text
        assert "demo-button" in page.text


def test_unknown_demo_shot_is_rejected(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/demo", data={"shot": "reverse sweep"})
    assert response.status_code == 400


def test_home_links_a_session_path(settings):
    with TestClient(create_app(settings)) as client:
        page = client.get("/s/not-a-real-session")
    assert page.status_code == 200
    assert "Open a saved session id" in page.text
