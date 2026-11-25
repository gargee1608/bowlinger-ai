"""G1 — release is the frame the ball starts moving. Synthetic clips only."""

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.synthetic import ClipSpec, write_clip


def test_release_ignores_the_held_ball(settings, tmp_path):
    path = tmp_path / "held.mp4"
    truth = write_clip(path, ClipSpec(shot="straight drive", hold_frames=4, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["release_frame"] == truth.deliveries[0].release_frame
    assert delivery["release_time_s"] == round(truth.deliveries[0].release_frame / truth.fps, 3)


def test_release_is_the_first_frame_when_the_ball_is_already_moving(settings, tmp_path):
    path = tmp_path / "moving.mp4"
    truth = write_clip(path, ClipSpec(shot="cover drive", hold_frames=0, include_audio=False))
    delivery = analyze_video(path, settings)["deliveries"][0]
    assert delivery["release_frame"] == truth.deliveries[0].release_frame == 0
