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

## Browser support

The upload path now runs the canonical NumPy detector in a Pyodide 0.29.3
worker, after browser decoding to mono 22.05 kHz. Native `analyze()` delegates
to the same `analyze_pcm()` entry point. No detector was replaced and no
third-party detection or DLPro code was copied.

Real browser testing found two implementation requirements absent from the
initial plan:

- NumPy on wasm32 rejects a full-signal strided view whose logical size exceeds
  its index limit. A 30-second fixture failed before the FFT. Creating the view
  inside each existing block fixes this without changing the spectral flux.
  Volume-reference windows needed the same treatment.
- A failed dynamic import remains cached inside its worker. Retrying with a new
  worker fixes runtime-load recovery; resetting only the initialization promise
  does not.

### Checks and limits

Validation used Chromium 149.0.7827.55 and Firefox 151.0 on Linux x86_64, with
Playwright 1.56.1 and the managed browser executable overrides. Native oracle
results used CPython 3.14.6 and NumPy 2.5.3. Commands:

```bash
uv run pytest -q
node --test tests/test_app.cjs
npm run test:browser
ISKUMETRI_LONG_TEST=1 npm run test:browser
```

The Python suite has 61 tests and the Node UI suite has eleven. `TASKS.md`
contains no issue entries on this branch or main, so there was no issue to
move; its diff remains empty and its invariant checker passes. Browser fixtures
cover clicks, accelerating quiet strokes, weak echoes, FFT block boundaries,
silence, empty PCM and one stroke. Identical PCM must preserve counts, raw
counts, inferred indices, parameter selection and segment detection. Flux
error must remain below 1e-5, timestamps and intervals within one hop, and
volume within 0.001. These checks passed in both engines.

Browser-native resampling and compressed decoders are a separate boundary.
All eight known attacks in the 44.1 kHz mono WAV, 48 kHz stereo WAV, MP3 and
WebM/Opus fixtures matched native onset timestamps exactly at the four-decimal
output precision. Total detections on the noisy six-second fixture differed:

| File | Native | Chromium | Firefox |
| --- | ---: | ---: | ---: |
| Mono WAV, 44.1 kHz | 13 | 13 | 13 |
| Stereo WAV, 48 kHz | 13 | 11 | 13 |
| MP3, 44.1 kHz | 13 | 11 | 11 |
| WebM/Opus, 48 kHz | 11 | 11 | 11 |

Inspection localized differences to noise at the clip edges and an inferred
stroke near 3.013 seconds, not the eight generated attacks. Browser tests
therefore compare the known attacks and their intervals across decoders and
report the total counts, while requiring complete result parity on identical
PCM. This does not establish byte-identical FFmpeg/browser decoding or identical
results on arbitrary recordings. Files with more than two channels use channel
averaging; their downmix has not been compared with FFmpeg's layout-specific mix.

The browser suite also exercises upload, Auto-tune/manual reanalysis, local
playhead and chart seeking, source replacement, zero/one-stroke summaries,
corrupt/empty/oversized inputs, and runtime-load failure followed by retry.
It rejects analysis API calls, audio uploads and YouTube requests during local
analysis. Static assets are served under a path prefix in these tests.
Separate real-browser smoke checks passed with both documented servers:
`python3 -m http.server --directory dist 8000` and
`uv run uvicorn iskumetri.server:app --port 8000`. Both returned the canonical
Python source and analyzed a one-stroke WAV. Desktop and 390 px dark-mode
screenshots were inspected; no page errors or horizontal overflow occurred.

A 1199-second silent WAV decoded and analyzed with zero strokes in both engines;
a 1201-second file was rejected. Combined analysis and over-limit decode took
8.3 seconds in Chromium and 51.6 seconds in Firefox. A 50 ms main-thread timer
fired 157 and 1021 times respectively. Chromium reported about 127 MB of
main-thread JavaScript heap afterward. This excludes worker/WASM memory and is
not a peak-memory measurement; Firefox did not expose that counter. These are
Linux desktop smoke measurements, not mobile performance guarantees. Both
long-file checks passed before the final worker-retry fix; the normal browser
suite was rerun afterward.

### YouTube extraction blocker

The full requested YouTube URL → extracted downloadable audio → local analysis
flow remains blocked. No extracted audio Blob or working static downloader was
produced. The UI explicitly reports extraction as unavailable and keeps local
uploads usable. Native API endpoints remain available, but the static UI does
not use a hidden server fallback.

Reproduce the independent probe with:

```bash
node tools/probe_browser_extraction.mjs
```

On 2026-09-11, from an ordinary `http://127.0.0.1` origin in both browsers:

- YouTube's watch page returned no readable CORS response. Firefox reported
  HTTP 200 with the `Access-Control-Allow-Origin` header missing; Chromium
  reported the same missing-header policy failure.
- The player JSON POST was blocked at CORS/preflight. An alternate
  `youtubei.googleapis.com` host also failed. `mode: no-cors` returned an opaque
  response with status 0 and zero readable bytes, so it cannot supply audio.
- The oEmbed endpoint returned title/embed metadata successfully, but no media
  stream. This confirms external networking worked; oEmbed is not an extractor.
- yt-dlp 2026.8.19 imported in Pyodide with the SSL package loaded and
  pyodide-http 0.2.2 patching urllib. Chromium failed its initial webpage request
  with `NoSupportingHandlers` wrapping an XHR `NetworkError`. Firefox proceeded
  to the initial-data API and failed with `DownloadError` / `HTTP/1.1 0`.
- A second yt-dlp attempt used `innertube_host=youtubei.googleapis.com`, the
  `android_vr` player client and skipped webpage/config/initial-data requests.
  Its player request failed too. Firefox also reported denied `Origin` and
  `Accept-Encoding` headers. Neither attempt reached a usable player response,
  media download or JavaScript challenge execution.

Inspected [DLPro revision c23ae325](https://github.com/machineonamission/dlPro/tree/c23ae325a38f61a8b72061487e74f8b0f3120287),
including `core/worker/worker.js`, `dl.py` and `ffmpeg-bridge.js`. Its pinned
[HTTP fork, revision 755799ab](https://github.com/machineonamission/pyodide-http-dlpro/blob/755799ab028858790ee65be5c4d8021d99b7e462/pyodide_http/_core.py)
strips restricted headers, forwards origin-sensitive requests through a content
script and falls back to that proxy on status 0. The extension has cookies,
scripting and all-site permissions. It also supplies a custom JavaScript
challenge provider and bridges FFmpeg calls to WASM. Those facilities do not
remove the restrictions of an ordinary static origin. DLPro is AGPL-3.0;
no source was incorporated here.

This evidence blocks the tested browser-only routes, not every conceivable
future YouTube transport. A privileged extension or server proxy would change
the agreed deployment model and was not introduced. Review should treat upload
analysis as delivered and YouTube extraction/download as unresolved.


#### Proof (2026-09-11)

Header-level probes from this sandbox show that the blocker is YouTube's
CORS policy, not a gap in the browser probe above. The `Origin` request header
is set by the browser and cannot be changed by page script, so a static
GitHub Pages origin can never satisfy an allowlist that excludes third-party
origins. Commands, with `$URL` being a `videoplayback` URL from
`uv run --with 'yt-dlp>=2026.8.19' yt-dlp -g -f 'ba/ba*' <watch URL>`:

```bash
curl -sS -D - -o body.json -X POST -H "Origin: $ORIGIN" -H "Content-Type: application/json" \
  "https://www.youtube.com/youtubei/v1/player?prettyPrint=false" \
  --data '{"videoId":"NvIDlwzHRGQ","context":{"client":{"clientName":"WEB","clientVersion":"2.20260910.01.00"}}}'
curl -sS -D - -o /dev/null "https://www.youtube.com/youtubei/v1/player?videoId=NvIDlwzHRGQ&callback=cb"
curl -sS -D - -o /dev/null -r 0-1023 -H "Origin: $ORIGIN" "$URL"
curl -sS -D - -o /dev/null -X OPTIONS -H "Origin: https://example.github.io" \
  -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: range" "$URL"
```

| Request | `Origin: https://example.github.io` | `Origin: https://www.youtube.com` |
| --- | --- | --- |
| `POST youtubei/v1/player`, WEB client | 403, no `Access-Control-Allow-Origin` | 200 JSON, `Vary: Origin` |
| `GET videoplayback` (itag 251, Opus) | 206, body served, no `Access-Control-Allow-Origin` | 206, `Access-Control-Allow-Origin: https://www.youtube.com`, `Allow-Credentials: true` |
| `OPTIONS videoplayback` preflight | 400 | not tested |
| `GET youtubei/v1/player?callback=cb` (JSONP) | 405 | 405 |

The requests in each row were identical apart from the `Origin` header. The
youtube.com player response was itself `playabilityStatus: UNPLAYABLE` with no
formats, because a bare WEB client without YouTube's full header set is not a
working extractor; that row only shows that the gate is origin-based. Without
a CORS header the browser discards the `videoplayback` body, an `<audio>`
element playing it would be CORS-tainted for Web Audio and `captureStream`,
and obtaining the URL already requires the blocked player response. The
`videoplayback` URLs expire after hours and are bound to the client IP, so
only headers are recorded here.

DLPro was re-read to answer whether it avoids a proxy. It does not. Its
`manifest.json` requests the `scripting`, `cookies` and `storage` permissions
with `*://*/*` host permissions. The pinned HTTP fork first tries an ordinary
page-context `XMLHttpRequest` after stripping `origin`, `referer`,
`user-agent` and cookie headers; when a request needs an `Origin` or cookies,
or the XHR returns status 0 (a CORS failure), it calls `dlpro_proxy_send`.
`core/worker/xmlproxy_worker.js` posts that request over a message port,
`core/content/content.js` receives it inside the YouTube tab, and
`core/content/xmlproxy_content.js` performs the XHR from the youtube.com page
origin with `withCredentials`, using cookies that `background.js` obtained via
`chrome.cookies.getAll`. The README states the reason: "origin header can't
be faked, must be sent from origin". That relay is a proxy running inside the
user's browser, and content scripts, cookie access and all-site host
permissions exist only for extensions. No DLPro code was incorporated, so
the licence question does not arise.

One proxy-free route remains for getting YouTube audio into the static page:
recording the embedded player in real time with `getDisplayMedia` tab
capture. It is a recording rather than a download, it takes the video's full
duration, it requires the user to pick the tab and share its audio in
Chromium's picker, and Firefox ignores the `audio` option. A headed Chromium
149 probe under Xvfb with `--auto-select-tab-capture-source-by-title` and
`--use-fake-ui-for-media-stream` returned a tab video track
(`web-contents-media-stream://`, only when `displaySurface: 'browser'` was
requested) but its audio track was Chromium's fake input device with a 500 ms
beep pattern, not the tab's audio, and headed Chromium could not start inside
the sandbox at all. The route therefore cannot be verified automatically here
and is tracked in `TASKS.md` as an unverified proposal, not as a solution.


### AI implementation review

Review reproduced and fixed a worker-lifecycle race: a delayed `error` or
`messageerror` callback from a retired worker could terminate its replacement.
Callbacks now check worker identity. Both regression cases failed before the
fix and pass afterward.

Identical-PCM result comparisons now use the production `analysis-worker.js`,
including its parameter and JSON conversion, rather than obtaining analysis
results from the separate flux-check worker. The latter only computes the
intermediate flux envelope. This preserves the original numerical tolerances.

The extraction probe was rerun during review in both engines. Default yt-dlp
and the alternate Google API host still failed before a usable player response;
normal fetches showed the same missing CORS headers and opaque no-CORS result.
The extraction/download requirement remains blocked. The tracker diff is empty,
its content hash matches `main:TASKS.md`, and `tools/check_tasks_md.py` confirms
that no issue occurs under more than one heading.

Post-fix review checks passed: 61 Python tests, 11 Node tests, and both browser
suites including direct production-worker parity, runtime-failure recovery and
the 1199/1201-second cases. The static-server and FastAPI smoke checks also
passed again. All probe servers, test servers and browser processes were closed.
