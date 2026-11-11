"""pzdev lua | repl | attach: live Lua channel to a running game (client/PZDevKit/Live.lua, protocol in
docs/specifications-techniques.md section 1).

    python PZDevKit/pzdev.py lua "<code>" [-f file.lua] [--shot] [--timeout S] [--target cache:<dir>|real]
    python PZDevKit/pzdev.py repl [--target ...]       one line = one command, empty line ignored, Ctrl+Z/Ctrl+D ends
    python PZDevKit/pzdev.py attach [--timeout S] [--target ...]

Target: cache:<dir> (a test game started with `pzdev sp --no-quit`, its cache folder), real (the game started by the
user with -debug and the batman_PZDevKit mod enabled), default: the last `sp --no-quit` cache while it exists, else
real. Exit codes: 0 ok, 2 Lua error, compile error or no answer.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

PROGRESS_S = 2.0
POLL_S = 0.1
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_DIR / 'runs' / 'live'


def default_pointer() -> Path:
    return Path(tempfile.gettempdir()) / 'pzdev' / 'last-live.json'


def default_user_dir() -> Path:
    return Path(os.environ.get('USERPROFILE') or str(Path.home())) / 'Zomboid'


def remember_cache(cache: Path, pointer: Path | None = None) -> None:
    """Called by `sp --no-quit`: the default target of the next live commands."""
    pointer = pointer or default_pointer()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({'cache': str(cache), 'at': time.time()}), encoding='utf-8')


def resolve_target(target: str | None, pointer: Path | None = None, user_dir: Path | None = None) -> Path:
    """Lua folder of the target game."""
    user_dir = user_dir or default_user_dir()
    if target is None:
        pointer = pointer or default_pointer()
        try:
            cache = Path(json.loads(pointer.read_text(encoding='utf-8'))['cache'])
        except (OSError, ValueError, KeyError):
            cache = None
        if cache is not None and (cache / 'Lua').is_dir():
            return cache / 'Lua'
        return user_dir / 'Lua'
    if target == 'real':
        return user_dir / 'Lua'
    if target.startswith('cache:'):
        return Path(target[len('cache:'):]) / 'Lua'
    raise ValueError(f'unknown target {target!r} (cache:<dir> or real)')


def next_id(channel: Path) -> str:
    """Strictly increasing id (milliseconds, above the last answered one)."""
    last = 0
    answer = read_header(channel / 'out.txt')
    if answer and answer.get('id', '').isdigit():
        last = int(answer['id'])
    return str(max(time.time_ns() // 1_000_000, last + 1))


def read_header(path: Path) -> dict | None:
    try:
        first = path.read_text(encoding='utf-8', errors='replace').split('\n', 1)[0]
    except OSError:
        return None
    if not first.startswith('--pzdev 1 '):
        return None
    return dict(part.split('=', 1) for part in first.split()[2:] if '=' in part)


def read_answer(path: Path, cmd_id: str) -> dict | None:
    """The complete answer to cmd_id (header, then lines up to --end), or None."""
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return None
    if not lines or '--end' not in lines:
        return None
    head = read_header(path)
    if not head or head.get('id') != cmd_id:
        return None
    body = lines[1:lines.index('--end')]
    shot = next((ln[5:].strip() for ln in body if ln.startswith('shot ')), None)
    return {'status': head.get('status', '?'), 'durationMs': head.get('durationMs'), 'lines': body, 'shot': shot}


def write_command(channel: Path, cmd_id: str, code: str, shot: bool, timeout_ms: int) -> None:
    channel.mkdir(parents=True, exist_ok=True)
    tmp, dst = channel / 'cmd.lua.tmp', channel / 'cmd.lua'
    tmp.write_text(f'--pzdev 1 id={cmd_id}{" shot" if shot else ""} timeoutMs={timeout_ms}\n{code}\n',
                   encoding='utf-8')
    for _ in range(20):  # the game may be reading the old file
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, dst)


def send(lua_dir: Path, code: str, shot: bool = False, timeout: float = 30.0, out_dir: Path | None = None,
         say=print) -> tuple[int, dict | None]:
    """Runs code in the game; prints progress at least every 2 s. (exit code, answer)."""
    if not lua_dir.is_dir():
        say(f'no Lua folder at {lua_dir}: wrong target (the game creates it at its first start)')
        return 2, None
    channel = lua_dir / 'pzdev'
    cmd_id = next_id(channel)
    write_command(channel, cmd_id, code, shot, int(timeout * 1000))
    start = last_say = time.monotonic()
    answer = None
    while True:
        answer = read_answer(channel / 'out.txt', cmd_id)
        if answer is not None:
            break
        now = time.monotonic()
        if now - start >= timeout:
            say(f'no answer after {timeout:.0f} s: is the game running with -debug, in game (not in the menu), '
                f'with batman_PZDevKit enabled? channel {channel}')
            return 2, None
        if now - last_say >= PROGRESS_S:
            last_say = now
            say(f'waiting for the game... {now - start:.0f} s')
        time.sleep(POLL_S)
    for line in answer['lines']:
        if not line.startswith('shot '):
            say(line)
    if answer['shot']:
        pic = copy_shot(lua_dir.parent / 'Screenshots' / answer['shot'], out_dir or DEFAULT_OUT, say)
        answer['shot_path'] = pic
    if answer['status'] != 'ok':
        say(f'status {answer["status"]}')
        return 2, answer
    return 0, answer


def copy_shot(src: Path, out_dir: Path, say, wait: float = 5.0) -> Path | None:
    """The game writes the screenshot at its next frame: wait for a stable file, then copy it."""
    start, size = time.monotonic(), -1
    while time.monotonic() - start < wait:
        if src.is_file():
            now = src.stat().st_size
            if now > 0 and now == size:
                out_dir.mkdir(parents=True, exist_ok=True)
                dst = out_dir / src.name
                shutil.copy2(src, dst)
                say(f'screenshot: {dst}')
                return dst
            size = now
        time.sleep(0.2)
    say(f'screenshot not found: {src}')
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev', description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('lua', 'repl', 'attach'):
        s = sub.add_parser(name)
        s.add_argument('--target', help='cache:<dir> or real (default: last sp --no-quit cache, else real)')
        s.add_argument('--timeout', type=float, default=10.0 if name == 'attach' else 30.0,
                       help='seconds to wait for each answer')
        if name == 'lua':
            s.add_argument('code', nargs='?', help='Lua chunk ("return" optional)')
            s.add_argument('-f', '--file', type=Path, help='Lua file instead of code')
            s.add_argument('--shot', action='store_true', help='game screenshot after the command')
    return p


def main(argv: list[str] | None = None, out_dir: Path | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        lua_dir = resolve_target(args.target)
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    if args.command == 'attach':
        print(f'target: {lua_dir}')
        code, answer = send(lua_dir, 'return "pong"', timeout=args.timeout, out_dir=out_dir)
        if code == 0 and answer and '-> pong' in answer['lines']:
            print('attached: the game answers on the live channel')
            return 0
        return 2
    if args.command == 'lua':
        if args.file:
            code_text = args.file.read_text(encoding='utf-8')
        elif args.code:
            code_text = args.code
        else:
            print('ERROR: give Lua code or -f file.lua')
            return 2
        return send(lua_dir, code_text, shot=args.shot, timeout=args.timeout, out_dir=out_dir)[0]
    print(f'pzdev repl on {lua_dir} (one line per command; end of input quits)')
    for line in sys.stdin:  # a Lua error in the REPL is shown, not fatal
        line = line.strip()
        if line:
            send(lua_dir, line, timeout=args.timeout, out_dir=out_dir)
    return 0
