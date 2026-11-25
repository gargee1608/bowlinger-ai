"""G2 — one ball id survives a short occlusion and a long gap starts another."""

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import ClipSpec, write_clip


def test_occlusion_keeps_the_same_id(settings, tmp_path):
    path = tmp_path / "occluded.mp4"
    truth = write_clip(path, ClipSpec(shot="cover drive", occlusion=(8, 14), include_audio=False))
    deliveries = analyze_video(path, settings)["deliveries"]
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["ball_track_id"] == "ball-1"
    assert delivery["predicted_point_count"] >= 4
    assert {"start_frame": 8, "end_frame": 13} in delivery["occlusion_gaps"]
    assert truth.deliveries[0].occlusion == (8, 14)


def test_two_deliveries_get_two_ids(settings, tmp_path):
    path = tmp_path / "two.mp4"
    write_clip(path, ClipSpec(shots=["cover drive", "pull"], gap_frames=40, include_audio=False))
    deliveries = analyze_video(path, settings)["deliveries"]
    assert [row["ball_track_id"] for row in deliveries] == ["ball-1", "ball-2"]
    assert deliveries[1]["release_frame"] > deliveries[0]["release_frame"]
