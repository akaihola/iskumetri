"""Generate offline browser inputs and native oracle results in a temporary directory."""
import json
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np

from iskumetri.onsets import SR, analyze_pcm, analyze, onset_strength

helpers = runpy.run_path(str(Path(__file__).with_name('test_onsets.py')))
click_track, ramp = helpers['click_track'], helpers['ramp']
output = Path(sys.argv[1])
output.mkdir(exist_ok=True)
fast = ramp(.4, .06, 70)
# Real quiet attacks and weaker delayed echoes must survive/reject as before.
quiet = click_track(fast, duration=20, gains={t: .15 for t in fast[35:]})
echoes = quiet.copy()
echoes[660:] += .02 * quiet[:-660]
cases = {
    'clicks': click_track(helpers['CLICKS']),
    'ramp': quiet,
    'echoes': echoes,
    'block': click_track(list(np.arange(.5, 29.5, .25)), duration=30),
    'empty': np.zeros(0, dtype=np.float32),
    'silent': np.zeros(SR, dtype=np.float32),
    'single': np.zeros(SR, dtype=np.float32),
}
cases['single'][SR // 2] = 1
manifest = {}
for name, y in cases.items():
    y.tofile(output / f'{name}.f32')
    onset_strength(y).astype(np.float32).tofile(output / f'{name}.flux')
    manifest[name] = [analyze_pcm(y), analyze_pcm(y, 1.0, .03)]
# Exercise real browser decode and resampling, with FFmpeg as the decode oracle.
formats = {}
for name, rate, channels, extension in [('mono44', 44100, 1, 'wav'), ('stereo48', 48000, 2, 'wav'),
                                         ('mp3', 44100, 2, 'mp3'), ('opus', 48000, 2, 'webm')]:
    path = output / f'{name}.{extension}'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1',
                    '-i', str(output / 'clicks.f32'), '-ar', str(rate), '-ac', str(channels), str(path)], check=True)
    formats[path.name] = analyze(path, 1.0, .03)
for name in ['single', 'silent']:
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1',
                    '-i', str(output / f'{name}.f32'), str(output / f'{name}.wav')], check=True)
(output / 'expected.json').write_text(json.dumps({'pcm': manifest, 'files': formats, 'clicks': helpers['CLICKS']}))
