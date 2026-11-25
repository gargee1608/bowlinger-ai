"""Audio presence and onset times. A silent stream counts as no audio."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from bowlinger.media import load_audio

RMS_PRESENT = 0.005


def inspect_audio(path: Path) -> dict:
    loaded = load_audio(path)
    if loaded is None:
        return {"present": False, "rms": 0.0, "onsets_s": []}
    samples, sample_rate = loaded
    if samples.size == 0:
        return {"present": False, "rms": 0.0, "onsets_s": []}
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= RMS_PRESENT:
        return {"present": False, "rms": rms, "onsets_s": []}
    onsets = librosa.onset.onset_detect(y=samples, sr=sample_rate, units="time")
    return {"present": True, "rms": rms, "onsets_s": [float(value) for value in onsets]}
