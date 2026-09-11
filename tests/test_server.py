"""Offline tests for URL handling and the cache: yt-dlp is never allowed online."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from iskumetri import server

VARIANTS = [
    "https://www.youtube.com/watch?v=NvIDlwzHRGQ",
    "https://www.youtube.com/watch?v=NvIDlwzHRGQ&list=PLx&index=2",
    "https://youtu.be/NvIDlwzHRGQ?si=abc&t=10",
    "https://m.youtube.com/watch?feature=share&v=NvIDlwzHRGQ",
    "https://music.youtube.com/watch?v=NvIDlwzHRGQ",
    "https://www.youtube.com/shorts/NvIDlwzHRGQ",
    "https://www.youtube.com/embed/NvIDlwzHRGQ",
    "https://youtube.com/live/NvIDlwzHRGQ",
]


@pytest.mark.parametrize("url", VARIANTS)
def test_every_url_form_resolves_to_the_same_id(url: str) -> None:
    assert server.video_id_from_url(url) == "NvIDlwzHRGQ"


@pytest.mark.parametrize("url", ["https://www.youtube.com/playlist?list=PLx", "https://example.com/x", "nope"])
def test_non_video_urls_are_rejected(url: str) -> None:
    with pytest.raises(HTTPException) as e:
        server.video_id_from_url(url)
    assert e.value.status_code == 400


def test_cached_video_is_served_without_yt_dlp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "CACHE", tmp_path)
    (tmp_path / "NvIDlwzHRGQ.webm").write_bytes(b"not really audio")
    (tmp_path / "NvIDlwzHRGQ.info.json").write_text(json.dumps({"title": "Roll", "duration": 37}))

    def offline(*_: object, **__: object) -> None:
        raise AssertionError("yt-dlp must not be used for a cached video")

    monkeypatch.setattr(server.yt_dlp, "YoutubeDL", offline)

    paths = {server.fetch(server.video_id_from_url(u)) for u in VARIANTS}

    assert paths == {("Roll", tmp_path / "NvIDlwzHRGQ.webm")}
