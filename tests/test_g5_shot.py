"""G5 — shot names from the exit angle. Synthetic clips only."""

import pytest

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import SHOT_CATALOG, ClipSpec, write_clip


def test_demo_length_cover_drive_stays_a_cover_drive(settings, tmp_path):
    """The anonymous demo uses a shorter clip, which exposed a stump fragment as a ball."""
    path = tmp_path / "demo.mp4"
    truth = write_clip(path, ClipSpec(shot="cover drive", include_audio=True, hold_frames=2, pre_frames=10, post_frames=6))
    result = analyze_video(path, settings)
    delivery = result["deliveries"][0]
    assert result["preanalysis"]["ball_type"] == "red"
    assert delivery["shot"] == truth.deliveries[0].shot == "cover drive"
    assert delivery["virtual_runs"] == 2


@pytest.mark.parametrize("shot", ["defence", "straight drive", "cover drive", "cut", "on drive", "pull", "no shot"])
def test_shot_label(settings, tmp_path, shot):
    path = tmp_path / f"{shot}.mp4"
    truth = write_clip(path, ClipSpec(shot=shot, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["shot"] == truth.deliveries[0].shot == SHOT_CATALOG[shot]["label"]
