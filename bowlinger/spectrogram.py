"""Waveform peaks and a spectrogram image for the audio training page."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from bowlinger.media import load_audio


def waveform_peaks(path: Path, buckets: int = 800) -> dict:
    loaded = load_audio(path)
    if not loaded:
        return {"duration_s": 0.0, "peaks": [], "sample_rate": 0}
    samples, sample_rate = loaded
    if samples.size == 0:
        return {"duration_s": 0.0, "peaks": [], "sample_rate": sample_rate}
    mono = samples if samples.ndim == 1 else samples.mean(axis=1)
    duration = float(mono.size) / float(sample_rate)
    width = min(buckets, int(mono.size))
    if width < 1:
        return {"duration_s": round(duration, 3), "peaks": [], "sample_rate": sample_rate}
    chunks = np.array_split(np.abs(mono), width)
    peaks = [round(float(chunk.max()) if chunk.size else 0.0, 5) for chunk in chunks]
    return {"duration_s": round(duration, 3), "peaks": peaks, "sample_rate": int(sample_rate)}


def spectrogram_png(path: Path) -> bytes:
    import librosa

    loaded = load_audio(path)
    if not loaded:
        image = np.zeros((80, 320, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("Could not encode an empty spectrogram")
        return encoded.tobytes()
    samples, sample_rate = loaded
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim > 1:
        mono = mono.mean(axis=1)
    if mono.size > sample_rate * 90:
        mono = mono[: sample_rate * 90]
    spectrum = np.abs(librosa.stft(mono, n_fft=1024, hop_length=512))
    decibels = librosa.amplitude_to_db(spectrum, ref=np.max)
    decibels = np.flipud(decibels)
    low = float(np.percentile(decibels, 5))
    high = float(np.percentile(decibels, 99))
    if high <= low:
        high = low + 1.0
    scaled = np.clip((decibels - low) / (high - low), 0, 1)
    gray = (scaled * 255).astype(np.uint8)
    colored = cv2.applyColorMap(gray, cv2.COLORMAP_MAGMA)
    colored = cv2.resize(colored, (960, 280), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".png", colored)
    if not ok:
        raise RuntimeError("Could not encode the spectrogram")
    return encoded.tobytes()
