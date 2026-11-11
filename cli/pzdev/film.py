"""pzdev film: shoot a PZDevKit production (formerly PZDirector tools/tournage.py) through the live channel, without
a Java agent.

    python PZDevKit/pzdev.py film FILE.lua [-P name=value ...] [--video [--no-audio] [--size 1600x900]]
    python PZDevKit/pzdev.py film --path REL.lua ...       a file already under Zomboid/Lua/PZPuppet/scenarios/

The game must already be open with batman_PZDevKit and -debug: a test game left open by
`pzdev sp <Project> --no-quit` (set PZAT_SOUND=1 for a video with the game sound), or the user's own game
(--target real). FILE returns function(params) building PZDevKit.Production.production(...) or .scene(...)
(examples/productions/). During the take: Lua debugger popup off and player windows recreated (restored after);
with --video, game window 1600x900 (a borderless foreground game freezes the window capture), FFmpeg gfxcapture of
the window only and the Windows output sound. A step without change for --stall seconds stops the take.

Results in --out (default PZDevKit/runs/film/<date>_<name>/): take.json (status, markers, screenshots, video),
PZDirector_*.png written by :screenshot and still= during the take, and with --video take.mp4, video.mp4,
audio.wav, capture.json, ffmpeg.log. Exit codes: 0 passed, 1 failed or cancelled, 2 error, no game or stopped.
Look at the images: a passed report proves neither the framing nor a clean screen.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import re
import shutil
import time
from pathlib import Path

from pzdev import live, recorder, scenario

PROJECT_DIR = Path(__file__).resolve().parents[2]
STOP = 'PZDevKit.Production.stop("{why}")'


def foreground_game() -> None:
    """Aiming uses the game cursor: bring the window forward (the window capture works in the background too)."""
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
    except (AttributeError, OSError):
        return
    hwnd = user32.FindWindowW(None, 'Project Zomboid')
    if not hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def first(answer) -> str:
    return (scenario.values(answer) + [''])[0]


def windowed_mode(lua_dir, send, width: int, height: int, sleep):
    code, answer = send(lua_dir, 'local c=getCore(); return c:getScreenWidth(), c:getScreenHeight(), c:isFullScreen(), '
                                 'c:getOptionBorderlessWindow()', timeout=10, say=scenario.quiet)
    vals = scenario.values(answer)
    if code != 0 or len(vals) < 4:
        raise RuntimeError('display mode unreadable')
    before = {'w': int(float(vals[0])), 'h': int(float(vals[1])), 'full': vals[2] == 'true', 'borderless': vals[3] == 'true'}
    if (before['w'], before['h'], before['full'], before['borderless']) != (width, height, False, False):
        send(lua_dir, f'local c=getCore(); c:setOptionBorderlessWindow(false); '
                      f'c:setResolutionAndFullScreen({width},{height},false); return true', timeout=10, say=scenario.quiet)
        sleep(3)
        print(f'display: {width}x{height} window for the take (was {before["w"]}x{before["h"]})')
    return before


def restore_mode(lua_dir, send, before, sleep) -> None:
    if not before:
        return
    send(lua_dir, f"local c=getCore(); c:setOptionBorderlessWindow({str(before['borderless']).lower()}); "
                  f"c:setResolutionAndFullScreen({before['w']},{before['h']},{str(before['full']).lower()}); "
                  'return true', timeout=10, say=scenario.quiet)
    sleep(3)


def collect_screenshots(shots: Path, started: float, out: Path) -> list[str]:
    copied = []
    if shots.is_dir():
        for path in sorted(shots.glob('PZDirector_*.png'), key=lambda p: p.stat().st_mtime):
            if path.stat().st_mtime >= started - 1:
                shutil.copy2(path, out / path.name)
                copied.append(path.name)
    return sorted(copied)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev film', description=__doc__.splitlines()[0])
    p.add_argument('file', nargs='?', type=Path)
    p.add_argument('--path', help='file relative to Zomboid/Lua/PZPuppet/scenarios/')
    p.add_argument('-P', '--param', action='append', default=[], metavar='NAME=VALUE')
    p.add_argument('--target')
    p.add_argument('--video', action='store_true')
    p.add_argument('--no-audio', action='store_true')
    p.add_argument('--size', default='1600x900')
    p.add_argument('--out', type=Path)
    p.add_argument('--minutes', type=float, default=30)
    p.add_argument('--stall', type=float, default=90)
    return p


def main(argv: list[str] | None = None, send=live.send, sleep=time.sleep) -> int:
    args = build_parser().parse_args(argv)
    size = re.fullmatch(r'(\d+)x(\d+)', args.size)
    try:
        if not size:
            raise ValueError('--size expects WIDTHxHEIGHT')
        if args.video and not recorder.ffmpeg_available():
            raise ValueError('ffmpeg not found in PATH (needed by --video)')
        params = scenario.lua_params(args.param)
        lua_dir = live.resolve_target(args.target)
        if not args.path and not (args.file and args.file.is_file()):
            raise ValueError('give an existing FILE.lua or --path')
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    code, answer = send(lua_dir, 'return PZDevKit.Production.VERSION', timeout=15, say=scenario.quiet)
    if code != 0 or not first(answer) or first(answer) == 'nil':
        print('ERROR: no game with batman_PZDevKit answers: open one with `pzdev sp <Project> --no-quit` '
              '(PZAT_SOUND=1 for sound) or start your own -debug game and use --target real')
        return 2
    path = args.path or scenario.install(lua_dir, args.file)
    if not scenario.PATH_RE.match(path):
        print(f'ERROR: bad scenario path {path!r}')
        return 2
    name = Path(path).stem
    out = args.out or PROJECT_DIR / 'runs' / 'film' / f'{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_{name}'
    out.mkdir(parents=True, exist_ok=True)
    root = lua_dir.parent
    markers = []
    take = recorder.Recorder(out, audio=not args.no_audio) if args.video else None

    def on_mark(kind, label):
        markers.append({'kind': kind, 'name': label, 'time': time.strftime('%H:%M:%S')})
        print(f'{kind} {label}')
        if take:
            take.mark(kind, label)

    watcher = recorder.ConsoleWatcher(root / 'console.txt', on_mark)
    watcher.start()
    started = time.time()
    _, answer = send(lua_dir, 'local was=UIManager.isShowLuaDebuggerOnError(); UIManager.setShowLuaDebuggerOnError(false); '
                              'if getPlayerInventory(0)==nil then createPlayerData(0) end; '
                              'return was, getPlayerInventory(0)~=nil', timeout=10, say=scenario.quiet)
    debugger = (scenario.values(answer) + ['true'])[0]
    display, capture, status, error, code = None, None, None, None, 2
    try:
        if args.video:
            display = windowed_mode(lua_dir, send, int(size[1]), int(size[2]), sleep)
            take.start()
            print(f'recording: {out}')
        foreground_game()
        ok, answer = send(lua_dir, f'local S = PZDevKit.Scenario\nlocal r = S.runFile({json.dumps(path)}, '
                                   f'{{playerIndex=0}}, {params}); return r.runToken', timeout=30)
        token = first(answer)
        if ok != 0 or not token:
            raise RuntimeError('the take did not start (see the error above)')
        print(f'take started, run token {token}')
        code = scenario.follow(lua_dir, token, args.minutes * 60, send=send, sleep=sleep, stall=args.stall,
                               stop_code=STOP.format(why='pzdev film: stopped'))
        status = {0: 'passed', 1: 'failed'}.get(code, 'stopped')
    except RuntimeError as failure:
        error = str(failure)
        print(f'ERROR: {error}')
    finally:
        sleep(2)  # last frames and console lines
        if take:
            capture = take.stop()
        watcher.stop()
        restore_mode(lua_dir, send, display, sleep)
        send(lua_dir, f'UIManager.setShowLuaDebuggerOnError({"true" if debugger == "true" else "false"}); return true',
             timeout=10, say=scenario.quiet)
    stills = collect_screenshots(root / 'Screenshots', started, out)
    summary = {'scenario': path, 'params': args.param, 'status': status, 'exitCode': code, 'error': error,
               'markers': markers, 'screenshots': stills, 'video': capture}
    (out / 'take.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'{len(stills)} screenshot(s)' + (f', video {capture.get("video")}' if capture else '') + f'; results: {out}')
    if capture and capture.get('errors'):
        print('video: ' + '; '.join(capture['errors']))
    return code
