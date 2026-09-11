"""Offline tests for URL handling and the cache: yt-dlp is never allowed online."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from iskumetri import server, pipeline

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
    assert pipeline.video_id_from_url(url) == "NvIDlwzHRGQ"


@pytest.mark.parametrize("url", ["https://www.youtube.com/playlist?list=PLx", "https://example.com/x", "nope"])
def test_non_video_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        pipeline.video_id_from_url(url)


def test_cached_video_is_served_without_yt_dlp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "NvIDlwzHRGQ.webm").write_bytes(b"not really audio")
    (tmp_path / "NvIDlwzHRGQ.info.json").write_text(json.dumps({"title": "Roll", "duration": 37, "description": ""}))

    def offline(*_: object, **__: object) -> None:
        raise AssertionError("yt-dlp must not be used for a cached video")

    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", offline)

    paths = {pipeline.fetch(pipeline.video_id_from_url(u), tmp_path) for u in VARIANTS}

    assert paths == {("Roll", tmp_path / "NvIDlwzHRGQ.webm")}


@pytest.mark.parametrize('description', ['', 'Drum roll\nDescription é'])
def test_legacy_description_refresh(tmp_path, monkeypatch, description):
    video = 'NvIDlwzHRGQ'
    (tmp_path / f'{video}.webm').touch()
    pipeline.save_analysis(tmp_path / f'{video}.info.json', {'title': 'Roll', 'duration': 37})
    calls = []

    class Downloader:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert not download
            calls.append(url)
            return {'title': 'Roll', 'duration': 37, 'description': description}
        def download(self, urls): pytest.fail('must not download cached audio')

    monkeypatch.setattr(pipeline.yt_dlp, 'YoutubeDL', Downloader)
    for _ in range(2):
        pipeline.fetch(video, tmp_path)
    assert len(calls) == 1
    assert pipeline.load_analysis(tmp_path / f'{video}.info.json')['description'] == description


def test_legacy_refresh_failure_retains_cache(tmp_path, monkeypatch):
    video = 'NvIDlwzHRGQ'
    audio = tmp_path / f'{video}.webm'
    audio.touch()
    metadata = {'title': 'Roll', 'duration': 37}
    pipeline.save_analysis(tmp_path / f'{video}.info.json', metadata)
    def fail(*args): raise pipeline.yt_dlp.utils.DownloadError('offline')
    monkeypatch.setattr(pipeline.yt_dlp, 'YoutubeDL', fail)
    assert pipeline.fetch(video, tmp_path) == ('Roll', audio)
    assert pipeline.load_analysis(tmp_path / f'{video}.info.json') == metadata


def test_analysis_cache_keys_and_version(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, 'fetch', lambda *args: ('Roll', tmp_path / 'audio'))
    def analyze(path, *params):
        calls.append(params)
        return {'onsets': [1, 2]}
    monkeypatch.setattr(pipeline, 'analyze', analyze)
    url = VARIANTS[0]
    for _ in range(2):
        pipeline.analyze_video(url, cache=tmp_path)
        pipeline.analyze_video(url, 1, .03, tmp_path)
    assert calls == [(None, None), (1, .03)]
    monkeypatch.setattr(pipeline, 'RESULT_VERSION', 'next')
    pipeline.analyze_video(url, cache=tmp_path)
    assert len(calls) == 3


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), 6])
def test_callable_validates_parameters(value, tmp_path):
    with pytest.raises(ValueError):
        pipeline.analyze_video(VARIANTS[0], value, .03, tmp_path)


@pytest.mark.parametrize('error,code', [(ValueError('bad URL'), 400),
    (pipeline.yt_dlp.utils.DownloadError('offline'), 400), (RuntimeError('no audio'), 500)])
def test_http_errors(monkeypatch, error, code):
    def fail(*args): raise error
    monkeypatch.setattr(pipeline, 'analyze_video', fail)
    with pytest.raises(HTTPException) as e:
        server.api_analyze(server.AnalyzeRequest(url=VARIANTS[0]))
    assert e.value.status_code == code


def test_pipeline_import_has_no_http_or_filesystem_side_effect(tmp_path):
    import os
    import subprocess
    import sys
    cache = tmp_path / 'absent'
    subprocess.run([sys.executable, '-c',
        'import sys; import iskumetri.pipeline; assert "fastapi" not in sys.modules'],
        env={**os.environ, 'ISKUMETRI_CACHE': str(cache)}, check=True)
    assert not cache.exists()


def test_failed_json_write_preserves_previous_result(tmp_path):
    path = tmp_path / 'result.json'
    pipeline.save_analysis(path, {'onsets': [1]})
    with pytest.raises(ValueError):
        pipeline.save_analysis(path, {'bad': float('nan')})
    assert pipeline.load_analysis(path) == {'onsets': [1]}
    assert not list(tmp_path.glob('*.partial'))


@pytest.mark.parametrize('duration', [37, pipeline.MAX_DURATION + 1])
def test_download_checks_duration_before_writing_audio(tmp_path, monkeypatch, duration):
    calls = []
    class Downloader:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            return {'title': 'Roll', 'duration': duration, 'description': 'Practice'}
        def download(self, urls):
            calls.append(urls)
            (tmp_path / 'NvIDlwzHRGQ.webm').touch()
    monkeypatch.setattr(pipeline.yt_dlp, 'YoutubeDL', Downloader)
    if duration > pipeline.MAX_DURATION:
        with pytest.raises(ValueError, match='limit'):
            pipeline.fetch('NvIDlwzHRGQ', tmp_path)
        assert not calls
    else:
        assert pipeline.fetch('NvIDlwzHRGQ', tmp_path)[0] == 'Roll'
        assert len(calls) == 1
        assert pipeline.load_analysis(tmp_path / 'NvIDlwzHRGQ.info.json')['description'] == 'Practice'


def test_legacy_refresh_does_not_bypass_duration_limit(tmp_path, monkeypatch):
    (tmp_path / 'NvIDlwzHRGQ.webm').touch()
    pipeline.save_analysis(tmp_path / 'NvIDlwzHRGQ.info.json', {'title': 'Roll', 'duration': 37})
    class Downloader:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs):
            return {'duration': pipeline.MAX_DURATION + 1}
    monkeypatch.setattr(pipeline.yt_dlp, 'YoutubeDL', Downloader)
    with pytest.raises(ValueError, match='limit'):
        pipeline.fetch('NvIDlwzHRGQ', tmp_path)


def test_detector_source_is_the_canonical_file():
    response = server.detector_source()
    assert response.path == pipeline.ROOT / 'iskumetri' / 'onsets.py'
    assert response.media_type == 'text/plain'
    assert response.path.is_file()
