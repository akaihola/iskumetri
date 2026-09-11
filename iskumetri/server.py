"""HTTP adapter for the reusable analysis pipeline."""

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from iskumetri import pipeline

app = FastAPI(title="Iskumetri")


class AnalyzeRequest(BaseModel):
    url: str
    # None means auto-tune. Bounded: sensitivity=0 divides by zero and yields an
    # empty, confusing result.
    sensitivity: float | None = Field(None, ge=0.1, le=5.0)
    min_interval: float | None = Field(None, ge=0.005, le=1.0)


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest) -> dict:
    try:
        return pipeline.analyze_video(req.url, req.sensitivity, req.min_interval)
    except (ValueError, yt_dlp.utils.DownloadError) as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/audio/{video_id}")
def api_audio(video_id: str) -> FileResponse:
    if not pipeline.VIDEO_ID.fullmatch(video_id) or (audio := pipeline.cached_audio(video_id, pipeline.CACHE)) is None:
        raise HTTPException(404)
    return FileResponse(audio, media_type=pipeline.MEDIA_TYPES[audio.suffix])


@app.get("/onsets.py")
def detector_source() -> FileResponse:
    return FileResponse(pipeline.ROOT / "iskumetri" / "onsets.py", media_type="text/plain")


app.mount("/", StaticFiles(directory=pipeline.ROOT / "static", html=True), name="static")
