"""pzdev scenario: the scenario engine (PZDevKit.Scenario, formerly PZPuppeteer) through the live channel.

    run FILE.lua [-P name=value ...]       copy FILE to Zomboid/Lua/PZPuppet/scenarios/pzdev/ of the target and run it
    run --path REL.lua [-P ...]            run a file already under Zomboid/Lua/PZPuppet/scenarios/
    run --name REGISTERED [-P ...]         run a scenario registered by a mod (PZDevKit.Scenario.register)
    batch --path PLAN.lua [-P ...]         run a batch plan (needs `scenario collect` running for the archive ACK)
    status | stop
    collect --output DIR [--user DIR] [--seconds S]   archive reports, acknowledge batch children

run follows the scenario until its report (progress at least every 2 s) and prints the report. Exit codes: 0 passed,
1 failed or cancelled, 2 Lua error, no answer or --timeout reached (the scenario is then stopped).
A scenario file returns function(params) building PZDevKit.Scenario.scenario(...) (examples/scenarios/).
Common options: --target cache:<dir>|real, --timeout S (whole run, default 600).
"""
from __future__ import annotations

import argparse
import re
import shutil
import time
from pathlib import Path

from pzdev import live
from pzdev.world import lua_str

FOLDER = 'pzdev'
PATH_RE = re.compile(r'^[A-Za-z0-9_/-]+\.lua$')


def lua_params(items: list[str]) -> str:
    out = []
    for item in items:
        if '=' not in item:
            raise ValueError(f'expected name=value, got {item!r}')
        name, value = item.split('=', 1)
        if not name.isidentifier():
            raise ValueError(f'bad parameter name {name!r}')
        try:
            number = float(value)
            literal = str(int(number)) if number.is_integer() and 'e' not in value.lower() else repr(number)
        except ValueError:
            literal = lua_str(value)
        out.append(f'{name} = {literal}')
    return '{ ' + ', '.join(out) + ' }'


def install(lua_dir: Path, source: Path) -> str:
    """Copies a scenario file below PZPuppet/scenarios/pzdev/ of the target; returns its relative path."""
    name = re.sub(r'[^A-Za-z0-9_-]', '_', source.stem) + '.lua'
    dst = lua_dir / 'PZPuppet' / 'scenarios' / FOLDER / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dst)
    return f'{FOLDER}/{name}'


def start_code(kind: str, target: str, params: str) -> str:
    S = 'local S = PZDevKit.Scenario\n'
    if kind == 'name':
        return S + f'local r = S.run({lua_str(target)}, nil, {params}); return r.runToken'
    if kind == 'batch':
        return S + f'local b = S.runBatchFile({lua_str(target)}, nil, {params}); return b.token, b.status'
    return S + f'local r = S.runFile({lua_str(target)}, nil, {params}); return r.runToken'


POLL_CODE = ('local S = PZDevKit.Scenario\nlocal r = S.lastReport\nlocal s = S.status() or {}\n'
             'return r and r.runToken or "", r and r.status or "none", s.label or "", r and r.reason or ""')


def values(answer: dict | None) -> list[str]:
    return [ln[3:] for ln in (answer or {}).get('lines', []) if ln.startswith('-> ')]


def quiet(*_args, **_kw):
    pass


STOP_CODE = 'PZDevKit.Scenario.stop("pzdev: {why}")'


def follow(lua_dir: Path, token: str, timeout: float, send=live.send, say=print, clock=time.monotonic,
           sleep=time.sleep, stall: float | None = None, stop_code: str | None = None) -> int:
    """Polls the report until it ends. timeout: whole run; stall: seconds without a step change (None: no limit).
    Both stop the scenario with stop_code (default PZDevKit.Scenario.stop) and give 2."""
    start = last_say = changed = clock()
    label = None
    stop = (stop_code or STOP_CODE.format(why='timeout')) + '; return "stopped"'
    while True:
        code, answer = send(lua_dir, POLL_CODE, timeout=10, say=quiet)
        if code != 0:
            say('no answer from the game while following the scenario')
            return 2
        run_token, status, step, reason = (values(answer) + ['', '', '', ''])[:4]
        if run_token != token:
            say(f'another scenario report is current ({run_token}): stopped following {token}')
            return 2
        now = clock()
        if status != 'running':
            report = lua_dir / 'PZPuppet' / 'reports' / f'{token}.txt'
            if report.is_file():
                say(report.read_text(encoding='utf-8', errors='replace').rstrip())
            say(f'scenario {status}' + (f': {reason}' if reason else '') + f' (report {report})')
            return 0 if status == 'passed' else 1
        if step != label:
            changed = now
        if step != label or now - last_say >= live.PROGRESS_S:
            say(f'running {now - start:.0f} s: {step}')
            label, last_say = step, now
        if now - start >= timeout:
            send(lua_dir, stop, timeout=10, say=quiet)
            say(f'timeout after {timeout:.0f} s: scenario stopped')
            return 2
        if stall is not None and now - changed >= stall:
            send(lua_dir, stop, timeout=10, say=quiet)
            say(f'no change for {stall:.0f} s on step {step!r}: scenario stopped (see pzdev logs --errors)')
            return 2
        sleep(1.0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev scenario', description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='action', required=True)
    for name in ('run', 'batch', 'status', 'stop'):
        s = sub.add_parser(name)
        s.add_argument('--target')
        s.add_argument('--timeout', type=float, default=600.0)
        if name in ('run', 'batch'):
            s.add_argument('-P', '--param', action='append', default=[], metavar='NAME=VALUE')
            s.add_argument('--path', help='file relative to Zomboid/Lua/PZPuppet/scenarios/')
        if name == 'run':
            s.add_argument('file', nargs='?', type=Path)
            s.add_argument('--name', help='registered scenario name')
    s = sub.add_parser('collect', add_help=False)
    s.add_argument('rest', nargs=argparse.REMAINDER)
    return p


def main(argv: list[str] | None = None, send=live.send, sleep=time.sleep) -> int:
    argv = list(argv or [])
    if argv[:1] == ['collect']:
        from pzdev import collect
        return collect.main(argv[1:])
    args = build_parser().parse_args(argv)
    try:
        lua_dir = live.resolve_target(args.target)
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    if args.action == 'status':
        code, answer = send(lua_dir, POLL_CODE, timeout=10, say=quiet)
        if code == 0:
            token, status, step, reason = (values(answer) + ['', '', '', ''])[:4]
            print(f'{status} {token} {step} {reason}'.strip())
        return code
    if args.action == 'stop':
        return send(lua_dir, 'PZDevKit.Scenario.stop("pzdev scenario stop"); return "stopped"', timeout=10)[0]
    try:
        params = lua_params(args.param)
        if args.action == 'batch':
            if not args.path:
                raise ValueError('batch needs --path PLAN.lua (relative to Zomboid/Lua/PZPuppet/scenarios/)')
            kind, target = 'batch', args.path
        elif args.name:
            kind, target = 'name', args.name
        elif args.path:
            kind, target = 'path', args.path
        elif args.file:
            if not args.file.is_file():
                raise ValueError(f'no file {args.file}')
            if not lua_dir.is_dir():
                raise ValueError(f'no Lua folder at {lua_dir}')
            kind, target = 'path', install(lua_dir, args.file)
            print(f'scenario file copied to {lua_dir / "PZPuppet" / "scenarios" / target}')
        else:
            raise ValueError('give a FILE, --path or --name')
        if kind != 'name' and not PATH_RE.match(target):
            raise ValueError(f'scenario paths use letters, digits, _ - / and end with .lua: {target!r}')
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    code, answer = send(lua_dir, start_code(kind, target, params), timeout=30)
    if code != 0:
        return 2
    if kind == 'batch':
        print('batch started: follow it with `pzdev scenario status`; `pzdev scenario collect` must be running')
        return 0
    token = (values(answer) + [''])[0]
    print(f'run token {token}')
    return follow(lua_dir, token, args.timeout, send=send, sleep=sleep)
