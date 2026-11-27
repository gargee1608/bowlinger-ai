"""GE–GK: stump lock, pitch, roles, release, YouTube, admin, and training export."""

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from bowlinger.api import create_app
from bowlinger.pipeline.areas import (
    YOLO_LABELS,
    apply_marks,
    assess_release,
    ball_outside_pitch,
    batsman_confirmed_before,
    classify_roles,
    contact_outcome,
    expand_box,
    fill_trajectory,
    lock_stump_box,
    manual_stump_box,
    recheck_pitch,
)
from bowlinger.synthetic import ClipSpec, write_clip
from bowlinger.train_export import yolo_line
from bowlinger.youtube import validate_youtube_url


def test_stump_box_locks_on_the_first_five_frames_and_ignores_later_motion():
    early = {"frame": 2, "box": [10, 20, 30, 80]}
    later = {"frame": 9, "box": [400, 400, 460, 500]}
    locked = lock_stump_box([early, later], 478, 850)
    assert locked["locked"] is True
    assert locked["fixed"] is True
    assert locked["source"] == "detected"
    assert locked["manual_required"] is False
    assert locked["box"][0] == 10
    grown = expand_box(locked["box"], 478, 850, 0.5)
    assert grown[0] < locked["box"][0]
    assert grown[1] < locked["box"][1]
    assert grown[2] > locked["box"][2]
    assert grown[3] > locked["box"][3]
    assert lock_stump_box([later], 478, 850)["manual_required"] is True


def test_manual_stump_box_is_the_reference():
    manual = manual_stump_box([40, 50, 20, 90], 200, 200)
    assert manual["source"] == "manual"
    assert manual["fixed"] is True
    assert manual["box"] == [20.0, 50.0, 40.0, 90.0]
    assert manual["expanded_box"][0] < 20


def test_roles_follow_the_bat_pads_and_keeper_rules():
    stumps = [100, 200, 140, 280]
    people = [
        {"label": "batsman", "box": [90, 190, 170, 320], "frame": 4, "has_pads": True, "has_gloves": False},
        {"label": "bowler", "box": [10, 400, 70, 560], "frame": 30, "bowling_action": True},
        {"label": "fielder", "box": [300, 80, 350, 180], "frame": 10, "has_pads": False, "has_gloves": False},
        {"label": "fielder", "box": [360, 80, 400, 180], "frame": 10, "has_pads": True, "has_gloves": False},
        {"label": "wicketkeeper", "box": [96, 110, 150, 190], "frame": 4, "has_gloves": True},
    ]
    roles = classify_roles(people, stumps, [[150, 200, 190, 280]])
    assert roles["batsman_confirmed"] is True
    assert roles["batsman"]["frame"] == 4
    assert roles["bowler"]["frame"] == 30
    assert roles["wicketkeeper"]["label"] == "wicketkeeper"
    assert [item["frame"] for item in roles["fielder"]] == [10]
    assert batsman_confirmed_before([4], 30) is True
    assert batsman_confirmed_before([40], 30) is False
    assert classify_roles(
        [{"label": "bowler", "box": [0, 0, 10, 10], "bowling_action": False}],
        stumps,
        [],
    )["bowler"] is None


def test_release_must_move_toward_the_stumps_and_needs_three_points():
    stumps = [100, 40, 120, 90]
    toward = [
        {"frame": 10, "x": 100, "y": 200},
        {"frame": 12, "x": 100, "y": 140},
        {"frame": 14, "x": 100, "y": 80},
    ]
    accepted = assess_release(toward, stumps)
    assert accepted["accepted"] is True
    assert accepted["toward_stumps"] is True
    assert accepted["points_after_release"] >= 3
    assert accepted["identity"] == "ball-1"
    away = [
        {"frame": 1, "x": 100, "y": 80},
        {"frame": 2, "x": 100, "y": 140},
        {"frame": 3, "x": 100, "y": 200},
    ]
    rejected = assess_release(away, stumps)
    assert rejected["accepted"] is False
    assert rejected["manual_required"] is True
    filled = fill_trajectory(
        [{"frame": 0, "x": 0, "y": 0}, {"frame": 4, "x": 4, "y": 8}]
    )
    assert [point["frame"] for point in filled] == [0, 1, 2, 3, 4]
    assert filled[2]["predicted"] is True
    manual = assess_release([{"frame": 5, "x": 1, "y": 1}], stumps, manual_frame=5)
    assert manual["accepted"] is True
    assert manual["source"] == "manual"
    assert manual["outcome_ready"] is False


def test_pitch_marks_a_dead_ball_and_rechecks_when_nothing_is_found():
    pitch = [0, 0, 100, 100]
    assert ball_outside_pitch([{"x": 10, "y": 10}, {"x": 150, "y": 10}], pitch) is True
    assert ball_outside_pitch([{"x": 10, "y": 10}], pitch) is False
    assert ball_outside_pitch([{"x": 150, "y": 10}], None) is False
    expanded, did = recheck_pitch(pitch, 200, 200, events_found=False)
    assert did is True
    assert expanded[2] > pitch[2]
    same, skipped = recheck_pitch(pitch, 200, 200, events_found=True)
    assert skipped is False and same == pitch
    assert contact_outcome(video_hit=True, dead_ball=False) == ("hit", 1)
    assert contact_outcome(video_hit=False, dead_ball=False) == ("miss", 0)
    assert contact_outcome(video_hit=True, dead_ball=True) == ("dead_ball", 0)


def test_marks_replace_the_stump_box_without_changing_virtual_runs():
    result = {
        "video": {"width": 200, "height": 200, "fps": 30},
        "preanalysis": {"audio_present": True},
        "geometry": {},
        "deliveries": [
            {
                "virtual_runs": 4,
                "release_frame": 12,
                "release_time_s": 0.4,
                "ball_points": [{"frame": 12, "x": 10, "y": 10}, {"frame": 14, "x": 180, "y": 10}, {"frame": 16, "x": 190, "y": 12}],
                "contact": {"video_detected": True, "time_s": 0.5},
                "batsman_confirmed_before_release": True,
            }
        ],
    }
    apply_marks(result, {"stumps": [40, 40, 70, 100], "pitch": [0, 0, 100, 100]})
    assert result["geometry"]["stumps"]["source"] == "manual"
    assert result["geometry"]["stumps"]["fixed"] is True
    assert result["deliveries"][0]["virtual_runs"] == 4
    assert result["deliveries"][0]["outcome"] == "dead_ball"
    assert result["deliveries"][0]["outcome_runs"] == 0
    assert result["deliveries"][0]["audio_analysed"] is True


def test_youtube_url_must_be_a_youtube_host():
    assert "youtu.be" in validate_youtube_url("https://youtu.be/abcdefghijk")
    for bad in ("https://example.com/watch?v=1", "file:///tmp/x.mp4", "ftp://youtube.com/a"):
        try:
            validate_youtube_url(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_youtube_session_does_not_store_the_url(settings, tmp_path, monkeypatch):
    clip = tmp_path / "source.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=4, post_frames=2))

    def fake_download(url, dest: Path):
        target = dest / "clip.mp4"
        target.write_bytes(clip.read_bytes())
        assert "youtube.com" not in target.name
        return target, "Net session"

    monkeypatch.setattr("bowlinger.api.download_youtube", fake_download)
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/sessions/youtube", data={"url": url, "user_key": "coach_1"})
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "youtube"
    assert body["original_name"] == "Net session.mp4"
    assert url not in json.dumps(body)
    stored = list(Path(settings.data_dir).rglob("*"))
    for path in stored:
        if path.is_file():
            assert url.encode() not in path.read_bytes()
    with TestClient(create_app(settings)) as client:
        rejected = client.post("/api/sessions/youtube", data={"url": "https://example.com/a.mp4"})
    assert rejected.status_code == 400


def test_admin_history_and_training_export(settings, tmp_path):
    settings.admin_password = "net-pass"
    clip = tmp_path / "bowl.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=4, post_frames=2))
    with TestClient(create_app(settings)) as client:
        closed = client.get("/api/admin/sessions")
        assert closed.status_code == 401
        page = client.get("/admin/history")
        assert page.status_code == 200
        assert b"Password" in page.content
        wrong = client.post("/api/admin/login", data={"password": "nope"})
        assert wrong.status_code == 401
        signed = client.post("/api/admin/login", data={"password": "net-pass"})
        assert signed.status_code == 200
        with clip.open("rb") as handle:
            uploaded = client.post("/api/sessions", files={"video": ("bowl.mp4", handle, "video/mp4")}, data={"user_key": "coach_1"})
        session_id = uploaded.json()["session_id"]
        history = client.get("/api/admin/sessions")
        assert history.status_code == 200
        row = history.json()["sessions"][0]
        assert row["path"] == f"/s/{session_id}"
        assert row["session_id"] == session_id
        saved = client.post(
            "/api/train/annotations",
            json={
                "kind": "video",
                "video_ref": session_id,
                "width": 100,
                "height": 100,
                "boxes": [{"frame": 3, "label": "ball", "box": [10, 10, 30, 30]}],
                "events": [{"kind": "release", "frame": 3, "time_s": 0.1}],
            },
        )
        assert saved.status_code == 201
        exported = client.get(f"/api/train/annotations/{saved.json()['id']}/yolo")
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            label = archive.read("labels/000003.txt").decode()
            classes = archive.read("classes.txt").decode().split()
        assert classes == list(YOLO_LABELS)
        assert label.startswith("0 ")
        assert yolo_line("ball", [10, 10, 30, 30], 100, 100).split()[0] == "0"
        audio = client.post(
            "/api/train/annotations",
            json={"kind": "audio", "video_ref": session_id, "audio_marks": [{"time_s": 1.2, "label": "hit", "frame": 36}]},
        )
        assert audio.status_code == 201
        wave = client.get("/api/train/waveform", params={"session_id": session_id})
        assert wave.status_code == 200
        assert "peaks" in wave.json()


def test_session_marks_and_first_frame(settings, tmp_path):
    clip = tmp_path / "bowl.mp4"
    write_clip(clip, ClipSpec(shot="defence", hold_frames=0, pre_frames=4, post_frames=2))
    with TestClient(create_app(settings)) as client:
        with clip.open("rb") as handle:
            uploaded = client.post(
                "/api/sessions",
                files={"video": ("bowl.mp4", handle, "video/mp4")},
                data={"user_key": "coach_1"},
            )
        session_id = uploaded.json()["session_id"]
        frame = client.get(f"/api/sessions/{session_id}/frames/0")
        assert frame.status_code == 200
        assert frame.headers["content-type"] == "image/jpeg"
        marked = client.post(
            f"/api/sessions/{session_id}/marks",
            json={"stumps": [20, 20, 40, 80], "pitch": [0, 0, 640, 360], "release_frame": 4},
        )
        assert marked.status_code == 200
        geometry = marked.json()["result"]["geometry"]
        assert geometry["stumps"]["source"] == "manual"
        assert geometry["stumps"]["fixed"] is True
        assert geometry["pitch"]["source"] == "manual"
