"""G3 — bat and batsman flags on the synthetic crease."""

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import ClipSpec, write_clip


def test_bat_and_batsman_are_detected(settings, tmp_path):
    path = tmp_path / "crease.mp4"
    write_clip(path, ClipSpec(shot="defence", include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["batsman_detected"] is True
    assert delivery["bat_detected"] is True


def test_missing_bat_and_batsman_are_reported(settings, tmp_path):
    path = tmp_path / "empty-crease.mp4"
    write_clip(path, ClipSpec(shot="straight drive", draw_bat=False, draw_batsman=False, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["batsman_detected"] is False
    assert delivery["bat_detected"] is False
