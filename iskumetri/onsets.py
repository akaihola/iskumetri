"""Spectral-flux onset detection on a mono PCM signal (numpy only)."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

SR = 22050
N_FFT = 1024
HOP = 128  # 5.8 ms at 22.05 kHz
BLOCK = 4096  # frames per STFT chunk; caps peak memory regardless of clip length
FRAMES_PER_S = SR / HOP
# Auto-tune grid. The flux envelope is computed once, so each run costs ~0.2 s.
GRID = [(s, w) for s in (0.5, 0.7, 1.0, 1.4, 2.0) for w in (0.03, 0.05)]
# A gap this far from its neighbours' median is an outlier, not a stroke.
REGULAR = (0.6, 1.6)


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


def adaptive_threshold(env: np.ndarray, sensitivity: float) -> tuple[np.ndarray, float]:
    """Local mean of the envelope over 150 ms, and the margin a peak must clear."""
    win = int(0.15 * FRAMES_PER_S)
    kernel = np.ones(2 * win + 1) / (2 * win + 1)
    return np.convolve(env, kernel, mode="same"), 0.25 * float(np.std(env)) / sensitivity


def pick_peaks(
    env: np.ndarray, hop: int = HOP, sr: int = SR,
    sensitivity: float = 1.0, min_interval: float = 0.03,
) -> np.ndarray:
    """Return onset times (s). Peaks must exceed a local adaptive threshold."""
    frames_per_s = sr / hop
    local_mean, delta = adaptive_threshold(env, sensitivity)
    thresh = local_mean + delta
    # Round up: truncating let peaks exactly min_interval apart through.
    wait = max(1, math.ceil(min_interval * frames_per_s))
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


def local_median(values: np.ndarray, k: int = 6) -> np.ndarray:
    """Median of each value's 2k+1 neighbours, edges padded with their end value."""
    if len(values) == 0:
        return np.asarray(values, dtype=float)
    padded = np.pad(np.asarray(values, dtype=float), k, mode="edge")
    return np.median(sliding_window_view(padded, 2 * k + 1), axis=1)


def _frame(t: float) -> int:
    return int(round(t * FRAMES_PER_S))


def clean_outliers(times: np.ndarray, env: np.ndarray, ratio: float = 0.5) -> np.ndarray:
    """Drop the weaker of two strokes closer than ratio × the surrounding median gap.

    Such pairs are the flux ringing right after an attack, not a second stroke.
    """
    t = list(times)
    while len(t) > 2:
        gaps = np.diff(t)
        bad = np.flatnonzero(gaps < ratio * local_median(gaps))
        if not len(bad):
            break
        drop: list[int] = []
        for i in bad:
            if drop and i - drop[-1] <= 1:  # neighbour already handled this pass
                continue
            drop.append(int(i) if env[_frame(t[i])] < env[_frame(t[i + 1])] else int(i) + 1)
        for j in sorted(set(drop), reverse=True):
            del t[j]
    return np.asarray(t)


def fill_gaps(
    times: np.ndarray, env: np.ndarray, sensitivity: float = 1.0, ratio: float = 1.7,
) -> tuple[np.ndarray, list[int]]:
    """Recover one missed stroke inside any gap longer than ratio × the local median.

    The gap is re-searched at a third of the detection threshold; the candidate is
    accepted only if it splits the gap into two regular gaps. Returns the times and
    the indices of the inserted strokes.
    """
    if len(times) < 3:
        return np.asarray(times), []
    local_mean, delta = adaptive_threshold(env, sensitivity)
    gaps = np.diff(times)
    lm = local_median(gaps)
    out = [float(times[0])]
    inferred: list[int] = []
    for i, gap in enumerate(gaps):
        if gap > ratio * lm[i]:
            a, b = _frame(times[i]) + 4, _frame(times[i + 1]) - 4  # skip the attacks
            if b > a:
                k = a + int(np.argmax(env[a:b]))
                tt = k / FRAMES_PER_S
                lo, hi = REGULAR[0] * lm[i], REGULAR[1] * lm[i]
                if env[k] > local_mean[k] + delta / 3 and lo < tt - times[i] < hi and lo < times[i + 1] - tt < hi:
                    out.append(tt)
                    inferred.append(len(out) - 1)
        out.append(float(times[i + 1]))
    return np.asarray(out), inferred


def _monotone_runs(s: np.ndarray, tol: float) -> list[tuple[int, int]]:
    """Split a series into runs that rise or fall, ignoring wiggles below tol."""
    runs: list[tuple[int, int]] = []
    start = ext = 0
    direction = 0
    for i in range(1, len(s)):
        if direction == 0:
            if abs(s[i] - s[start]) > tol:
                direction = 1 if s[i] > s[start] else -1
                ext = i
        elif (s[i] - s[ext]) * direction >= 0:
            ext = i
        elif (s[ext] - s[i]) * direction > tol:
            runs.append((start, ext))
            start, ext, direction = ext, i, -direction
    runs.append((start, len(s) - 1))
    return runs


def find_exercise(
    times: np.ndarray, min_strokes: int = 16, min_ratio: float = 2.0, hysteresis: float = 0.15,
) -> tuple[int, int, bool]:
    """Locate the tempo ramp: onset slice [i0, i1) and whether one was found.

    Strokes are split into pieces at pauses. Inside a piece the smoothed log gap is cut
    into rising and falling runs; a ramp is one run or two adjacent runs of opposite
    direction (slow-fast, fast-slow or slow-fast-slow) with at least min_strokes
    strokes and a tempo change of at least min_ratio. The longest ramp wins and is
    then extended over neighbouring runs that stay inside its tempo range, so a held
    top speed with jittery detection is not cut off. Without a ramp, the whole
    recording is returned so the app stays usable.
    """
    n = len(times)
    if n < min_strokes:
        return 0, n, False
    gaps = np.diff(times)
    pause = np.flatnonzero(gaps > np.maximum(2.0, 2 * local_median(gaps)))
    best: tuple[int, int] | None = None
    # Gap slice [a, b) of each piece between pauses, the pause gaps themselves excluded.
    for a, b in zip([0, *(pause + 1)], [*pause, len(gaps)]):
        if b - a < min_strokes - 1:
            continue
        s = local_median(np.log(gaps[a:b]), k=4)
        runs = _monotone_runs(s, hysteresis)
        # A wiggle smaller than the required change is a plateau, not a reversal.
        merged = [runs[0]]
        for r in runs[1:]:
            if np.ptp(s[r[0] : r[1] + 1]) < math.log(1.3):
                merged[-1] = (merged[-1][0], r[1])
            else:
                merged.append(r)
        candidates = merged + [(x[0], y[1]) for x, y in zip(merged[:-1], merged[1:])]
        ramp = None
        for r0, r1 in candidates:
            strokes = r1 - r0 + 2
            if strokes >= min_strokes and np.ptp(s[r0 : r1 + 1]) >= math.log(min_ratio):
                if ramp is None or strokes > ramp[1] - ramp[0]:
                    ramp = (r0, r1)
        if ramp is None:
            continue
        r0, r1 = ramp
        lo, hi = s[r0 : r1 + 1].min() - 0.25, s[r0 : r1 + 1].max() + 0.25

        def inside(run: tuple[int, int]) -> bool:
            part = s[run[0] : run[1] + 1]
            return bool(np.all((part >= lo) & (part <= hi)))

        # Adjacent runs share their boundary index, so walk outwards from the ramp:
        # leftwards through the runs in reverse order, rightwards in order.
        for run in reversed(merged):
            if run[1] == r0 and inside(run):
                r0 = run[0]
        for run in merged:
            if run[0] == r1 and inside(run):
                r1 = run[1]
        if best is None or r1 - r0 + 2 > best[1] - best[0]:
            best = (a + r0, a + r1 + 2)
    if best is None:
        return 0, n, False
    return best[0], best[1], True


def outlier_fraction(times: np.ndarray) -> float:
    gaps = np.diff(times)
    if len(gaps) == 0:
        return 0.0
    ratio = gaps / local_median(gaps)
    return float(np.mean((ratio < REGULAR[0]) | (ratio > REGULAR[1])))


def detect(env: np.ndarray, sensitivity: float, min_interval: float) -> dict:
    """Pick, clean, fill and trim to the exercise for one parameter pair."""
    raw = pick_peaks(env, sensitivity=sensitivity, min_interval=min_interval)
    filled, inferred = fill_gaps(clean_outliers(raw, env), env, sensitivity)
    i0, i1, detected = find_exercise(filled)
    times = filled[i0:i1]
    return {
        "times": times,
        "inferred": [i - i0 for i in inferred if i0 <= i < i1],
        "segment": {
            "start": float(times[0]) if len(times) else 0.0,
            "end": float(times[-1]) if len(times) else 0.0,
            "detected": detected,
        },
        "params": {"sensitivity": sensitivity, "min_interval": min_interval},
        "raw_count": len(raw),
        # Irregular gaps plus the share of strokes the segment had to leave out: a
        # parameter set whose messy start gets trimmed away must not look clean.
        "score": outlier_fraction(filled) + (len(filled) - len(times)) / len(filled) if len(filled) else 0.0,
    }


def auto_tune(env: np.ndarray) -> dict:
    """Run the grid and keep the most strokes among the near-smoothest results.

    The exercise is by definition a smooth tempo ramp, so the fraction of gaps that
    disagree with their neighbours measures detection errors of either kind. Among
    results within 0.01 of the best score, more strokes wins: a low sensitivity
    that drops every soft stroke also reads as smooth, and this guards against it.
    """
    results = [detect(env, s, w) for s, w in GRID]
    floor = min(r["score"] for r in results) + 0.01
    return max((r for r in results if r["score"] <= floor), key=lambda r: len(r["times"]))


def analyze(path: Path, sensitivity: float | None = None, min_interval: float | None = None) -> dict:
    y = decode(path)
    env = onset_strength(y)
    if sensitivity is None or min_interval is None:
        r = auto_tune(env)
    else:
        r = detect(env, sensitivity, min_interval)
    times = r["times"]
    return {
        "duration": len(y) / SR,
        "onsets": [round(float(t), 4) for t in times],
        "intervals": [round(float(d), 4) for d in np.diff(times)],
        "inferred": r["inferred"],
        "segment": r["segment"],
        "params": r["params"],
        "raw_count": r["raw_count"],
    }
