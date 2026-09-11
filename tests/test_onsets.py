"""Offline tests for onset detection: no network, no audio fixtures."""

from __future__ import annotations

import numpy as np
import pytest

from iskumetri.onsets import (
    BLOCK, HOP, N_FFT, SR, auto_tune, clean_outliers, detect, fill_gaps, find_exercise,
    onset_strength, outlier_fraction, pick_peaks,
)

CLICKS = [0.5, 1.0, 1.75, 2.0, 2.5, 3.6, 4.4, 5.0]
DURATION = 6.0


def click_track(times: list[float], duration: float = DURATION, gains: dict[float, float] | None = None) -> np.ndarray:
    """A quiet noise floor with a sharp decaying click at each given time."""
    rng = np.random.default_rng(0)
    y = rng.standard_normal(int(duration * SR)).astype(np.float32) * 0.001
    click = (np.exp(-np.arange(400) / 40.0) * rng.standard_normal(400)).astype(np.float32)
    for t in times:
        i = int(t * SR)
        y[i : i + len(click)] += click * (gains or {}).get(t, 1.0)
    return y


def ramp(start: float, stop: float, n: int, t0: float = 0.5) -> list[float]:
    """n strokes whose gaps shrink geometrically from start to stop seconds."""
    gaps = np.geomspace(start, stop, n - 1)
    return [t0, *(t0 + np.cumsum(gaps))]


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


def test_min_interval_rejects_a_peak_exactly_that_far_away() -> None:
    """30 ms is 5.2 hops; truncating it to 5 let peaks 5 hops apart both through."""
    env = np.full(300, 0.01)
    env[100] = env[105] = 1.0
    assert len(pick_peaks(env, min_interval=0.03)) == 1
    env[105], env[106] = 0.01, 1.0
    assert len(pick_peaks(env, min_interval=0.03)) == 2


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


def interior(times: np.ndarray, duration: float) -> np.ndarray:
    return times[(times > 0.2) & (times < duration - 0.2)]


def test_clean_outliers_drops_the_weaker_half_of_a_doublet() -> None:
    strokes = ramp(0.4, 0.2, 20)
    doublet = strokes[8] + 0.04  # a quiet echo 40 ms after a real stroke
    y = click_track([*strokes, doublet], duration=8.0, gains={doublet: 0.3})
    env = onset_strength(y)
    raw = interior(pick_peaks(env, min_interval=0.03), 8.0)
    assert len(raw) == len(strokes) + 1, "the doublet should be detected before cleaning"

    cleaned = clean_outliers(raw, env)

    assert len(cleaned) == len(strokes)
    assert np.allclose(cleaned, strokes, atol=0.025)


def test_fill_gaps_recovers_a_stroke_below_threshold() -> None:
    strokes = ramp(0.4, 0.2, 20)
    soft = strokes[10]
    y = click_track(strokes, duration=8.0, gains={soft: 0.003})
    env = onset_strength(y)
    raw = interior(pick_peaks(env), 8.0)
    assert len(raw) == len(strokes) - 1, "the soft stroke should be missed at first"

    filled, inferred = fill_gaps(raw, env)

    assert len(filled) == len(strokes)
    assert inferred == [10]
    assert abs(filled[10] - soft) < 0.03


def licks_ramp_licks() -> tuple[list[float], list[float], list[float]]:
    """Unrelated playing, a pause, a 60 to 240 bpm ramp, a pause, more playing."""
    rng = np.random.default_rng(3)
    intro = list(np.cumsum(rng.uniform(0.1, 0.5, 12)) + 0.3)
    exercise = ramp(1.0, 0.25, 40, t0=intro[-1] + 3.0)
    outro = list(exercise[-1] + 2.5 + np.cumsum(rng.uniform(0.1, 0.5, 12)))
    return intro, exercise, outro


def test_find_exercise_returns_the_ramp_between_unrelated_playing() -> None:
    intro, exercise, outro = licks_ramp_licks()

    i0, i1, detected = find_exercise(np.array([*intro, *exercise, *outro]))

    assert detected
    assert (i0, i1) == (len(intro), len(intro) + len(exercise))


def test_find_exercise_keeps_a_jittery_held_tempo_on_both_sides_of_the_ramp() -> None:
    """Runs that wobble inside the ramp's tempo range are the exercise too, however many."""
    wobble = [0.3] * 5 + [0.45] * 5 + [0.3] * 5 + [0.45] * 5  # four reversals, all in range
    gaps = [*wobble, *np.geomspace(0.5, 0.15, 30), *wobble]
    times = np.concatenate([[0.5], 0.5 + np.cumsum(gaps)])

    i0, i1, detected = find_exercise(times)

    assert detected
    assert (i0, i1) == (0, len(times))


def test_find_exercise_falls_back_to_everything_without_a_ramp() -> None:
    steady = np.arange(0.5, 10.0, 0.25)

    i0, i1, detected = find_exercise(steady)

    assert not detected
    assert (i0, i1) == (0, len(steady))


def test_auto_tune_leaves_a_ramp_with_doublets_regular() -> None:
    strokes = ramp(0.5, 0.15, 40)
    doublets = [strokes[i] + 0.035 for i in (5, 14, 23)]
    y = click_track([*strokes, *doublets], duration=14.0, gains={d: 0.35 for d in doublets})
    env = onset_strength(y)
    assert len(pick_peaks(env, min_interval=0.03)) > len(strokes), "doublets should trip the raw detector"

    best = auto_tune(env)
    found = interior(best["times"], 14.0)

    assert len(found) == len(strokes)
    assert np.allclose(found, strokes, atol=0.025)
    assert set(best["params"]) == {"sensitivity", "min_interval"}


def test_detect_trims_to_the_exercise_and_reindexes_inferred_strokes() -> None:
    intro, exercise, outro = licks_ramp_licks()
    soft = exercise[20]
    duration = outro[-1] + 1.0
    y = click_track([*intro, *exercise, *outro], duration=duration, gains={soft: 0.003})

    r = detect(onset_strength(y), 1.0, 0.03)

    assert r["segment"]["detected"]
    assert len(r["times"]) == len(exercise)
    assert np.allclose(r["times"], exercise, atol=0.03)
    assert r["inferred"] == [20]


def test_auto_tune_rejects_slow_shadows_but_keeps_quiet_fast_attacks():
    # Sharp peaks on a steady flux floor: slow shadows have little prominence,
    # while the fast attacks soften together rather than alternating with noise.
    slow = np.arange(1, 8, .6)
    fast = np.arange(10, 14, .08)
    times = np.concatenate([slow, np.arange(8, 10, .2), fast])
    env = np.full(int(15 * SR / HOP), .1)
    for t in times:
        env[round(t * SR / HOP)] = 2 if t < 8 else .3
    shadows = slow + .25
    for t in shadows:
        env[round(t * SR / HOP)] = .14
    result = auto_tune(env)
    found = result['times']
    assert all(np.min(abs(found - t)) < HOP / SR for t in times)
    assert all(np.min(abs(found - t)) > .025 for t in shadows)


@pytest.mark.parametrize('length', [0, 1, 2, 10, 40])
def test_short_silent_envelopes(length):
    env = np.zeros(length)
    assert len(auto_tune(env)['times']) == 0
    assert len(pick_peaks(env)) == 0


def test_velocity_tracks_volume_and_is_independent_of_detection():
    from iskumetri.onsets import stroke_velocities
    times = np.array([.5, 1, 1.5])
    y = click_track(times.tolist(), duration=2, gains={.5: .1, 1: .4, 1.5: 1})
    levels = stroke_velocities(y, times)
    assert 0 <= levels[0] < levels[1] < levels[2] <= 1
    assert stroke_velocities(y, times[1:]) == levels[1:]
    assert stroke_velocities(np.zeros(20), np.array([0])) == [0]
    assert stroke_velocities(np.array([]), np.array([])) == []


def test_analyze_velocity_alignment(monkeypatch):
    from iskumetri import onsets
    monkeypatch.setattr(onsets, 'decode', lambda _: click_track(CLICKS))
    result = onsets.analyze(None)
    assert len(result['onsets']) == len(result['velocities'])
    assert len(result['intervals']) == len(result['onsets']) - 1
    assert all(0 <= v <= 1 for v in result['velocities'])


def test_auto_tune_keeps_a_quiet_real_stroke_in_a_ramp():
    strokes = ramp(.4, .12, 40)
    soft = strokes[20]
    env = onset_strength(click_track(strokes, duration=12, gains={soft: .05}))
    found = auto_tune(env)['times']
    assert all(np.min(abs(found - t)) < .025 for t in strokes)


@pytest.mark.parametrize('params', [(None, None), (1.0, 0.03)])
def test_pcm_matches_native_wrapper(monkeypatch, params):
    from iskumetri import onsets
    y = click_track(CLICKS)
    monkeypatch.setattr(onsets, 'decode', lambda _: y)
    assert onsets.analyze(None, *params) == onsets.analyze_pcm(y, *params)


@pytest.mark.parametrize('y', [np.zeros((2, 2), dtype=np.float32), np.array([np.nan], dtype=np.float32),
                             np.array([np.inf], dtype=np.float32), np.zeros(2), [0.0]])
def test_pcm_rejects_invalid_samples(y):
    from iskumetri.onsets import analyze_pcm
    with pytest.raises(ValueError, match='PCM'):
        analyze_pcm(y)


def test_empty_pcm_is_finite():
    import json
    from iskumetri.onsets import analyze_pcm
    result = analyze_pcm(np.array([], dtype=np.float32))
    assert result['duration'] == 0
    assert result['onsets'] == result['intervals'] == result['velocities'] == []
    json.dumps(result, allow_nan=False)


def test_native_params_are_validated_before_decoding(monkeypatch):
    from iskumetri import onsets
    monkeypatch.setattr(onsets, 'decode', lambda _: pytest.fail('decode called'))
    with pytest.raises(ValueError, match='sensitivity'):
        onsets.analyze(None, 0, 0.03)


def test_velocity_chunking_preserves_the_reference(monkeypatch):
    from iskumetri import onsets
    y = click_track(CLICKS)
    times = np.array(CLICKS)
    expected = onsets.stroke_velocities(y, times)
    monkeypatch.setattr(onsets, 'BLOCK', 7)
    assert onsets.stroke_velocities(y, times) == expected
