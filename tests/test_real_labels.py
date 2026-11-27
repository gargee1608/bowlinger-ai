"""Real deliveries labelled by watching the two phone clips. See Sample/labels.json."""

import json
from pathlib import Path

from bowlinger.pipeline.analyze import analyze_video

ROOT = Path(__file__).resolve().parents[1]
LABELS = json.loads((ROOT / "Sample" / "labels.json").read_text())
TOLERANCE = LABELS["tolerance"]
FAMILIES = LABELS["shot_families"]


def _family(shot: str) -> str:
    for name, members in FAMILIES.items():
        if shot in members:
            return name
    return shot


def _match(predicted: list[dict], time_s: float, field: str, tolerance: float):
    best = None
    best_delta = None
    for row in predicted:
        if field == "release":
            value = row.get("release_time_s")
        else:
            value = (row.get("contact") or {}).get("time_s")
        if value is None:
            continue
        delta = abs(value - time_s)
        if best_delta is None or delta < best_delta:
            best, best_delta = row, delta
    if best is None or best_delta > tolerance:
        return None
    return best


def test_labelled_deliveries_are_found(settings):
    settings.detector = "footage"
    for clip in LABELS["clips"]:
        result = analyze_video(ROOT / clip["file"], settings)
        assert result["detector"] == "yolo"
        if (ROOT / "models" / "cricket.pt").is_file():
            assert result["model"] == "cricket"
        assert result["preanalysis"]["batsman_on_crease"] is clip["scene"]["striker_visible"]
        assert result["preanalysis"]["audio_present"] is clip["scene"]["audio"]
        if clip["scene"]["near_wicket_visible"]:
            assert result["preanalysis"]["stumps_detected"] is True
        deliveries = result["deliveries"]
        for label in clip["deliveries"]:
            if label["contact_s"] is not None:
                found = _match(deliveries, label["contact_s"], "contact", TOLERANCE["contact_s"])
                assert found is not None, f"{label['id']} contact {label['contact_s']} not in {[row['contact']['time_s'] for row in deliveries]}"
                assert found["batsman_detected"] is True
                if label["outcome"] == "hit":
                    assert found["contact"]["video_detected"] is True
            if label["release_s"] is not None:
                found = _match(deliveries, label["release_s"], "release", TOLERANCE["release_s"])
                assert found is not None, f"{label['id']} release {label['release_s']} not in {[row['release_time_s'] for row in deliveries]}"
            if label["expected_runs"] is not None:
                found = _match(deliveries, label["contact_s"], "contact", TOLERANCE["contact_s"])
                assert found["virtual_runs"] == label["expected_runs"]
        geometry = result["geometry"]
        stumps = geometry["stumps"]
        assert stumps["frames_used"] == 5
        assert stumps["source"] in {"detected", "manual", "missing"}
        if stumps["source"] == "detected":
            assert stumps["fixed"] is True
            assert stumps["locked"] is True
            assert stumps["expanded_box"] is not None
        else:
            assert stumps["manual_required"] is True
        assert "movement" in geometry
        assert "roles" in geometry
        for row in deliveries:
            assert row["outcome"] in {"hit", "miss", "dead_ball"}
            assert row["outcome_runs"] == (1 if row["outcome"] == "hit" else 0)
            assert "ball_release" in row
            if row["outcome"] == "hit":
                assert row["contact"]["video_detected"] is True
