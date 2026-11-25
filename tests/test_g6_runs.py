"""G6 — virtual runs per delivery. The number is a straight-line carry, not a fielder model."""

import pytest

from bowlinger.config import Settings
from bowlinger.pipeline.analyze import analyze_video
from bowlinger.pipeline.shot import virtual_runs
from bowlinger.synthetic import SHOT_CATALOG, ClipSpec, write_clip


def test_distance_buckets_follow_the_documented_defaults():
    settings = Settings(db_path=Settings.from_env().db_path, data_dir=Settings.from_env().data_dir)
    assert virtual_runs(3.5, False, settings) == (0, 7.0)
    assert virtual_runs(9.0, False, settings)[0] == 1  # 18 m
    assert virtual_runs(16.0, False, settings) == (2, 32.0)
    assert virtual_runs(25.0, False, settings)[0] == 3  # 50 m
    assert virtual_runs(40.0, False, settings) == (4, 80.0)
    assert virtual_runs(40.0, True, settings) == (6, 80.0)


@pytest.mark.parametrize("shot", ["defence", "straight drive", "lofted drive", "ground four", "no shot"])
def test_clip_runs_match_the_synthetic_delivery(settings, tmp_path, shot):
    path = tmp_path / "runs.mp4"
    truth = write_clip(path, ClipSpec(shot=shot, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["virtual_runs"] == truth.deliveries[0].virtual_runs == SHOT_CATALOG[shot]["runs"]
    assert delivery["virtual_runs_detail"]["lofted"] is truth.deliveries[0].lofted
