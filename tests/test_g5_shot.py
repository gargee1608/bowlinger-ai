"""G5 — shot names from the exit angle. Synthetic clips only."""

import pytest

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import SHOT_CATALOG, ClipSpec, write_clip


@pytest.mark.parametrize("shot", ["defence", "straight drive", "cover drive", "cut", "on drive", "pull", "no shot"])
def test_shot_label(settings, tmp_path, shot):
    path = tmp_path / f"{shot}.mp4"
    truth = write_clip(path, ClipSpec(shot=shot, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["shot"] == truth.deliveries[0].shot == SHOT_CATALOG[shot]["label"]
