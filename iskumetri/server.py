"""FastAPI app: download a YouTube video's audio, detect onsets, serve the UI."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from yt_dlp.extractor.youtube import YoutubeIE
from yt_dlp.utils import ExtractorError

from iskumetri.onsets import analyze

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("ISKUMETRI_CACHE", ROOT / "cache"))
CACHE.mkdir(parents=True, exist_ok=True)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MEDIA_TYPES = {".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg", ".mp3": "audio/mpeg"}
MAX_DURATION = 20 * 60  # s; analysis cost and disk use scale with length
# Smallest stream that still detects strokes reliably: Opus at <=100 kbps matched the
# 130 kbps AAC result, while the 49 kbps HE-AAC stream (22 kHz core) lost ~10 % of
# strokes. Full-band streams only; HLS entries with unknown sample rate are skipped.
FORMAT = "bestaudio[abr<=100][asr>=44000]/worstaudio[asr>=44000]/bestaudio"
# Bump when the analysis output changes shape, so stale results are not served.
RESULT_VERSION = "v2"

app = FastAPI(title="Iskumetri")


class AnalyzeRequest(BaseModel):
    url: str
    # None means auto-tune. Bounded: sensitivity=0 divides by zero and yields an
    # empty, confusing result.
    sensitivity: float | None = Field(None, ge=0.1, le=5.0)
    min_interval: float | None = Field(None, ge=0.005, le=1.0)


def video_id_from_url(url: str) -> str:
    """Resolve youtube.com, youtu.be, shorts, embed, m. and music. URLs offline."""
    try:
        video_id = YoutubeIE.extract_id(url)
    except ExtractorError as e:
        raise HTTPException(400, "Only YouTube video URLs are supported") from e
    # Validate before this reaches a path or a glob pattern.
    if not VIDEO_ID.match(video_id):
        raise HTTPException(400, f"Unsupported video id: {video_id!r}")
    return video_id


def _cached_audio(video_id: str) -> Path | None:
    return next((p for p in CACHE.glob(f"{video_id}.*") if p.suffix in MEDIA_TYPES), None)


def _write_json(path: Path, obj: dict) -> None:
    # Write then rename, so an interrupted write cannot leave a truncated cache
    # file that every later request would choke on.
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)


def fetch(video_id: str) -> tuple[str, Path]:
    """Return (title, audio path), touching the network only for a new video."""
    info_path = CACHE / f"{video_id}.info.json"
    audio = _cached_audio(video_id)
    if audio is not None and info_path.exists():
        return json.loads(info_path.read_text())["title"], audio
    url = f"https://www.youtube.com/watch?v={video_id}"  # canonical: no playlist or timestamp
    opts = {
        "format": FORMAT,
        "outtmpl": str(CACHE / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # otherwise the progress bar floods the server log
        "cachedir": str(CACHE / "yt-dlp"),  # the default ~/.cache may be read-only
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise HTTPException(400, "Could not read video info")
        duration = info.get("duration") or 0
        if duration > MAX_DURATION:
            raise HTTPException(
                400,
                f"Video is {int(duration) // 60} min long; the limit is {MAX_DURATION // 60} min",
            )
        title = info.get("title") or video_id
        if audio is None:
            ydl.download([url])
            audio = _cached_audio(video_id)
        if audio is None:
            raise HTTPException(500, "Download produced no usable audio file")
    _write_json(info_path, {"title": title, "duration": duration})
    return title, audio


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest) -> dict:
    video_id = video_id_from_url(req.url)
    try:
        title, audio = fetch(video_id)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(400, str(e)) from e
    auto = req.sensitivity is None or req.min_interval is None
    tag = "auto" if auto else f"s{req.sensitivity:g}.w{req.min_interval:g}"
    result_path = CACHE / f"{video_id}.{RESULT_VERSION}.{tag}.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    params = (None, None) if auto else (req.sensitivity, req.min_interval)
    result = {"video_id": video_id, "title": title, **analyze(audio, *params)}
    _write_json(result_path, result)
    return result


@app.get("/api/audio/{video_id}")
def api_audio(video_id: str) -> FileResponse:
    if not VIDEO_ID.match(video_id) or (audio := _cached_audio(video_id)) is None:
        raise HTTPException(404)
    return FileResponse(audio, media_type=MEDIA_TYPES[audio.suffix])


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
