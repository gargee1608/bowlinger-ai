"""G0 — the service skeleton, queue, and synthetic clip tools run locally."""

import cv2
import librosa
import numpy as np

from bowlinger import __version__
from bowlinger.api import create_app
from bowlinger.config import Settings
from bowlinger.db import get_job, init_db
from bowlinger.jobs import JobQueue
from bowlinger.media import load_audio, probe
from bowlinger.synthetic import ClipSpec, write_clip
from fastapi.testclient import TestClient


def test_core_libraries_import():
    assert cv2.__version__
    assert librosa.__version__
    assert __version__ == "0.1.0"


def test_documented_defaults(monkeypatch):
    monkeypatch.delenv("BOWLINGER_QUOTA_BYTES", raising=False)
    monkeypatch.delenv("BOWLINGER_MIN_FPS", raising=False)
    monkeypatch.delenv("BOWLINGER_MIN_HEIGHT", raising=False)
    monkeypatch.delenv("BOWLINGER_FLUSH_POLICY", raising=False)
    settings = Settings.from_env()
    assert settings.quota_bytes == 1_073_741_824
    assert settings.min_fps == 50
    assert settings.min_height == 720
    assert settings.flush_policy == "oldest_first"
    assert settings.audio_confirm_window_s == 0.15


def test_health_and_config(settings):
    client = TestClient(create_app(settings))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["service"] == "bowlinger"
    config = client.get("/api/config").json()
    assert config["quota_bytes"] == 1_073_741_824
    assert config["min_fps"] == 50
    assert config["min_height"] == 720
    assert config["flush_policy"] == "oldest_first"
    assert config["defaults_pending_approval"] is True


def test_sqlite_schema_initialises(settings):
    init_db(settings.db_path)
    import sqlite3

    conn = sqlite3.connect(settings.db_path)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"users", "sessions", "jobs"} <= names


def test_job_queue_completes_and_records_failure(settings):
    init_db(settings.db_path)
    seen: list[str] = []

    def handler(job):
        seen.append(job["session_id"])
        if job["session_id"] == "bad":
            raise RuntimeError("analysis broke")

    queue = JobQueue(settings.db_path, handler, sync=True)
    ok_id = queue.enqueue("good")
    bad_id = queue.enqueue("bad")
    assert seen == ["good", "bad"]
    assert get_job(settings.db_path, ok_id)["status"] == "completed"
    failed = get_job(settings.db_path, bad_id)
    assert failed["status"] == "failed"
    assert "analysis broke" in failed["error"]


def test_synthetic_clip_matches_probe(tmp_path):
    spec = ClipSpec(fps=50, width=640, height=480, include_audio=False, shot="straight drive")
    path = tmp_path / "clip.mp4"
    truth = write_clip(path, spec)
    info = probe(path)
    assert info["width"] == 640
    assert info["height"] == 480
    assert info["fps"] == 50
    assert info["frame_count"] == truth.frame_count
    assert info["has_audio_stream"] is False
    assert truth.deliveries[0].shot == "straight drive"
    assert truth.stump_height_px == 71


def test_synthetic_click_is_an_onset(tmp_path):
    spec = ClipSpec(include_audio=True, shot="cover drive", audio_offset_s=0.0)
    path = tmp_path / "click.mp4"
    truth = write_clip(path, spec)
    info = probe(path)
    assert info["has_audio_stream"] is True
    loaded = load_audio(path)
    assert loaded is not None
    samples, sr = loaded
    onsets = librosa.onset.onset_detect(y=samples, sr=sr, units="time")
    assert len(truth.click_times_s) == 1
    assert onsets.size >= 1
    assert np.min(np.abs(onsets - truth.click_times_s[0])) < 0.08
