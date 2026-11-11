"""pzdev sp|server|mp|check: unattended Project Zomboid 42 tests (solo, dedicated server, server + clients).
Windows only. Formerly pz-autotest.

    python PZDevKit/pzdev.py sp     <project> [-P name=value ...] [options]
    python PZDevKit/pzdev.py server <project> [-P name=value ...] [options]
    python PZDevKit/pzdev.py mp     <project> [--clients N] [--client-run] [options]
    python PZDevKit/pzdev.py check  <project>          configuration and mods only

<project> is a folder holding autotest.json (or the file itself). See README.md for the configuration.
Exit codes: 0 ok, 1 tests failed, 2 timeout / start failure / error, 3 a game or server is already running.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pzdev import core
from pzdev.launcher import Env, Options, Runner, log


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev', description=__doc__.splitlines()[0])
    p.add_argument('mode', choices=core.MODES + ('check',))
    p.add_argument('project', type=Path, help='project folder holding autotest.json, or the file')
    p.add_argument('-P', '--param', action='append', default=[], metavar='NAME=VALUE',
                   help='hook parameter (ctx.params.NAME), repeatable; overrides the configuration "params"')
    p.add_argument('--lua', help='Lua code run at start instead of the configured hooks (P = ctx.params); its '
                                 'return value is the result ({ok=, summary=, lines=} or a value)')
    p.add_argument('--done-lua', help='with --lua: Lua expression polled until true (end of the run)')
    p.add_argument('--save', help='sp: save folder or glob pattern (default: sp.save of the configuration)')
    p.add_argument('--game-mode', help='sp: Saves/<mode> folder (default Sandbox)')
    p.add_argument('--timeout', type=int, help='seconds from the launch to the result (default: configuration)')
    p.add_argument('--menu-timeout', type=int, default=300, help='sp: seconds for the driver to reach the menu')
    p.add_argument('--quit-timeout', type=int, default=120, help='seconds for a game/server to exit after the end')
    p.add_argument('--wait-idle', type=int, default=0,
                   help='seconds to wait until no java.exe / ProjectZomboid64.exe runs (else exit 3)')
    p.add_argument('--start-delay', type=int, help='seconds in game before the run')
    p.add_argument('--lua-timeout', type=int, default=0, help='seconds for the done hook, checked in Lua (0 = none)')
    p.add_argument('--bridge', choices=('auto', 'on', 'off', 'offline'),
                   help='external bridge of the configuration (default: bridge.default, else auto)')
    p.add_argument('--clients', type=int, help='mp: number of clients (default mp.clients, else 1)')
    p.add_argument('--client-run', action='store_true', default=None,
                   help='mp: client 1 also runs the client hooks (others stay idle)')
    p.add_argument('--server-debug', action='store_true',
                   help='server, mp: run the dedicated server with the Java property -Ddebug '
                        '(the -debug argument of a client is ignored by GameServer)')
    p.add_argument('--no-quit', action='store_true', help='sp: leave the game open at the end')
    p.add_argument('--no-screenshot', action='store_true')
    p.add_argument('--keep-cache', action='store_true', help='keep the temporary caches even on success')
    p.add_argument('--out', type=Path, help='result folder (default <project>/runs/<date>-<mode>-<token>)')
    p.add_argument('--dry-run', action='store_true', help='build the caches and print the commands, launch nothing')
    return p


def main(argv=None, env: Env | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.platform != 'win32' and env is None:
        log('ERROR: pzdev runs on Windows only (game window, tasklist, taskkill)')
        return core.EXIT_ERROR
    try:
        project = core.load_project(args.project)
        params = core.parse_params(args.param)
    except core.ConfigError as e:
        log(f'ERROR: {e}')
        return core.EXIT_ERROR
    if args.mode == 'check':
        try:
            for mod_id, src in core.resolve_mods(project):
                log(f'mod {mod_id}: {src}')
            for mode in core.MODES:
                if mode in project.conf:
                    core.hooks_text(project, mode)
                    log(f'{mode}: hooks ok')
        except core.ConfigError as e:
            log(f'ERROR: {e}')
            return core.EXIT_ERROR
        return core.EXIT_OK
    opts = Options(mode=args.mode, params=params, lua=args.lua, done_lua=args.done_lua, save=args.save,
                   game_mode=args.game_mode, timeout=args.timeout, menu_timeout=args.menu_timeout,
                   quit_timeout=args.quit_timeout, wait_idle=args.wait_idle, start_delay=args.start_delay,
                   lua_timeout=args.lua_timeout, keep_cache=args.keep_cache, no_quit=args.no_quit,
                   screenshot=not args.no_screenshot, bridge=args.bridge, clients=args.clients,
                   client_run=args.client_run, out=args.out, dry_run=args.dry_run,
                   server_debug=args.server_debug)
    return Runner(project, opts, env).run()


if __name__ == '__main__':
    sys.exit(main())
