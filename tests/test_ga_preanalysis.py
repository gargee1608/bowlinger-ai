"""GA — quality warnings and pre-video facts on synthetic clips.

Real match footage was not available in this workspace, so these checks do
not claim on-field accuracy.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from bowlinger.api import create_app
from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import ClipSpec, write_clip

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "Sample"
REAL_CLIPS = [SAMPLE_DIR / "sample_01.mp4", SAMPLE_DIR / "sample_02.mp4"]


def _analyse(tmp_path: Path, settings, spec: ClipSpec):
    path = tmp_path / "clip.mp4"
    write_clip(path, spec)
    return analyze_video(path, settings)


def test_low_resolution_and_low_fps_warn(settings, tmp_path):
    result = _analyse(tmp_path, settings, ClipSpec(fps=25, width=640, height=480, shot="defence", hold_frames=0, pre_frames=8, post_frames=4))
    text = " ".join(result["quality"]["warnings"])
    assert result["quality"]["passes"] is False
    assert "25.00" in text
    assert "480px" in text
    assert "50" in text
    assert "720" in text


def test_threshold_clip_does_not_warn(settings, tmp_path):
    result = _analyse(
        tmp_path,
        settings,
        ClipSpec(fps=50, width=1280, height=720, shot="defence", hold_frames=0, pre_frames=6, post_frames=3),
    )
    assert result["quality"]["warnings"] == []
    assert result["quality"]["passes"] is True
    assert result["quality"]["height"] == 720
    assert result["quality"]["fps"] == 50


def test_preanalysis_on_a_red_ball_with_audio(settings, tmp_path):
    result = _analyse(tmp_path, settings, ClipSpec(ball_color="red", include_audio=True, shot="cover drive"))
    pre = result["preanalysis"]
    assert pre["stumps_detected"] is True
    assert pre["stump_count"] == 3
    assert pre["ball_type"] == "red"
    assert pre["batsman_on_crease"] is True
    assert pre["audio_present"] is True


def test_white_ball_without_audio_or_batsman(settings, tmp_path):
    result = _analyse(
        tmp_path,
        settings,
        ClipSpec(ball_color="white", include_audio=False, draw_batsman=False, shot="pull"),
    )
    pre = result["preanalysis"]
    assert pre["ball_type"] == "white"
    assert pre["batsman_on_crease"] is False
    assert pre["audio_present"] is False
    assert pre["stumps_detected"] is True


def test_session_stores_preanalysis(settings, tmp_path):
    clip = tmp_path / "upload.mp4"
    write_clip(clip, ClipSpec(ball_color="white", include_audio=False, shot="straight drive"))
    with TestClient(create_app(settings)) as client:
        with clip.open("rb") as handle:
            response = client.post(
                "/api/sessions",
                files={"video": ("upload.mp4", handle, "video/mp4")},
                data={"user_key": "reader"},
            )
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["preanalysis"]["ball_type"] == "white"
    assert body["result"]["quality"]["height"] == 480
    assert body["result"]["quality"]["passes"] is False


def test_real_sample_clips_fail_the_quality_bar(settings):
    """FPS and the short side are metadata. Vision is checked against Sample/labels.json."""
    settings.detector = "classic"
    for name in ("sample_01.mp4", "sample_02.mp4"):
        path = SAMPLE_DIR / name
        assert path.is_file(), path
        result = analyze_video(path, settings)
        quality = result["quality"]
        assert 29 <= quality["fps"] <= 31
        assert quality["width"] == 478
        assert quality["height"] == 850
        assert quality["passes"] is False
        warning_text = " ".join(quality["warnings"])
        assert "50" in warning_text
        assert "478px" in warning_text
        assert result["preanalysis"]["audio_present"] is True
