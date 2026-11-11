"""pzdev sound check|install: the sound of `pzdev film --video` (loopback of the Windows default output, no microphone).

    python PZDevKit/pzdev.py sound check      ffmpeg in PATH, soundcard module, default output device (exit 0 when ready)
    python PZDevKit/pzdev.py sound install    pip install --target PZDevKit/.pydeps soundcard numpy, then check

The modules go to PZDevKit/.pydeps (git-ignored), never into the system Python. The test game itself needs the game
sound on: start it with PZAT_SOUND=1 (`set PZAT_SOUND=1` then `pzdev sp <Project> --no-quit`).
"""
from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys

from pzdev.recorder import DEPS

PACKAGES = ('soundcard', 'numpy')


def probe() -> tuple[bool, str]:
    """(ready, default output name or reason)."""
    if DEPS.is_dir() and str(DEPS) not in sys.path:
        sys.path.insert(0, str(DEPS))
    try:
        importlib.import_module('numpy')
        sc = importlib.import_module('soundcard')
        return True, sc.default_speaker().name
    except ImportError as e:
        return False, f'module {e.name} absent'
    except Exception as e:  # no output device, COM error...
        return False, f'no default output device ({e!r})'


def ffmpeg_present() -> bool:
    return shutil.which('ffmpeg') is not None


def check(probe=probe, ffmpeg=ffmpeg_present) -> int:
    has_ffmpeg = ffmpeg()
    ready, detail = probe()
    print('ffmpeg: ' + ('found' if has_ffmpeg else 'missing (FFmpeg 8 or newer in PATH, gfxcapture filter)'))
    print('sound: ' + (f'loopback of {detail}' if ready else detail))
    if not ready:
        print('fix: python PZDevKit/pzdev.py sound install')
    return 0 if has_ffmpeg and ready else 1


def install(run=None, probe=probe, ffmpeg=ffmpeg_present) -> int:
    argv = [sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', str(DEPS), *PACKAGES]
    print('installing: ' + ' '.join(PACKAGES) + f' into {DEPS}')
    code = (run or (lambda a: subprocess.run(a).returncode))(argv)
    if code != 0:
        print(f'ERROR: pip exited with {code}')
        return 2
    return check(probe=probe, ffmpeg=ffmpeg)


def main(argv: list[str] | None = None, run=None, probe=probe, ffmpeg=ffmpeg_present) -> int:
    p = argparse.ArgumentParser(prog='pzdev sound', description=__doc__.splitlines()[0])
    p.add_argument('action', choices=('check', 'install'))
    args = p.parse_args(argv)
    if args.action == 'check':
        return check(probe=probe, ffmpeg=ffmpeg)
    return install(run=run, probe=probe, ffmpeg=ffmpeg)
