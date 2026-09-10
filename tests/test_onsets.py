"""Offline tests for onset detection: no network, no audio fixtures."""

from __future__ import annotations

import numpy as np
import pytest

from iskumetri.onsets import BLOCK, HOP, N_FFT, SR, onset_strength, pick_peaks

CLICKS = [0.5, 1.0, 1.75, 2.0, 2.5, 3.6, 4.4, 5.0]
DURATION = 6.0


def click_track(times: list[float], duration: float = DURATION) -> np.ndarray:
    """A quiet noise floor with a sharp decaying click at each given time."""
    rng = np.random.default_rng(0)
    y = rng.standard_normal(int(duration * SR)).astype(np.float32) * 0.001
    click = (np.exp(-np.arange(400) / 40.0) * rng.standard_normal(400)).astype(np.float32)
    for t in times:
        i = int(t * SR)
        y[i : i + len(click)] += click
    return y


def reference_flux(y: np.ndarray, n_fft: int = N_FFT, hop: int = HOP) -> np.ndarray:
    """The unchunked float64 spectral flux, kept as the correctness oracle."""
    y = np.pad(y, (n_fft // 2, n_fft // 2))
    n = 1 + (len(y) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    log_mag = np.log1p(1000.0 * np.abs(np.fft.rfft(y[idx] * np.hanning(n_fft), axis=1)))
    return np.maximum(np.diff(log_mag, axis=0, prepend=log_mag[:1]), 0).mean(axis=1)


def interior_onsets(y: np.ndarray, **kwargs) -> np.ndarray:
    """Onsets away from the edges, where zero-padding makes silence look like an attack."""
    found = pick_peaks(onset_strength(y), **kwargs)
    return found[(found > 0.2) & (found < len(y) / SR - 0.2)]


def test_pick_peaks_recovers_every_click() -> None:
    found = interior_onsets(click_track(CLICKS), sensitivity=1.0, min_interval=0.05)

    assert len(found) == len(CLICKS)
    # Absolute timing is bounded by the 46 ms analysis window, not the 5.8 ms hop:
    # a window overlapping the attack raises the flux slightly before the attack itself.
    assert np.allclose(found, CLICKS, atol=0.025)


def test_stroke_durations_are_accurate_to_within_a_hop() -> None:
    """The app plots gaps between strokes, so this is the precision that matters.

    The window-induced lead is the same for every stroke, so it cancels in the
    difference and durations land far tighter than the absolute times do.
    """
    found = interior_onsets(click_track(CLICKS), sensitivity=1.0, min_interval=0.05)

    assert np.allclose(np.diff(found), np.diff(CLICKS), atol=HOP / SR)


def test_chunking_matches_unchunked_reference() -> None:
    """A signal spanning more than one block must match the oracle."""
    y = np.random.default_rng(0).standard_normal(SR * 30).astype(np.float32)
    got = onset_strength(y)

    assert len(got) > BLOCK, "signal too short to exercise chunking"
    assert np.max(np.abs(reference_flux(y) - got)) < 1e-5


def test_block_boundary_adds_no_spurious_onset() -> None:
    """Steady input: the boundary frame must not stand out as an onset."""
    y = np.random.default_rng(1).standard_normal(SR * 30).astype(np.float32)
    env = onset_strength(y)

    assert len(env) > BLOCK
    assert env[BLOCK] == pytest.approx(env.mean(), rel=0.5)
    assert BLOCK not in (pick_peaks(env) * SR / HOP).round().astype(int)
