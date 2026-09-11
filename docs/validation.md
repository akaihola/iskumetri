# Reference recording validation

Compared cached `NvIDlwzHRGQ.m4a` with the original detector and the new local
prominence floor. No timestamps or video IDs enter the detector.

| Portion | Manual 1 / 30 ms | Old auto 2 / 50 ms | New auto 2 / 50 ms |
| --- | ---: | ---: | ---: |
| Before 0:09 | 14 | 28 | 14 |
| From 0:25 | 93 | 131 | 131 |
| Whole detected exercise | 205 | 257 | 243 |

New early onsets exactly match manual, and all later onsets exactly match old
auto. No new onset was added. Comparisons used a 25 ms matching tolerance;
retained timestamps were in fact identical before rounding.

Removed timestamps in seconds:
1.4745, 1.9621, 2.5832, 3.3030, 3.9358, 4.6266, 5.2593,
5.8340, 6.4145, 6.8789, 7.3956, 7.8077, 8.2373, 8.6610.

Retained early reference timestamps in seconds:
1.7009, 2.3626, 3.0418, 3.7094, 4.3595, 5.0039, 5.6076,
6.1417, 6.6409, 7.1285, 7.5871, 8.0051, 8.4230, 8.8294.

Signal inspection found early secondary peaks with spectral prominence about
0.02–0.04 versus 1.35–2.33 for the retained attacks. Their 40 ms PCM RMS was
about 0.005–0.009 versus 0.14–0.21 for the attacks. Fast peaks have smaller flux
prominence but substantial PCM energy. A floor relative to nearby prominence
rejects the former without losing the latter.

These are signal-based reference observations, not independently annotated
physical strokes. A smoother chart alone does not prove stroke accuracy.
Synthetic regressions separately check weak echoes and quiet fast attacks.


## Completed checks

- `uv run pytest -q`: 50 passed, including real quiet strokes, slow shadows,
  fast transitions, short/silent envelopes, velocity alignment, cache keys,
  description backfill/fallback and HTTP error mapping.
- `node --test tests/test_app.cjs` passed. Direct execution with
  `node tests/test_app.cjs` reports all six tests individually.
- A temporary cache using the real AAC recording produced 243 aligned onsets
  and velocities; a repeat via another URL form returned the identical cache.
- Chromium browser checks passed for native spinner clicks, keyboard arrows,
  typing, re-enabling Auto-tune, light/dark rendering and a 390 px mobile layout.
  No page JavaScript errors or horizontal page overflow occurred.
- The real YouTube iframe loaded and played using its Play button. Paused
  seeking updated the playhead; clicking the chart sought to 14.259 s;
  reanalyzing the same video preserved exactly that playback position.
  Browser analysis responses used the precomputed real-audio result fixture.
- Unit tests cover delayed player readiness, changing the selected video,
  paused clock updates and API failure status. Embedding remains subject to
  YouTube availability and uploader permissions.
- `python3 tools/check_tasks_md.py TASKS.md` passed. The tracker contains no
  issue entries on this branch or main, so there was no existing issue to move;
  TASKS.md is unchanged.

Absolute audio/video timing retains the detector's documented roughly 20 ms
lead and codec-dependent offsets. The player clock is used directly, without
an arbitrary correction. Physical stroke accuracy beyond the signal comparison
above has not been independently annotated.


## AI review follow-up

Re-ran the detector against the implementation on main using the cached AAC
recording. Early detections still exactly match manual defaults, and every
onset at or after 0:09 remains identical to old Auto-tune.

Fixed and regression-tested two recovery defects: returning to Auto-tune with
an empty/invalid Sensitivity now restores the valid default, and an analysis
can retry a failed YouTube API script load. Chromium verified a deliberately
failed first API request followed by a successful second load.

The extended tooltip measured 576 px on a 390 px viewport. It now wraps within
the chart. The expanded table scrolls within its container. Chromium verified
both bounds in the dark mobile layout without JavaScript errors.

All 50 Python tests and six JavaScript tests pass. The TASKS.md diff against
main is empty; the tracker checker again confirms no issue appears under more
than one heading.
