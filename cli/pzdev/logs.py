"""pzdev logs: filtered extracts of the game log of the current session (console.txt is rewritten at each start).

    python PZDevKit/pzdev.py logs [--target cache:<dir>|real | --file PATH] [--server] [options]

Default: session summary (start, version, mods loaded, Lua loads, error counts, test results) and the last lines.
    --errors        Lua error blocks (message and Lua frames only); exit 1 when there is one
    --all-errors    every ERROR block (engine ones too, all frames kept short)
    --result        PZAT-RESULT lines of the automated tests
    --grep REGEX    matching lines
    --tail N        last N lines (default 20; with --grep: last N matches)
    --server        server-console.txt of the target instead of console.txt
Target as pzdev lua (default: the last `sp --no-quit` cache while it exists, else the real game folder).
Scenario reports come with `pzdev scenario` (step 7 of plan 001).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from pzdev import live

MAX_LINE = 300
START_RE = re.compile(r'^\S+\s*:\s*General\s+f:0> (\d\d-\d\d-\d{4} \d\d:\d\d:\d\d)$')
VERSION_RE = re.compile(r'f:\d+> version=(\S+ \S+)')
MOD_RE = re.compile(r'^LOG\s*:\s*Mod\s+f:\d+> loading (\S+)$')
RESULT_RE = re.compile(r'(PZAT-RESULT .*)$')


def cut(line: str) -> str:
    return line if len(line) <= MAX_LINE else line[:MAX_LINE - 3] + '...'


def last(items: list, n: int) -> list:
    return items[-n:] if n > 0 else []


def short_list(items: list[str], limit: int = 20) -> str:
    text = ', '.join(items[:limit])
    return text + (f' (+{len(items) - limit} more)' if len(items) > limit else '')


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding='utf-8', errors='replace').splitlines()


def log_file(target: str | None, server: bool) -> Path:
    root = live.resolve_target(target).parent
    return root / ('server-console.txt' if server else 'console.txt')


def blocks(lines: list[str]):
    """(first line, continuation lines) of every ERROR entry; continuation lines start with a tab."""
    i = 0
    while i < len(lines):
        if lines[i].startswith('ERROR'):
            j = i + 1
            while j < len(lines) and lines[j].startswith('\t'):
                j += 1
            yield lines[i], [ln.strip() for ln in lines[i + 1:j]]
            i = j
        else:
            i += 1


def is_lua(head: str, rest: list[str]) -> bool:
    return 'Lua(' in head or any(ln.startswith('Lua(') or 'KahluaException' in ln for ln in rest)


def error_blocks(lines: list[str], lua_only: bool) -> list[list[str]]:
    out = []
    for head, rest in blocks(lines):
        lua = is_lua(head, rest)
        if lua_only and not lua:
            continue
        if lua:
            kept = [ln for ln in rest if ln.startswith('Lua(') or 'Exception' in ln or ln.startswith('at ')]
        else:
            kept = [ln for ln in rest if ln != 'Stack trace:'][:3]
        out.append([cut(head)] + ['  ' + cut(ln) for ln in kept])
    return out


def summary(lines: list[str]) -> dict:
    start = next((m.group(1) for m in map(START_RE.match, lines[:5]) if m), None)
    version = next((m.group(1) for m in map(VERSION_RE.search, lines) if m), None)
    loads = [m.group(1) for m in map(MOD_RE.match, lines) if m]
    mods = list(dict.fromkeys(loads))
    lua_errors = other = 0
    for head, rest in blocks(lines):
        if is_lua(head, rest):
            lua_errors += 1
        else:
            other += 1
    return {'start': start, 'version': version, 'mods': mods,
            'luaLoads': loads.count(mods[0]) if mods else 0, 'luaErrors': lua_errors, 'otherErrors': other,
            'warnings': sum(1 for ln in lines if ln.startswith('WARN')), 'results': results(lines)}


def results(lines: list[str]) -> list[str]:
    return [m.group(1) for m in map(RESULT_RE.search, lines) if m]


def grep(lines: list[str], pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [ln for ln in lines if rx.search(ln)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev logs', description=__doc__.splitlines()[0])
    p.add_argument('--target')
    p.add_argument('--file', type=Path)
    p.add_argument('--server', action='store_true')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--errors', action='store_true')
    g.add_argument('--all-errors', action='store_true')
    g.add_argument('--result', action='store_true')
    g.add_argument('--grep')
    p.add_argument('--tail', type=int, default=20)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = args.file or log_file(args.target, args.server)
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    if not path.is_file():
        print(f'ERROR: no log at {path}')
        return 2
    lines = read_lines(path)
    if args.errors or args.all_errors:
        found = error_blocks(lines, lua_only=args.errors)
        for block in found:
            print('\n'.join(block))
        print(f'{len(found)} {"Lua " if args.errors else ""}error(s) in {path}')
        return 1 if found else 0
    if args.result:
        found = results(lines)
        print('\n'.join(found) if found else f'no PZAT-RESULT in {path}')
        return 0
    if args.grep:
        found = grep(lines, args.grep)
        for line in last(found, args.tail):
            print(cut(line))
        return 0
    s = summary(lines)
    print(f'{path}: started {s["start"]}, version {s["version"]}')
    print(f'mods ({len(s["mods"])}): {short_list(s["mods"]) or "none"} (Lua loads: {s["luaLoads"]})')
    print(f'Lua errors: {s["luaErrors"]}, other errors: {s["otherErrors"]}, warnings: {s["warnings"]}')
    for r in s['results']:
        print(r)
    print(f'--- last {args.tail} lines')
    for line in last(lines, args.tail):
        print(cut(line))
    return 0
