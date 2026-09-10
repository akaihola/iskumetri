"""Spectral-flux onset detection on a mono PCM signal (numpy only)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

SR = 22050
N_FFT = 1024
HOP = 128  # 5.8 ms at 22.05 kHz
BLOCK = 4096  # frames per STFT chunk; caps peak memory regardless of clip length


def decode(path: Path, sr: int = SR) -> np.ndarray:
    """Decode any ffmpeg-readable file to mono float32 samples (read-only array)."""
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
    ]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def onset_strength(y: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    """Half-wave rectified log spectral flux, one value per hop.

    The STFT is computed in blocks and kept in float32, so peak memory stays flat
    instead of scaling with the length of the recording.
    """
    pad = n_fft // 2
    y = np.pad(y, (pad, pad))  # copies, so a read-only input from decode() is fine
    frames = sliding_window_view(y, n_fft)[::hop]
    window = np.hanning(n_fft).astype(np.float32)

    flux_blocks: list[np.ndarray] = []
    carried: np.ndarray | None = None  # last log-magnitude frame of the previous block
    for start in range(0, len(frames), BLOCK):
        block = frames[start : start + BLOCK] * window
        log_mag = np.log1p(1000.0 * np.abs(np.fft.rfft(block, axis=1)))
        # Carrying the previous block's final frame keeps the difference continuous;
        # without it every block boundary would register as a spurious onset.
        previous = log_mag[:1] if carried is None else carried
        flux = np.diff(log_mag, axis=0, prepend=previous)
        flux_blocks.append(np.maximum(flux, 0).mean(axis=1))
        carried = log_mag[-1:]
    return np.concatenate(flux_blocks)


def pick_peaks(
    env: np.ndarray, hop: int = HOP, sr: int = SR,
    sensitivity: float = 1.0, min_interval: float = 0.03,
) -> np.ndarray:
    """Return onset times (s). Peaks must exceed a local adaptive threshold."""
    frames_per_s = sr / hop
    win = int(0.15 * frames_per_s)  # 150 ms local context
    kernel = np.ones(2 * win + 1) / (2 * win + 1)
    local_mean = np.convolve(env, kernel, mode="same")
    delta = 0.25 * np.std(env) / sensitivity
    thresh = local_mean + delta
    wait = max(1, int(min_interval * frames_per_s))
    is_peak = (env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > thresh[1:-1])
    cand = np.flatnonzero(is_peak) + 1
    kept: list[int] = []
    for f in cand:
        if kept and f - kept[-1] < wait:
            if env[f] > env[kept[-1]]:
                kept[-1] = int(f)
            continue
        kept.append(int(f))
    return np.asarray(kept) * hop / sr


def analyze(path: Path, sensitivity: float = 1.0, min_interval: float = 0.03) -> dict:
    y = decode(path)
    env = onset_strength(y)
    times = pick_peaks(env, sensitivity=sensitivity, min_interval=min_interval)
    return {
        "duration": len(y) / SR,
        "onsets": [round(float(t), 4) for t in times],
        "intervals": [round(float(d), 4) for d in np.diff(times)],
    }
