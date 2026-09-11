"""Reusable download, analysis and JSON storage stages; no HTTP dependencies."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import yt_dlp
from yt_dlp.extractor.youtube import YoutubeIE
from yt_dlp.utils import ExtractorError

from iskumetri.onsets import analyze, validate_params

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("ISKUMETRI_CACHE", ROOT / "cache"))
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
MEDIA_TYPES = {".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg", ".mp3": "audio/mpeg"}
MAX_DURATION = 20 * 60  # s; analysis cost and disk use scale with length
# Smallest stream that still detects strokes reliably: Opus at <=100 kbps matched the
# 130 kbps AAC result, while the 49 kbps HE-AAC stream (22 kHz core) lost ~10 % of
# strokes. Full-band streams only; HLS entries with unknown sample rate are skipped.
FORMAT = "bestaudio[abr<=100][asr>=44000]/worstaudio[asr>=44000]/bestaudio"
# Bump when the analysis output changes shape, so stale results are not served.
RESULT_VERSION = "v3"


def video_id_from_url(url: str) -> str:
    """Resolve youtube.com, youtu.be, shorts, embed, m. and music. URLs offline."""
    try:
        video_id = YoutubeIE.extract_id(url)
    except ExtractorError as e:
        raise ValueError("Only YouTube video URLs are supported") from e
    # Validate before this reaches a path or a glob pattern.
    if not VIDEO_ID.match(video_id):
        raise ValueError(f"Unsupported video id: {video_id!r}")
    return video_id


def cached_audio(video_id: str, cache: Path) -> Path | None:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid video id")
    return next((p for p in cache.glob(f"{video_id}.*") if p.suffix in MEDIA_TYPES), None)


def save_analysis(path: Path, obj: dict) -> None:
    """Atomically store JSON, with a distinct temporary file for each writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".partial", delete=False) as f:
        tmp = Path(f.name)
        try:
            json.dump(obj, f, allow_nan=False)
            f.close()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def load_analysis(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def fetch(video_id: str, cache: Path = CACHE) -> tuple[str, Path]:
    """Download audio and cache metadata; refresh legacy metadata without audio."""
    info_path = cache / f"{video_id}.info.json"
    audio = cached_audio(video_id, cache)
    cached = load_analysis(info_path)
    if audio is not None and cached is not None and "description" in cached:
        return cached["title"], audio
    cache.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"  # canonical: no playlist or timestamp
    opts = {
        "format": FORMAT,
        "outtmpl": str(cache / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # otherwise the progress bar floods the server log
        "cachedir": str(cache / "yt-dlp"),  # the default ~/.cache may be read-only
    }
    duration = 0
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise ValueError("Could not read video info")
            duration = info.get("duration") or 0
            if duration > MAX_DURATION:
                raise ValueError(
                    f"Video is {int(duration) // 60} min long; the limit is {MAX_DURATION // 60} min",
                )
            title = info.get("title") or video_id
            if audio is None:
                ydl.download([url])
                audio = cached_audio(video_id, cache)
            if audio is None:
                raise RuntimeError("Download produced no usable audio file")
    except (yt_dlp.utils.DownloadError, ValueError):
        if duration > MAX_DURATION:
            raise
        if audio is not None and cached is not None:
            return cached["title"], audio
        raise
    save_analysis(info_path, {"title": title, "duration": duration, "description": info.get("description") or ""})
    return title, audio


def analyze_video(
    url: str, sensitivity: float | None = None, min_interval: float | None = None,
    cache: Path = CACHE,
) -> dict:
    """Compose the independent stages for the web app or a future CLI."""
    validate_params(sensitivity, min_interval)
    video_id = video_id_from_url(url)
    title, audio = fetch(video_id, cache)
    auto = sensitivity is None or min_interval is None
    tag = "auto" if auto else f"s{sensitivity:g}.w{min_interval:g}"
    path = cache / f"{video_id}.{RESULT_VERSION}.{tag}.json"
    cached = load_analysis(path)
    if cached is not None:
        return cached
    params = (None, None) if auto else (sensitivity, min_interval)
    result = {"video_id": video_id, "title": title, **analyze(audio, *params)}
    save_analysis(path, result)
    return result
