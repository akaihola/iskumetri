# Iskumetri

A web app that listens to a drummers' pyramid exercise on YouTube and draws the
duration of every stroke as a zoomable bar graph.

Paste a YouTube URL and the server pulls the audio, finds each stroke, and plots
one bar per stroke: the bar spans until the next stroke and its height is that
gap in milliseconds. A pyramid exercise then reads as a staircase, one step per
subdivision.

## Running it

Requires [uv](https://docs.astral.sh/uv/) and `ffmpeg` on the path.

```bash
uv sync
uv run uvicorn iskumetri.server:app --port 8000
```

Open <http://127.0.0.1:8000/>. A 60 bpm pyramid exercise is pre-filled, so
pressing Analyze is enough to see it work. The first run on a video downloads and
analyses it, which takes about 15 seconds for 10 minutes of audio; repeat runs
are served from `cache/`.

## Reading the graph

- **Scroll** to zoom about the cursor, **drag** to pan, **double-click** to reset.
- **Hover** a bar for its stroke number, timestamp, duration and strokes per minute.
- **Click** a bar to seek the audio there, and play along under a moving playhead.
- **Sensitivity** raises or lowers the detection threshold, and **min gap** sets how
  close two strokes may be before they are treated as one. Recordings with backing
  music or talking usually need a lower sensitivity.

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

Detection quality depends on the recording. A clean drum or pad track resolves
down to 32nd notes; a track with backing music, talking or a metronome will pick
up strokes that are not there, which is what the two controls are for.

## Limits

Videos are capped at 20 minutes, and only YouTube URLs are accepted.

## Tests

```bash
uv run pytest
```

The tests are offline and need no audio fixtures. To re-check accuracy against a
real recording:

```bash
uv run yt-dlp -f "bestaudio[ext=m4a]/bestaudio" -o "cache/%(id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=VojYvzrYsjY"
```

Analysing that clip should show interval modes near 127, 163, 247, 345 and
481 ms, being 32nd, 16th-triplet, 16th, 8th-triplet and 8th notes at 60 bpm,
with a median of 250 ms.
