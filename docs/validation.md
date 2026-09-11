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
