"""Stage the static app and its canonical detector. Run from any directory."""
from pathlib import Path
from shutil import copy2

ROOT = Path(__file__).resolve().parent.parent


def build():
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    for source in (ROOT / 'static').iterdir():
        if source.is_file():
            copy2(source, output / source.name)
    copy2(ROOT / 'iskumetri' / 'onsets.py', output / 'onsets.py')


if __name__ == '__main__':
    build()
