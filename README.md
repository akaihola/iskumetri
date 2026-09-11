# Iskumetri

A web app that listens to a drummer's open–close–open roll on YouTube and draws
the duration of every stroke as a zoomable bar graph.

Paste a YouTube URL and the server pulls the audio, finds the exercise, finds
each stroke in it, and plots one bar per stroke: the bar spans until the next
stroke and its height is that gap in milliseconds. A roll that speeds up then
reads as a falling ramp.

## The exercise

The [Percussive Arts Society rudiment sheet][pas] says every rudiment is to be
practiced "open (slow) to close (fast) to open (slow)", and drummers call the
exercise **open–close–open** (also written "open, closed, open" or
"slow–fast–slow"; see [Wikipedia][ocō]). Videos that only go one way tend to be
titled "slow to fast", "fast to slow" or, in classical terms, accelerando and
ritardando; "tempo ramp" and "speed ramp" are informal. The subdivision
staircase called a "pyramid" is a different exercise, although the app handles
it as well, since a staircase is also a monotone ramp.

[pas]: https://pas.org/rudiments/
[ocō]: https://en.wikipedia.org/wiki/Open,_closed,_open

## Running it

Requires [uv](https://docs.astral.sh/uv/) and `ffmpeg` on the path.

```bash
uv sync
uv run uvicorn iskumetri.server:app --port 8000
```

Open <http://127.0.0.1:8000/>. A slow-to-fast double stroke roll is pre-filled,
so pressing Analyze is enough to see it work. The first run on a video downloads
and analyses it, which takes about 15 seconds for 10 minutes of audio; repeat
runs are served from `cache/` without touching the network.

## Reading the graph

- **Scroll** to zoom about the cursor, **drag** to pan, **double-click** to reset.
- **Hover** a bar for its stroke number, timestamp, duration and strokes per minute.
- **Click** a bar to seek the embedded YouTube video there. Its playback clock drives the chart
  playhead, including seeks while paused. Reanalyzing the same video preserves
  playback. YouTube embedding requires network access and may be disabled by
  the uploader; the chart remains usable if playback fails.
- **Duration / Tempo** switches the bar height between the gap in milliseconds and
  its reciprocal in strokes per minute. Both come from the time since the previous
  stroke, so either view shows the jitter of every single stroke. The tempo view
  magnifies jitter on fast strokes and flattens it on slow ones, because a fixed
  error in milliseconds is a larger share of a short gap.
- **Average around each stroke** uses N intervals around that stroke, requiring
  N+1 timestamps for a full window. Even N splits equally before and after;
  odd N has one extra following interval. Edges use only available intervals.
  Mean duration is elapsed time divided by interval count; tempo is 60 times
  interval count divided by elapsed seconds, not the average of reciprocals.
  N=1 hides the overlay. Keep N below a subdivision step to avoid blurring it.
- **Auto-tune** (default) tries ten sensitivity and min gap combinations and keeps
  the one that reads most like a steady ramp; the chosen values are shown under the
  graph. Editing **sensitivity** turns Auto-tune off automatically. Untick it to set **sensitivity** (the detection threshold) and **min gap**
  (how close two strokes may be before they are treated as one) by hand. Recordings
  with backing music or talking usually need a lower sensitivity.
- **Color shade** shows relative recorded volume, from quiet/faint to loud/solid.
  A 40 ms attack RMS window is normalized to the recording’s maximum 40 ms RMS,
  with -40 dB mapped to 0% and 0 dB to 100%. This measures recorded sound, not
  physical stick velocity. Hover or open the table for the numeric value.
- **Green outlines** mark strokes the analyzer inferred inside a gap that was too long
  for its neighbours, and the table marks them with `?`.

## How detection works

`iskumetri/onsets.py` decodes the audio to mono at 22.05 kHz and computes
half-wave rectified log spectral flux, which spikes when broadband energy
appears, as it does on a drum attack. Peaks above an adaptive local threshold
become strokes, and the graph plots the gaps between them.

The transform runs in float32 blocks rather than one whole-signal allocation, so
peak memory stays near 0.3 GB for a 10-minute clip instead of scaling with
length.

Absolute stroke times run 14 to 19 ms early, because a 46 ms analysis window
overlapping an attack lifts the flux slightly before the attack itself. That lead
is near enough constant that it cancels when consecutive strokes are subtracted,
so the durations the graph actually plots are accurate to within about 5 ms.

### Cleaning up

Raw peaks contain two kinds of errors: a second, weaker peak 30–50 ms after a
stroke where the flux rings after the attack, and a stroke missed because it was
softer than its neighbours. Both stand out against the surrounding gaps, because
the exercise is by definition a smooth ramp.

1. Any gap shorter than half the median of its twelve neighbours loses the weaker
   of its two strokes, repeatedly.
2. Any gap longer than 1.7 times that median is searched again at a third of the
   threshold; a peak is accepted only if it splits the gap into two regular gaps.
   These strokes are reported as *inferred*.
3. Strokes are split at pauses, the smoothed gap series is cut into rising and
   falling runs, and the longest run (or pair of opposite runs) with at least 16
   strokes and a two-fold tempo change is the exercise. It is extended over
   neighbouring runs that stay within its tempo range, so a held top speed is
   kept. Only that part is plotted; intros, wrap-ups and other playing separated
   from the roll by a pause are dropped. Without a ramp, the whole recording is
   shown and the summary says so.
4. Auto-tune runs the sensitivity/min-gap grid with an additional local prominence
   floor: a candidate must clear 5% of the strongest prominence within one second
   either side. The floor follows the quieter attacks in fast passages, and also
   applies to gap recovery. Among near-equal regularity scores, summed attack
   evidence breaks ties. Empty detections cannot beat supported results.

On the cached AAC version of the pre-filled video, this removes 14 weak early
peaks from the old 257-stroke result. The 14 retained strokes before 0:09 exactly
match manual sensitivity 1 / 30 ms, and all 131 old Auto-tune detections from
0:25 remain unchanged. The result has 243 strokes over 1.701–35.213 s using
sensitivity 2 / 50 ms. This comparison demonstrates the reported slow/fast
tradeoff is addressed; it is not a hand-labelled ground truth for every stroke.
Very quiet intentional strokes can still resemble ringing, and recordings with
abrupt changes in volume need particular care.

Detection quality depends on the recording. A clean drum or pad track resolves
down to 32nd notes; a track with backing music, talking or a metronome will pick
up strokes that are not there, which is what the manual controls are for.

## Cache

Everything lives in `cache/` (or `$ISKUMETRI_CACHE`), keyed by the 11-character
video id, so every URL form for the same video (`youtube.com/watch`, `youtu.be`,
`m.`, `music.`, `shorts/`, `embed/`, `live/`, with or without playlist or
timestamp parameters) hits the same files and needs no network:

- `<id>.webm` or `<id>.m4a` — the audio stream.
- `<id>.info.json` — title, duration and description. Legacy entries refresh metadata
  once when online; a failed refresh keeps cached audio usable.
- `<id>.v3.auto.json` or `<id>.v3.s<sensitivity>.w<min gap>.json` — one analysis
  per parameter choice. The version tag changes when the output shape does.

### Reusable stages

`iskumetri.pipeline.fetch(video_id, cache)` downloads audio and caches metadata.
`iskumetri.onsets.analyze(audio_path, sensitivity, min_interval)` analyzes local
media without HTTP or storage. `pipeline.load_analysis(path)` and
`pipeline.save_analysis(path, result)` read and atomically store results.
`pipeline.analyze_video(url, sensitivity, min_interval, cache)` composes them.
Either parameter being None selects Auto-tune. Importing the pipeline creates
no directories; a future CLI can call these functions directly.

### Audio format

The smallest stream that still gives a reliable analysis is fetched:
`bestaudio[abr<=100][asr>=44000]/worstaudio[asr>=44000]/bestaudio`. Measured on
the pre-filled video, with the same detector on every stream:

| yt-dlp format | codec | kbps | size | strokes after cleaning |
|---|---|---|---|---|
| 140 | AAC-LC 44.1 kHz | 130 | 581 KB | 210 (reference) |
| 251 | Opus 48 kHz | 89 | 401 KB | 216, 207 of them within 12 ms of the reference |
| 139 | HE-AAC, 22 kHz core | 49 | 225 KB | 191, loses about one stroke in ten |

Opus at 89 kbps reproduces the reference; the 22 kHz-core HE-AAC stream smears
attacks and is excluded by the sample-rate filter. Codecs decode with different
fixed offsets (tens of milliseconds), which cancel in the gaps the graph plots.

## Limits

Videos are capped at 20 minutes, and only YouTube URLs are accepted.

## Tests

```bash
uv run pytest
node --test tests/test_app.cjs
```

The tests are offline and need no audio fixtures. To re-check accuracy against a
real recording:

```bash
uv run yt-dlp -f "bestaudio[abr<=100][asr>=44000]/worstaudio[asr>=44000]/bestaudio" \
  -o "cache/%(id)s.%(ext)s" "https://www.youtube.com/watch?v=NvIDlwzHRGQ"
uv run python -c "from pathlib import Path; from iskumetri.onsets import analyze; \
  r = analyze(Path('cache/NvIDlwzHRGQ.webm')); \
  print(r['params'], r['segment'], len(r['onsets']), min(r['intervals']))"
```

Compare individual onset times in both the slow and fast portions rather than
asserting one stroke count across audio formats. See docs/validation.md for the
cached recording comparison and remaining validation limits.

## Issues

- Issues: `TASKS.md`
