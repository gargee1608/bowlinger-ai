"""G4 — video contact, with audio only as a second confirmation."""

from bowlinger.pipeline.analyze import analyze_video
from bowlinger.pipeline.contact import NO_AUDIO
from bowlinger.synthetic import ClipSpec, write_clip


def _delivery(tmp_path, settings, **spec):
    path = tmp_path / "contact.mp4"
    truth = write_clip(path, ClipSpec(**spec))
    return analyze_video(path, settings)["deliveries"][0], truth


def test_audio_confirms_a_video_contact(settings, tmp_path):
    delivery, truth = _delivery(tmp_path, settings, shot="cover drive", include_audio=True)
    contact = delivery["contact"]
    assert contact["video_detected"] is True
    assert contact["frame"] == truth.deliveries[0].contact_frame
    assert contact["audio_confirmation"] == "confirmed"
    assert abs(contact["audio_onset_time_s"] - truth.click_times_s[0]) < 0.08


def test_audio_outside_the_window_is_not_confirmed(settings, tmp_path):
    delivery, _truth = _delivery(
        tmp_path,
        settings,
        shot="cover drive",
        include_audio=True,
        audio_offset_s=0.22,
        post_frames=12,
    )
    assert delivery["contact"]["video_detected"] is True
    assert delivery["contact"]["audio_confirmation"] == "not confirmed"


def test_missing_audio_is_flagged_exactly(settings, tmp_path):
    delivery, truth = _delivery(tmp_path, settings, shot="straight drive", include_audio=False)
    assert delivery["contact"]["video_detected"] is True
    assert delivery["contact"]["frame"] == truth.deliveries[0].contact_frame
    assert delivery["contact"]["audio_confirmation"] == NO_AUDIO
    assert NO_AUDIO == "no audio second confirmation"


def test_a_miss_has_no_video_contact(settings, tmp_path):
    delivery, _truth = _delivery(tmp_path, settings, shot="no shot", include_audio=False)
    assert delivery["contact"]["video_detected"] is False
    assert delivery["contact"]["audio_confirmation"] == NO_AUDIO
    assert delivery["shot"] == "no shot"
