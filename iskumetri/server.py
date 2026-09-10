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

from iskumetri.onsets import analyze

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("ISKUMETRI_CACHE", ROOT / "cache"))
CACHE.mkdir(parents=True, exist_ok=True)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/|live/)|youtu\.be/)",
)
MEDIA_TYPES = {".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg", ".mp3": "audio/mpeg"}
MAX_DURATION = 20 * 60  # s; analysis cost and disk use scale with length

app = FastAPI(title="Iskumetri")


class AnalyzeRequest(BaseModel):
    url: str
    # Bounded: sensitivity=0 divides by zero and yields an empty, confusing result.
    sensitivity: float = Field(1.0, ge=0.1, le=5.0)
    min_interval: float = Field(0.03, ge=0.005, le=1.0)


def _cached_audio(video_id: str) -> Path | None:
    return next((p for p in CACHE.glob(f"{video_id}.*") if p.suffix in MEDIA_TYPES), None)


def download(url: str) -> tuple[str, str, Path]:
    if not YOUTUBE_URL.match(url):
        raise HTTPException(400, "Only YouTube video URLs are supported")
    opts = {
        # Audio-only: a "best" fallback can return a video container whose
        # extension is not in MEDIA_TYPES, which reads as a download failure.
        "format": "bestaudio[ext=m4a]/bestaudio",
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
        video_id = info["id"]
        # Validate before this reaches a path or a glob pattern.
        if not VIDEO_ID.match(video_id):
            raise HTTPException(400, f"Unsupported video id: {video_id!r}")
        duration = info.get("duration") or 0
        if duration > MAX_DURATION:
            raise HTTPException(
                400,
                f"Video is {int(duration) // 60} min long; the limit is {MAX_DURATION // 60} min",
            )
        title = info.get("title") or video_id
        audio = _cached_audio(video_id)
        if audio is None:
            ydl.download([url])
            audio = _cached_audio(video_id)
        if audio is None:
            raise HTTPException(500, "Download produced no usable audio file")
    return video_id, title, audio


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest) -> dict:
    try:
        video_id, title, audio = download(req.url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(400, str(e)) from e
    result_path = CACHE / f"{video_id}.s{req.sensitivity:g}.w{req.min_interval:g}.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    result = {"video_id": video_id, "title": title, **analyze(audio, req.sensitivity, req.min_interval)}
    # Write then rename, so an interrupted write cannot leave a truncated cache
    # file that every later request would choke on.
    tmp = result_path.with_suffix(".partial")
    tmp.write_text(json.dumps(result))
    tmp.replace(result_path)
    return result


@app.get("/api/audio/{video_id}")
def api_audio(video_id: str) -> FileResponse:
    if not VIDEO_ID.match(video_id) or (audio := _cached_audio(video_id)) is None:
        raise HTTPException(404)
    return FileResponse(audio, media_type=MEDIA_TYPES[audio.suffix])


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
