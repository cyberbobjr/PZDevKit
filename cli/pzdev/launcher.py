"""Orchestration of pz-autotest: temporary caches, game/server processes, bridge, monitoring, collection, summary.

Nothing is written to the game folder, to %USERPROFILE%\\Zomboid (options.ini and the save are only read and copied)
nor to the Steam Workshop folder (Workshop mods are only read and copied). Only processes started here are killed.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pzdev import core
from pzdev import live
from pzdev import winproc

IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '*.bak', '*.tmp', '.git', '.env', '*.env')
SERVER_READY = ('server is listening on port', '*** SERVER STARTED')
TEXT_EXT = {'.txt', '.log', '.json', '.jsonl', '.lua', '.ini', '.csv', '.md'}


def log(message: str) -> None:
    print(time.strftime('%H:%M:%S') + ' ' + message, flush=True)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


@dataclass
class Env:
    """Everything that touches the machine; the test benches replace parts of it."""
    game: Path = core.GAME
    zomboid: Path = core.ZOMBOID
    workshop: Path = core.STEAM_WORKSHOP
    python: str = sys.executable
    busy: object = staticmethod(winproc.busy_processes)
    find_window: object = staticmethod(winproc.find_window)
    click: object = staticmethod(winproc.post_click)
    kill: object = staticmethod(winproc.kill_tree)
    free_memory_mb: object = staticmethod(winproc.free_memory_mb)
    client_command: object = None  # (env, cache, xmx|None) -> argv
    server_command: object = None  # (env, cache, name, admin, password, xmx, debug) -> argv
    poll: float = 1.0
    click_every: float = 3.0
    idle_poll: float = 10.0
    live_pointer: Path | None = None  # sp --no-quit: default target of pzdev lua (None: %TEMP%/pzdev)

    def client_argv(self, cache: Path, xmx: str | None = None) -> list[str]:
        return (self.client_command or client_java_command)(self, cache, xmx)

    def server_argv(self, cache: Path, name: str, admin: str, password: str, xmx: str,
                    debug: bool = False) -> list[str]:
        return (self.server_command or server_java_command)(self, cache, name, admin, password, xmx,
                                                            debug)


def client_java_command(env: Env, cache: Path, xmx: str | None = None) -> list[str]:
    """java.exe command of ProjectZomboid64.json (read only), Steam off, test cache, debug, no sound."""
    conf = json.loads((env.game / 'ProjectZomboid64.json').read_text(encoding='utf-8'))
    vm = [a for a in conf.get('vmArgs', []) if not a.startswith('-Dzomboid.steam=')]
    windows = conf.get('windows', {})
    if windows:
        newest = max(windows, key=lambda v: tuple(int(x) for x in v.split('.')))
        vm = list(windows[newest].get('vmArgs', [])) + vm
    if xmx:
        vm = [a for a in vm if not a.startswith('-Xmx')] + [f'-Xmx{xmx}']
    vm += ['-Dzomboid.steam=0', f'-XX:ErrorFile={cache / "java-error.log"}']
    cp = ';'.join(conf.get('classpath', ['.', 'projectzomboid.jar']))
    main = conf.get('mainClass', 'zombie/gameStates/MainScreenState').replace('/', '.')
    # PZAT_SOUND=1 keeps the sound (videos); every other run stays silent.
    sound = [] if os.environ.get('PZAT_SOUND') == '1' else ['-nosound']
    return [str(env.game / 'jre64' / 'bin' / 'java.exe')] + vm + ['-cp', cp, main, f'-cachedir={cache}', '-debug',
                                                                  *sound, '-nosteam']


def server_java_command(env: Env, cache: Path, name: str, admin: str, password: str, xmx: str,
                        debug: bool = False) -> list[str]:
    """Dedicated server (same options as the former RadioSurvivor smoke script), test cache, no Steam.

    `debug` adds the Java property `-Ddebug`. On a dedicated server, that property is the **only** way to
    turn `Core.debug` on: the `-debug` argument that works for a client is ignored by `GameServer`
    A suite that exercises a debug-only feature therefore
    needs `serverDebug: true`, and a suite that proves such a feature is refused must run without it.
    """
    extra = ['-Ddebug'] if debug else []
    return [str(env.game / 'jre64' / 'bin' / 'java.exe'), '-Djava.awt.headless=true', '-Dzomboid.steam=0',
            *extra,
            '--enable-native-access=ALL-UNNAMED', '--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED',
            '-XX:+UseZGC', '-XX:-CreateCoredumpOnCrash', '-XX:-OmitStackTraceInFastThrow', f'-Xmx{xmx}',
            f'-XX:ErrorFile={cache / "java-error.log"}', '-Djava.library.path=./;./natives/win64/;./natives/',
            '-cp', './;projectzomboid.jar', 'zombie.network.GameServer', f'-cachedir={cache}', '-nosteam',
            '-ip', '127.0.0.1', '-servername', name, '-adminusername', admin, '-adminpassword', password,
            '-disablelog=NetworkPacket']


# ---------------------------------------------------------------- caches

def copy_mods(mods: list[tuple[str, Path]], mods_dir: Path) -> None:
    mods_dir.mkdir(parents=True, exist_ok=True)
    for mod_id, src in mods:
        shutil.copytree(src, mods_dir / mod_id, ignore=IGNORE)


def write_lua_files(cache: Path, command: str, hooks: str) -> Path:
    d = cache / 'Lua' / core.LUA_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / 'command.txt').write_bytes(command.encode('utf-8'))  # no BOM: getFileReader keeps it
    (d / 'hooks.lua').write_bytes(hooks.encode('utf-8'))
    return d


def build_client_cache(env: Env, cache: Path, mods, command: str, hooks: str, save: tuple[str, str] | None = None,
                       save_mods: str = 'replace') -> None:
    ids = [m for m, _ in mods]
    copy_mods(mods, cache / 'mods')
    (cache / 'mods' / 'default.txt').write_text(core.mods_txt(ids), encoding='utf-8')
    # Without this marker a new cache folder gets an empty default.txt at startup (no mod at the main menu).
    (cache / 'mods' / 'reset-mods-42_00.txt').write_text(core.RESET_MARKER, encoding='utf-8')
    options = env.zomboid / 'options.ini'
    text = read_text(options) if options.exists() else ''
    # PZAT_OPTIONS="language=EN;width=1920": extra options.ini values for this run (videos, captures).
    extra = dict(core.WINDOW)
    for pair in os.environ.get('PZAT_OPTIONS', '').split(';'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            extra[key.strip()] = value.strip()
    (cache / 'options.ini').write_text(core.patch_options(text, extra), encoding='utf-8')
    if save:
        game_mode, name = save
        src = env.zomboid / 'Saves' / game_mode / name
        dst = cache / 'Saves' / game_mode / name
        shutil.copytree(src, dst)
        if save_mods == 'replace':
            (dst / 'mods.txt').write_text(core.mods_txt(ids), encoding='utf-8')
    write_lua_files(cache, command, hooks)


def build_server_cache(cache: Path, mods, name: str, ini: str, command: str, hooks: str) -> None:
    copy_mods(mods, cache / 'mods')
    (cache / 'Server').mkdir(parents=True, exist_ok=True)
    (cache / 'Server' / f'{name}.ini').write_bytes(ini.encode('utf-8'))
    write_lua_files(cache, command, hooks)


# ---------------------------------------------------------------- processes

@dataclass
class Proc:
    name: str
    kind: str  # client | server
    cache: Path
    token: str
    run: bool = True
    popen: object = None
    stdout: Path = None
    clicks: int = 0
    next_click: float = 0.0
    last_state: str | None = None
    exit_code: int | None = None
    killed: bool = False
    reason: str = ''
    result: dict | None = None
    started_at: float = 0.0
    state_seen: dict = field(default_factory=dict)

    @property
    def lua(self) -> Path:
        return self.cache / 'Lua' / core.LUA_DIR

    def status_text(self) -> str:
        return read_text(self.lua / 'status.txt')

    def state(self) -> tuple[str | None, str]:
        return core.last_state(self.status_text(), self.token)

    def has(self, state: str) -> bool:
        return core.has_state(self.status_text(), self.token, state)

    def read_result(self) -> dict | None:
        text = read_text(self.lua / 'result.txt')
        if core.result_complete(text):
            self.result = core.parse_result(text)
        return self.result

    def alive(self) -> bool:
        return self.popen is not None and self.popen.poll() is None

    def control(self, *words: str) -> None:
        """Writes control.txt atomically (temporary file then rename)."""
        tmp = self.lua / 'control.tmp'
        tmp.write_bytes(('\n'.join(words) + '\n').encode('utf-8'))
        os.replace(tmp, self.lua / 'control.txt')


def start_process(proc: Proc, argv: list[str], cwd: Path, stdin_pipe: bool = False) -> None:
    proc.stdout = proc.cache / f'{proc.kind}-stdout.log'
    with open(proc.stdout, 'wb') as out:
        proc.popen = subprocess.Popen(argv, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT,
                                      stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL)
    proc.started_at = time.monotonic()
    log(f'{proc.name} started (pid {proc.popen.pid})')


def send_console(proc: Proc, line: str) -> bool:
    """One line on the server console (stdin, UTF-8 without BOM)."""
    try:
        proc.popen.stdin.write((line + '\n').encode('utf-8'))
        proc.popen.stdin.flush()
        return True
    except (OSError, ValueError):
        return False


def stop_process(env: Env, proc: Proc, timeout: float) -> None:
    """Waits for the process to end, then kills its tree (only processes started here)."""
    if proc.popen is None:
        return
    try:
        proc.popen.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f'{proc.name} still running {timeout:g} s later: killed')
        env.kill(proc.popen.pid)
        proc.killed = True
        try:
            proc.popen.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    proc.exit_code = proc.popen.returncode
    if proc.popen.stdin:
        try:
            proc.popen.stdin.close()
        except OSError:
            pass


def tick_client(env: Env, proc: Proc) -> str | None:
    """Logs state changes and clicks the loading screen while the last state is "load". Returns the state."""
    state, detail = proc.state()
    if state != proc.last_state:
        log(f'{proc.name} state {state}: {detail}')
        proc.last_state = state
    # On a saved MP character no creation screen is shown and Lua may keep the
    # connection-reset "menu" state. The new process log proves world loading ended.
    saved_mp_loaded = state in ('menu', 'connect') and proc.stdout is not None \
        and 'game loading took' in read_text(proc.stdout)
    if (state == 'load' or saved_mp_loaded) and proc.alive() and time.monotonic() >= proc.next_click:
        hwnd = env.find_window(proc.popen.pid)
        if hwnd:
            env.click(hwnd)
            proc.clicks += 1
        proc.next_click = time.monotonic() + env.click_every
    return state


# ---------------------------------------------------------------- bridge

def start_bridge(env: Env, project: core.Project, choice: str, exchange: Path, out_log: Path):
    conf = project.conf['bridge']
    values = {'python': env.python, 'exchange': str(exchange), 'project': str(project.root)}
    argv = core.expand_args(list(conf['command']), values)
    if choice == 'offline':
        argv += core.expand_args(list(conf.get('offlineArgs', [])), values)
    cwd = project.root / conf.get('cwd', '.')
    exchange.mkdir(parents=True, exist_ok=True)
    # The bridge reads its own configuration (its .env or the environment): this tool never opens it.
    proc_env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    with open(out_log, 'wb') as out:
        p = subprocess.Popen(argv, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env=proc_env)
    ready, timeout = conf.get('ready'), float(conf.get('readyTimeoutSec', 60))
    deadline = time.monotonic() + timeout
    while ready:
        if ready in read_text(out_log):
            break
        if p.poll() is not None:
            return p, f'the bridge exited (code {p.returncode}) before "{ready}"'
        if time.monotonic() >= deadline:
            return p, f'no "{ready}" from the bridge after {timeout:g} s'
        time.sleep(0.25)
    log(f'bridge ready (pid {p.pid}{", offline" if choice == "offline" else ""}), exchange {exchange}')
    return p, ''


def stop_bridge(env: Env, p) -> None:
    if p is None or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        env.kill(p.pid)


# ---------------------------------------------------------------- collection

def copy_text(src: Path, dst: Path, literals: list[str], own: list[str] = ()) -> int:
    """Copies a file; text files are redacted. own = throwaway passwords of this run, hidden but not counted."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in TEXT_EXT:
        text = read_text(src)
        for value in own:
            if value:
                text = text.replace(value, '[RUN-PASSWORD]')
        text, n = core.redact(text, literals)
        dst.write_text(text, encoding='utf-8')
        return n
    shutil.copy2(src, dst)
    return 0


def collect(proc: Proc, out: Path, globs: list[str], literals: list[str], own: list[str] = ()) -> int:
    """Copies the files of a process cache to out/ (text files redacted). Returns the number of redactions."""
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    lua = proc.cache / 'Lua'
    for name in ('status.txt', 'result.txt', 'command.txt'):
        if (proc.lua / name).exists():
            n += copy_text(proc.lua / name, out / name, literals, own)
    fixed = [proc.cache / 'console.txt', proc.cache / 'server-console.txt', proc.stdout,
             proc.cache / 'java-error.log', proc.cache / 'bridge.log']
    for f in fixed:
        if f and f.exists():
            n += copy_text(f, out / f.name, literals, own)
    shots = proc.cache / 'Screenshots'
    if shots.is_dir():
        for f in shots.glob('*.png'):
            shutil.copy2(f, out / f.name)
    for pattern in globs:
        for f in lua.glob(pattern):
            if f.is_file():
                n += copy_text(f, out / 'lua' / f.relative_to(lua), literals, own)
    logs = proc.cache / 'Logs'
    if proc.kind == 'server' and logs.is_dir():
        for f in logs.rglob('*.txt'):
            n += copy_text(f, out / 'Logs' / f.relative_to(logs), literals, own)
    return n


# ---------------------------------------------------------------- run

@dataclass
class Options:
    mode: str
    params: dict
    lua: str | None = None
    done_lua: str | None = None
    save: str | None = None
    game_mode: str | None = None
    timeout: int | None = None
    menu_timeout: int = 300
    quit_timeout: int = 120
    wait_idle: int = 0
    start_delay: int | None = None
    lua_timeout: int = 0
    keep_cache: bool = False
    no_quit: bool = False
    screenshot: bool = True
    bridge: str | None = None
    clients: int | None = None
    client_run: bool | None = None
    out: Path | None = None
    dry_run: bool = False
    #: Serveur dedie lance avec la propriete Java `-Ddebug`. Faux par defaut : un serveur de production
    #: n'est pas en debug, et c'est l'etat sous lequel une fonction reservee au debug doit etre refusee.
    server_debug: bool = False


class Runner:
    def __init__(self, project: core.Project, opts: Options, env: Env | None = None):
        self.project, self.opts, self.env = project, opts, env or Env()
        self.sect = project.section(opts.mode)
        self.token = secrets.token_hex(6)
        self.literals = core.secret_literals(project.conf)
        self.own: list[str] = []  # throwaway passwords of this run (hidden in the stored logs, not counted)
        self.params = dict(project.conf.get('params') or {})
        self.params.update(self.sect.get('params') or {})
        self.params.update(opts.params)
        self.params = {k: str(v) for k, v in self.params.items() if v is not None}
        self.out = opts.out
        self.procs: list[Proc] = []
        self.bridge = None
        self.bridge_log: Path | None = None
        self.caches: list[Path] = []
        self.started = time.monotonic()
        self.reason = ''
        self.warnings: list[str] = []

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)
            log('WARNING: ' + text)

    # ------------------------------------------------ helpers
    def setting(self, key, default=None):
        return self.sect.get(key, self.project.conf.get(key, default))

    def port(self) -> int:
        return int(self.setting('port', 17391 if self.opts.mode == 'mp' else 17381))

    def server_debug(self) -> bool:
        """Le serveur dedie doit-il tourner en mode debug (`-Ddebug`) ?

        Par defaut non : c'est l'etat d'un serveur de production, et c'est donc l'etat sous lequel une
        fonction reservee au debug doit etre **refusee**. L'option de section `serverDebug` (ou
        `--server-debug`) l'active pour une suite qui exerce une telle fonction.
        """
        if getattr(self.opts, 'server_debug', False):
            return True
        return bool(self.setting('serverDebug', False))

    def hooks(self) -> str:
        return core.hooks_text(self.project, self.opts.mode, self.opts.lua, self.opts.done_lua)

    def mods(self):
        gv = core.version_tuple(str(self.project.conf.get('gameVersion', '42.21'))) or (42, 21)
        return core.resolve_mods(self.project, self.env.workshop, gv)

    def new_cache(self, label: str) -> Path:
        cache = Path(tempfile.mkdtemp(prefix=f'pzat-{label}-'))
        self.caches.append(cache)
        return cache

    def wait_idle(self) -> bool:
        deadline = time.monotonic() + self.opts.wait_idle
        announced = False
        while True:
            busy = self.env.busy()
            if not busy:
                return True
            if time.monotonic() >= deadline:
                log('ERROR: game or server already running: ' + ', '.join(busy) + ' (never killed by this tool)')
                return False
            if not announced:
                log('waiting for: ' + ', '.join(busy))
                announced = True
            time.sleep(self.env.idle_poll)

    def bridge_choice(self) -> str:
        return self.opts.bridge or (self.project.conf.get('bridge') or {}).get('default', 'auto')

    def maybe_bridge(self, exchange_root: Path) -> str:
        """Starts the bridge when wanted. Returns an error reason or ''."""
        conf = self.project.conf.get('bridge')
        choice = self.bridge_choice()
        if not core.bridge_wanted(choice, conf, self.params):
            log(f'bridge not started (--bridge {choice})' if conf else 'no bridge configured')
            return ''
        exchange = exchange_root / 'Lua' / conf.get('exchange', '')
        self.bridge_log = exchange_root / 'bridge.log'
        self.bridge, why = start_bridge(self.env, self.project, choice, exchange, self.bridge_log)
        return why

    # ------------------------------------------------ entry
    def run(self) -> int:
        mode = self.opts.mode
        try:
            mods = self.mods()
            hooks = self.hooks()
        except core.ConfigError as e:
            log(f'ERROR: {e}')
            return core.EXIT_ERROR
        if not self.opts.dry_run and not self.wait_idle():
            return core.EXIT_BUSY
        self.started = time.monotonic()  # the wait for an idle machine is not part of the run
        if self.out is None:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            runs = self.project.root / self.project.conf.get('runsDir', 'runs')
            self.out = runs / f'{stamp}-{mode}-{self.token}'
        log(f'project {self.project.name}, mode {mode}, token {self.token}, mods: ' + ', '.join(m for m, _ in mods))
        if self.params:
            log('params: ' + ', '.join(f'{k}={v}' for k, v in self.params.items()))
        code = core.EXIT_ERROR
        try:
            if mode == 'sp':
                code = self.run_sp(mods, hooks)
            elif mode == 'server':
                code = self.run_server(mods, hooks)
            else:
                code = self.run_mp(mods, hooks)
        except core.ConfigError as e:
            self.reason = str(e)
            code = core.EXIT_ERROR
        finally:
            stop_bridge(self.env, self.bridge)
            for p in self.procs:
                if p.alive():
                    self.env.kill(p.popen.pid)
                    p.killed = True
        if self.opts.dry_run:
            for cache in self.caches:
                if self.opts.keep_cache:
                    log(f'dry run: cache kept {cache}')
                else:
                    shutil.rmtree(cache, ignore_errors=True)
            return code
        return self.finish(code)

    def finish(self, code: int) -> int:
        if self.reason:
            log('ERROR: ' + self.reason)
        for p in self.procs:
            for text in core.gate_warnings(p.status_text(), self.token):
                self.warn(f'{p.name}: {text}')
        redacted = 0
        for p in self.procs:
            sub = self.out if len(self.procs) == 1 else self.out / p.name
            redacted += collect(p, sub, self.setting('collect', []), self.literals, self.own)
        if self.bridge_log and self.bridge_log.exists():
            redacted += copy_text(self.bridge_log, self.out / 'bridge.log', self.literals)
        summary = {
            'project': self.project.name, 'mode': self.opts.mode, 'token': self.token, 'exitCode': code,
            'reason': self.reason, 'warnings': self.warnings, 'params': self.params, 'durationSec': int(time.monotonic() - self.started),
            'date': datetime.now().isoformat(timespec='seconds'), 'redactedStrings': redacted,
            'bridge': None if self.bridge is None else {'exitCode': self.bridge.returncode},
            'processes': [{'name': p.name, 'kind': p.kind, 'run': p.run, 'exitCode': p.exit_code, 'killed': p.killed,
                           'clicks': p.clicks, 'lastState': p.last_state, 'reason': p.reason, 'result': p.result}
                          for p in self.procs],
        }
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        (self.out / 'summary.txt').write_text(summary_text(summary), encoding='utf-8')
        if redacted:
            log(f'WARNING: {redacted} credential-shaped string(s) redacted from the stored logs')
        log(f'results in {self.out}')
        keep = code != 0 or self.opts.keep_cache or self.opts.no_quit
        for cache in self.caches:
            if keep:
                log(f'temporary cache kept: {cache}')
            else:
                shutil.rmtree(cache, ignore_errors=True)
        if not keep:
            log('temporary cache(s) removed')
        log(f'PZAT_EXIT={code} ({summary["durationSec"]} s)')
        return code

    # ------------------------------------------------ sp
    def client_command(self, role: str, run: bool, control: bool, **extra) -> str:
        return core.command_text(
            self.token, role, params=self.params, control=control, run=run,
            startDelaySec=self.opts.start_delay if self.opts.start_delay is not None else self.setting('startDelaySec', 5),
            timeoutSec=self.opts.lua_timeout or None, quit=not self.opts.no_quit, screenshot=self.opts.screenshot,
            readyTimeoutSec=self.setting('readyTimeoutSec'), readyFrames=self.setting('readyFrames'), **extra)

    def run_sp(self, mods, hooks) -> int:
        game_mode = self.opts.game_mode or self.setting('gameMode', 'Sandbox')
        pattern = self.opts.save or self.setting('save')
        if not pattern:
            raise core.ConfigError('sp: no save (sp.save in autotest.json or --save); a new game is not supported')
        save = core.pick_save(self.env.zomboid / 'Saves' / game_mode, pattern)
        if not save:
            raise core.ConfigError(f'sp: no save matching {pattern!r} in {self.env.zomboid / "Saves" / game_mode}')
        cache = self.new_cache('sp')
        command = self.client_command('sp', True, False, save=save, gameMode=game_mode)
        build_client_cache(self.env, cache, mods, command, hooks, (game_mode, save), self.setting('saveMods', 'replace'))
        log(f'PZAT_CACHE={cache}')
        if self.opts.no_quit:
            live.remember_cache(cache, self.env.live_pointer)
            log('live channel: python PZDevKit/pzdev.py lua "<code>" targets this game (left open at the end)')
        log(f'save {game_mode}/{save} (copy)')
        argv = self.env.client_argv(cache, self.setting('xmx'))
        if self.opts.dry_run:
            log('dry run, command: ' + subprocess.list2cmdline(argv))
            return core.EXIT_OK
        why = self.maybe_bridge(cache)
        if why:
            self.reason = why + ': game not started'
            return core.EXIT_ERROR
        proc = Proc('client', 'client', cache, self.token)
        self.procs.append(proc)
        start_process(proc, argv, self.env.game)
        timeout = self.opts.timeout or self.setting('timeoutSec', 900)
        return self.watch_single_client(proc, timeout)

    def watch_single_client(self, proc: Proc, timeout: int) -> int:
        quit_deadline, code = None, core.EXIT_ERROR
        while True:
            now = time.monotonic()
            state = tick_client(self.env, proc)
            if self.bridge is not None and self.bridge.poll() is not None and not proc.state_seen.get('bridge'):
                log(f'WARNING: the bridge exited during the run (code {self.bridge.returncode})')
                proc.state_seen['bridge'] = True
            res = proc.read_result()
            if res is not None and quit_deadline is None:
                log(f'result: ok={res["ok"]} ' + (f'error={res["error"]} ' if res['error'] else '') + res['summary'])
                code = core.result_exit_code(res)
                if self.opts.no_quit:
                    proc.popen = None  # left open on purpose
                    return code
                quit_deadline = now + self.opts.quit_timeout
            if not proc.alive():
                proc.exit_code = proc.popen.returncode
                log(f'{proc.name} exited (code {proc.exit_code}) after {int(now - proc.started_at)} s, '
                    f'{proc.clicks} click(s)')
                if quit_deadline is None:
                    self.reason = proc.reason = 'the game stopped without a complete result.txt'
                    return core.EXIT_ERROR
                return code
            if quit_deadline is not None and now >= quit_deadline:
                self.reason = proc.reason = f'game still running {self.opts.quit_timeout} s after the result: killed'
                self.env.kill(proc.popen.pid)
                proc.killed = True
                stop_process(self.env, proc, 30)
                return max(code, core.EXIT_ERROR) if code == 0 else code
            if state is None and now - proc.started_at >= self.opts.menu_timeout:
                self.reason = proc.reason = (f'no status from the driver after {self.opts.menu_timeout} s '
                                             '(mods not loaded at the menu?): killed')
                self.env.kill(proc.popen.pid)
                proc.killed = True
                stop_process(self.env, proc, 30)
                return core.EXIT_ERROR
            if quit_deadline is None and now - proc.started_at >= timeout:
                self.reason = proc.reason = f'no complete result after {timeout} s (last state {state}): killed'
                self.env.kill(proc.popen.pid)
                proc.killed = True
                stop_process(self.env, proc, 30)
                return core.EXIT_ERROR
            time.sleep(self.env.poll)

    # ------------------------------------------------ server
    def server_setup(self, mods, hooks, control: bool, run: bool,
                     players: int = 0) -> tuple[Proc, list[str], str, str]:
        name = self.setting('serverName', 'pzat_server')
        port = self.port()
        ini_extra = dict(self.project.section('server').get('ini') or {})
        if self.opts.mode == 'mp':
            ini_extra.update(self.sect.get('ini') or {})
        if self.opts.mode == 'mp' and self.setting('spawn'):
            ini_extra.setdefault('SpawnPoint', self.setting('spawn'))
        ini = core.server_ini([m for m, _ in mods], port, ini_extra)
        cache = self.new_cache('server')
        command = core.command_text(self.token, 'server', params=self.params, control=control, run=run,
                                    startDelaySec=self.opts.start_delay if self.opts.start_delay is not None
                                    else self.setting('startDelaySec', 2),
                                    timeoutSec=self.opts.lua_timeout or None, players=players or None,
                                    playerWaitSec=self.setting('playerWaitSec') if players else None)
        build_server_cache(cache, mods, name, ini, command, hooks)
        admin, password = 'pzat_admin', secrets.token_hex(8)
        self.own.append(password)
        argv = self.env.server_argv(cache, name, admin, password,
                                    self.project.section('server').get('xmx', '3072m'),
                                    debug=self.server_debug())
        proc = Proc('server', 'server', cache, self.token, run=run)
        log(f'PZAT_SERVER_CACHE={cache} (server {name}, port {port})')
        return proc, argv, password, name

    def run_server(self, mods, hooks) -> int:
        proc, argv, admin_password, _name = self.server_setup(mods, hooks, control=False, run=True)
        if self.opts.dry_run:
            log('dry run, command: ' + subprocess.list2cmdline(argv).replace(admin_password, '***'))
            return core.EXIT_OK
        why = self.maybe_bridge(proc.cache)
        if why:
            self.reason = why + ': server not started'
            return core.EXIT_ERROR
        self.procs.append(proc)
        start_process(proc, argv, self.env.game, stdin_pipe=True)
        timeout = self.opts.timeout or self.setting('timeoutSec', 600)
        code = core.EXIT_ERROR
        while True:
            now = time.monotonic()
            state, detail = proc.state()
            if state != proc.last_state:
                log(f'server state {state}: {detail}')
                proc.last_state = state
            res = proc.read_result()
            if res is not None:
                log(f'result: ok={res["ok"]} ' + (f'error={res["error"]} ' if res['error'] else '') + res['summary'])
                code = core.result_exit_code(res)
                break
            if not proc.alive():
                self.reason = proc.reason = f'the server stopped without a complete result.txt (code {proc.popen.returncode})'
                break
            if now - proc.started_at >= timeout:
                self.reason = proc.reason = f'no complete result after {timeout} s (last state {state})'
                break
            time.sleep(self.env.poll)
        self.quit_server(proc)
        if proc.killed and code == 0:
            code = core.EXIT_ERROR
        return code

    def quit_server(self, proc: Proc) -> None:
        if proc.alive():
            if send_console(proc, 'quit'):
                log('sent "quit" to the server console')
        stop_process(self.env, proc, self.opts.quit_timeout)
        if not proc.killed:
            log(f'server stopped (code {proc.exit_code})')

    # ------------------------------------------------ mp
    def run_mp(self, mods, hooks) -> int:
        clients = self.opts.clients or int(self.setting('clients', 1))
        client_run = self.opts.client_run if self.opts.client_run is not None else bool(self.setting('clientRun', False))
        server_run = bool(self.setting('serverRun', True))
        port = self.port()
        server, sargv, admin_password, _name = self.server_setup(mods, hooks, control=True, run=server_run,
                                                                 players=clients)
        users = [f'pzat{i}' for i in range(1, clients + 1)]
        password = secrets.token_hex(6)
        self.own.append(password)
        client_procs = []
        for i, user in enumerate(users, 1):
            cache = self.new_cache(f'client{i}')
            run_client = client_run and (i == 1 or bool(self.setting('clientRunAll', False)))
            command = self.client_command('mpclient', run_client, True, connect=f'127.0.0.1:{port}',
                                          user=user, password=password)
            build_client_cache(self.env, cache, mods, command, hooks)
            client_procs.append(Proc(f'client{i}', 'client', cache, self.token, run=run_client))
        cxmx = self.setting('clientXmx', '4096m')
        if self.opts.dry_run:
            log('dry run, server: ' + subprocess.list2cmdline(sargv).replace(admin_password, '***'))
            log('dry run, client: ' + subprocess.list2cmdline(self.env.client_argv(client_procs[0].cache, cxmx)))
            return core.EXIT_OK
        need = clients * int(re.sub(r'\D', '', cxmx) or 0) * (1024 if cxmx.lower().endswith('g') else 1)
        free = self.env.free_memory_mb()
        if free and need > free:
            log(f'WARNING: {free} MB free for {clients} client(s) of -Xmx{cxmx} (+ server): lower mp.clientXmx')
        why = self.maybe_bridge(server.cache)
        if why:
            self.reason = why + ': server not started'
            return core.EXIT_ERROR
        self.procs.append(server)
        start_process(server, sargv, self.env.game, stdin_pipe=True)
        deadline = time.monotonic() + int(self.setting('serverTimeoutSec', 300))
        while not (server.has('started') or any(m in read_text(server.stdout) for m in SERVER_READY)):
            if not server.alive():
                self.reason = 'the server stopped before listening'
                return core.EXIT_ERROR
            if time.monotonic() >= deadline:
                self.reason = 'the server is not listening after serverTimeoutSec'
                self.quit_server(server)
                return core.EXIT_ERROR
            time.sleep(self.env.poll)
        log('server listening')
        for user in users:
            # A client started with -debug is disconnected unless its role has ConnectWithDebug (admin).
            send_console(server, f'adduser {user} {password}')
            send_console(server, f'setaccesslevel {user} admin')
        time.sleep(2)
        join_timeout = int(self.setting('joinTimeoutSec', 600))
        for proc in client_procs:
            self.procs.append(proc)
            start_process(proc, self.env.client_argv(proc.cache, cxmx), self.env.game)
            while True:
                state = tick_client(self.env, proc)
                if proc.has('ingame'):  # next client once this one is in game (world gate awaited below)
                    break
                if state == 'error' or not proc.alive() or time.monotonic() - proc.started_at >= join_timeout:
                    self.reason = proc.reason = f'{proc.name} did not reach the game (last state {state})'
                    return self.mp_abort(server, client_procs)
                time.sleep(self.env.poll)
        # Every client in game. "go" to the server only once each client is in the world (driver world gate:
        # player, online id, square and chunk) and its start hook ran, so its subscribers exist.
        delay = self.opts.start_delay if self.opts.start_delay is not None else self.setting('startDelaySec', 5)
        ready_wait = int(self.setting('clientReadyTimeoutSec',
                                      int(self.setting('readyTimeoutSec', 60)) + int(delay) + 30))
        late = self.wait_clients(client_procs, ('ready',), ready_wait)
        if late is None:
            return self.mp_abort(server, client_procs)
        if late:
            self.warn(', '.join(p.name for p in late) + f' not ready in the world after {ready_wait} s '
                      '(clientReadyTimeoutSec): "go" given anyway')
        for p in client_procs:
            for text in core.gate_warnings(p.status_text(), self.token):
                self.warn(f'{p.name}: {text}')
        log('every client ready in the world: "go" to the clients')
        for p in client_procs:
            p.control('go')
        start_wait = int(self.setting('clientStartTimeoutSec', 60))
        late = self.wait_clients(client_procs, ('run', 'idle', 'done'), start_wait)
        if late is None:
            return self.mp_abort(server, client_procs)
        if late:
            self.warn(', '.join(p.name for p in late) + f' hooks not started after {start_wait} s '
                      '(clientStartTimeoutSec): "go" given to the server anyway')
        log('client hooks started: "go" to the server')
        server.control('go')
        timeout = self.opts.timeout or int(self.setting('timeoutSec', 1800))
        start = time.monotonic()
        waiting = [p for p in [server] + client_procs if p.run]
        reconnected = False
        while waiting:
            for p in list(waiting):
                if p.kind == 'client':
                    tick_client(self.env, p)
                if p.read_result() is not None:
                    r = p.result
                    log(f'{p.name} result: ok={r["ok"]} ' + (f'error={r["error"]} ' if r['error'] else '') + r['summary'])
                    waiting.remove(p)
                    if (p is client_procs[0] and not reconnected and r['ok']
                            and self.setting('reconnectClient1', False)):
                        # A new process and cache provide a real disconnect/reconnect. Retain the
                        # first connection's cache and result intact as separate evidence.
                        p.control('go', 'quit')
                        stop_process(self.env, p, self.opts.quit_timeout)
                        if p.killed:
                            p.reason = 'first connection did not exit cleanly before reconnect'
                            continue
                        cache = self.new_cache('client1-reconnect')
                        shutil.copytree(p.cache, cache, dirs_exist_ok=True, ignore=IGNORE)
                        lua = cache / 'Lua' / core.LUA_DIR
                        for name in ('result.txt', 'status.txt', 'control.txt'):
                            (lua / name).unlink(missing_ok=True)
                        command = self.client_command('mpclient', True, False,
                            connect=f'127.0.0.1:{port}', user=users[0], password=password)
                        (lua / 'command.txt').write_text(command + 'param.reconnect=1\n', encoding='utf-8')
                        reconnect = Proc('client1-reconnected', 'client', cache, self.token, run=True)
                        self.procs.append(reconnect)
                        client_procs[0] = reconnect
                        waiting.append(reconnect)
                        reconnected = True
                        log('first client disconnected cleanly; starting its second connection')
                        start_process(reconnect, self.env.client_argv(cache, cxmx), self.env.game)
                elif not p.alive():
                    p.reason = f'{p.name} stopped without a result'
                    waiting.remove(p)
            if time.monotonic() - start >= timeout:
                for p in waiting:
                    p.reason = f'no result after {timeout} s'
                break
            time.sleep(self.env.poll)
        for p in client_procs:
            p.control('go', 'quit')
        for p in client_procs:
            stop_process(self.env, p, self.opts.quit_timeout)
        self.quit_server(server)
        codes = [core.result_exit_code(p.result) if p.run else core.EXIT_OK for p in [server] + client_procs]
        if not any(p.run for p in [server] + client_procs):
            codes.append(core.EXIT_OK)
        reasons = [f'{p.name}: {p.reason}' for p in [server] + client_procs if p.reason]
        self.reason = '; '.join(reasons)
        return core.combine_codes(codes)

    def wait_clients(self, procs: list[Proc], states: tuple[str, ...], timeout: int) -> list[Proc] | None:
        """Waits until each client status holds one of the states. Returns the late clients ([] = all there), or
        None after a driver error or a stopped client (self.reason set)."""
        deadline = time.monotonic() + timeout
        while True:
            waiting = []
            for p in procs:
                state = tick_client(self.env, p)
                if any(p.has(s) for s in states):
                    continue
                if state == 'error' or not p.alive():
                    self.reason = p.reason = f'{p.name} stopped or failed before {"/".join(states)} (last state {state})'
                    return None
                waiting.append(p)
            if not waiting:
                return []
            if time.monotonic() >= deadline:
                return waiting
            time.sleep(self.env.poll)

    def mp_abort(self, server: Proc, clients: list[Proc]) -> int:
        for p in clients:
            if p.alive():
                self.env.kill(p.popen.pid)
                p.killed = True
                stop_process(self.env, p, 30)
        self.quit_server(server)
        return core.EXIT_ERROR


def summary_text(s: dict) -> str:
    lines = [f'pz-autotest {s["project"]} mode={s["mode"]} exit={s["exitCode"]} ({s["durationSec"]} s) '
             f'token={s["token"]} {s["date"]}']
    if s['params']:
        lines.append('params: ' + ', '.join(f'{k}={v}' for k, v in s['params'].items()))
    if s['reason']:
        lines.append('reason: ' + s['reason'])
    for w in s.get('warnings') or []:
        lines.append('warning: ' + w)
    for p in s['processes']:
        r = p['result']
        head = f'[{p["name"]}] run={p["run"]} exit={p["exitCode"]} killed={p["killed"]} lastState={p["lastState"]}'
        lines.append(head)
        if r:
            lines.append(f'    ok={r["ok"]} durationMs={r["durationMs"]}' + (f' error={r["error"]}' if r['error'] else '')
                         + f' summary={r["summary"]}')
            bad = [ln for ln in r['lines'] if re.match(r'\s*(FAIL|ERROR|EMPTY)\b', ln)]
            lines += ['    ' + ln for ln in bad[:40]]
    if s['redactedStrings']:
        lines.append(f'redacted strings: {s["redactedStrings"]}')
    return '\n'.join(lines) + '\n'
