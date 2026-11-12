"""Pure helpers of the pzdev launcher (no process, no game): configuration, mods, command files, results, redaction."""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

GAME = Path(r'D:\SteamLibrary\steamapps\common\ProjectZomboid')
STEAM_WORKSHOP = Path(r'D:\SteamLibrary\steamapps\workshop\content\108600')
ZOMBOID = Path(os.environ.get('USERPROFILE') or str(Path.home())) / 'Zomboid'
PROJECT_DIR = Path(__file__).resolve().parents[2]
DRIVER_DIR = PROJECT_DIR / 'Contents' / 'mods' / 'batman_PZDevKit'
DRIVER_ID = 'batman_PZDevKit'
DEFAULT_GAME_VERSION = '42.22.2'  # game build actually run; picks the 42.x mod.info variant
LUA_DIR = 'pz-autotest'  # under <cachedir>/Lua
RESET_MARKER = 'If this file does not exist, default.txt will be reset to empty (no mods active).'
WINDOW = {'width': '1280', 'height': '720', 'fullScreen': 'false', 'borderless': 'false'}
SECRET_PATTERNS = (r'\b(?:sk|gsk|xai|pk|rk)[-_][A-Za-z0-9_-]{16,}', r'\bAIza[A-Za-z0-9_-]{30,}',
                   r'Bearer\s+[A-Za-z0-9._-]{8,}', r'(?i)\b[A-Z0-9_]*(?:API_?KEY|_KEY|SECRET|ACCESS_TOKEN|AUTH_TOKEN)\s*[=:]\s*\S+',
                   r'(?i)authorization\s*[=:]\s*\S+', r'\bghp_[A-Za-z0-9]{20,}', r'\bxox[bp]-[A-Za-z0-9-]{10,}')
EXIT_OK, EXIT_FAIL, EXIT_ERROR, EXIT_BUSY = 0, 1, 2, 3
MODES = ('sp', 'server', 'mp')


class ConfigError(Exception):
    pass


# ---------------------------------------------------------------- configuration

def strip_comments(text: str) -> str:
    """JSON with full-line // comments (the examples are commented that way)."""
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//'))


@dataclass
class Project:
    root: Path
    conf: dict
    path: Path = field(default=None)

    @property
    def name(self) -> str:
        return self.conf.get('name') or self.root.name

    def section(self, mode: str) -> dict:
        return dict(self.conf.get(mode) or {})


def load_project(path: Path) -> Project:
    """Loads <project>/autotest.json (path = the file or its folder)."""
    path = Path(path)
    if path.is_dir():
        path = path / 'autotest.json'
    if not path.is_file():
        raise ConfigError(f'configuration not found: {path}')
    try:
        conf = json.loads(strip_comments(path.read_text(encoding='utf-8-sig')))
    except json.JSONDecodeError as e:
        raise ConfigError(f'{path}: invalid JSON ({e})') from e
    if not isinstance(conf, dict):
        raise ConfigError(f'{path}: a JSON object is expected')
    if not conf.get('mods'):
        raise ConfigError(f'{path}: "mods" (list) is required')
    if 'hooks' in conf and 'lua' in conf:
        raise ConfigError(f'{path}: "hooks" and "lua" exclude each other')
    return Project(path.parent.resolve(), conf, path)


# ---------------------------------------------------------------- mods

def version_tuple(name: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r'\d+(?:\.\d+)*', name):
        return None
    return tuple(int(x) for x in name.split('.'))


def read_mod_info(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            out.setdefault(k.strip(), v.strip())
    return out


def active_mod_info(folder: Path, game_version: tuple[int, ...] | None = None) -> Path | None:
    """mod.info that the game reads for this mod folder: newest numeric variant <= game version, then common/,
    then the root (old layout)."""
    game_version = game_version or version_tuple(DEFAULT_GAME_VERSION)
    best, best_v = None, None
    if folder.is_dir():
        for child in folder.iterdir():
            v = version_tuple(child.name)
            if v is None or v > game_version or not (child / 'mod.info').is_file():
                continue
            if best_v is None or v > best_v:
                best, best_v = child / 'mod.info', v
    if best:
        return best
    for candidate in (folder / 'common' / 'mod.info', folder / 'mod.info'):
        if candidate.is_file():
            return candidate
    return None


def mod_id(folder: Path, game_version=None) -> str | None:
    info = active_mod_info(folder, game_version)
    return read_mod_info(info).get('id') if info else None


def resolve_mods(project: Project, workshop: Path = STEAM_WORKSHOP, game_version=None) -> list[tuple[str, Path]]:
    """(id, source folder) of every mod of the configuration, in load order, then the driver."""
    out = []
    for i, entry in enumerate(project.conf['mods']):
        if isinstance(entry, str):
            entry = {'path': entry}
        if 'path' in entry:
            src = Path(entry['path'])
            src = src if src.is_absolute() else (project.root / src).resolve()
            if not src.is_dir():
                raise ConfigError(f'mods[{i}]: folder not found: {src}')
            found = mod_id(src, game_version)
            if not found:
                raise ConfigError(f'mods[{i}]: no mod.info with id= in {src}')
            if entry.get('id') and entry['id'] != found:
                raise ConfigError(f'mods[{i}]: id {entry["id"]!r} expected, mod.info says {found!r}')
            out.append((found, src))
        elif 'workshop' in entry:
            wid, want = str(entry['workshop']), entry.get('id')
            base = workshop / wid / 'mods'
            if not base.is_dir():
                raise ConfigError(f'mods[{i}]: Workshop item {wid} not found (not subscribed?): {base}')
            matches = [(mod_id(d, game_version), d) for d in sorted(base.iterdir()) if d.is_dir()]
            matches = [(m, d) for m, d in matches if m and (want is None or m == want)]
            if len(matches) != 1:
                raise ConfigError(f'mods[{i}]: Workshop item {wid}: {len(matches)} mod(s) match id {want!r}; '
                                  'give "id"')
            out.append(matches[0])
        else:
            raise ConfigError(f'mods[{i}]: "path" or "workshop" is required')
    ids = [m for m, _ in out]
    dup = {m for m in ids if ids.count(m) > 1}
    if dup:
        raise ConfigError('mod ids listed twice: ' + ', '.join(sorted(dup)))
    if DRIVER_ID not in ids:
        out.append((DRIVER_ID, DRIVER_DIR))
    return out


def mods_txt(mod_ids: list[str]) -> str:
    """mods.txt / default.txt (ActiveModsFile format)."""
    lines = ['VERSION = 1,', '', 'mods', '{'] + [f'    mod = {m},' for m in mod_ids] + ['}', '', 'maps', '{', '}', '']
    return '\n'.join(lines)


def patch_options(text: str, values: dict[str, str] = WINDOW) -> str:
    out, seen = [], set()
    for line in text.splitlines():
        key = line.split('=', 1)[0]
        if '=' in line and key in values:
            out.append(f'{key}={values[key]}')
            seen.add(key)
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in values.items() if k not in seen]
    return '\n'.join(out) + '\n'


def pick_save(saves: Path, pattern: str) -> str | None:
    """Save folder name: exact name, or the most recent folder matching a glob pattern (e.g. rstest*)."""
    if not any(c in pattern for c in '*?['):
        return pattern if (saves / pattern / 'map_ver.bin').exists() else None
    found = [p for p in saves.iterdir() if p.is_dir() and fnmatch.fnmatch(p.name.lower(), pattern.lower())
             and (p / 'map_ver.bin').exists()] if saves.is_dir() else []
    return max(found, key=lambda p: p.stat().st_mtime).name if found else None


# ---------------------------------------------------------------- command and hooks

_VALUE_OK = re.compile(r'[^\r\n]*')


def command_text(token: str, role: str, *, params: dict[str, str] | None = None, **keys) -> str:
    """pz-autotest/command.txt (format in shared/PZDevKit/Driver.lua). keys: save, gameMode, connect, user, password, control,
    run, startDelaySec, timeoutSec, quit, screenshot, readyTimeoutSec, readyFrames, players, playerWaitSec
    (None = omitted)."""
    if not re.fullmatch(r'[A-Za-z0-9]+', token):
        raise ValueError('token must be alphanumeric')
    if role not in ('sp', 'server', 'mpclient'):
        raise ValueError('bad role ' + role)
    lines = ['# Written by pz-autotest; read by batman_PZDevKit (PZDevKit/Driver.lua).', f'token={token}',
             f'role={role}']
    for key, value in keys.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        value = str(value)
        if '\n' in value or '\r' in value:
            raise ValueError(f'{key}: one line only')
        lines.append(f'{key}={value}')
    for name, value in (params or {}).items():
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise ValueError(f'parameter name {name!r}: letters, digits and "_" only')
        value = str(value)
        if '\n' in value or '\r' in value:
            raise ValueError(f'parameter {name}: one line only')
        lines.append(f'param.{name}={value}')
    return '\n'.join(lines) + '\n'


def parse_params(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items or []:
        if '=' not in item:
            raise ConfigError(f'parameter {item!r}: name=value expected')
        k, v = item.split('=', 1)
        out[k.strip()] = v
    return out


def inline_hooks(lua: dict) -> str:
    """hooks.lua from inline Lua bodies {"start", "done", "result"} (each may be a string or a list of lines);
    P = ctx.params inside each body."""
    def body(key):
        v = lua.get(key)
        return '\n'.join(v) if isinstance(v, list) else v

    if not body('start'):
        raise ConfigError('"lua.start" is required')
    out = ['-- Generated by pz-autotest from inline Lua.', 'local H = {}']
    for key in ('start', 'done', 'result'):
        b = body(key)
        if b:
            out += [f'function H.{key}(ctx)', '    local P = ctx.params', b, 'end']
    out.append('return H')
    return '\n'.join(out) + '\n'


def code_hooks(code: str, done: str | None = None) -> str:
    """hooks.lua of --lua CODE: the code runs at start; what it returns (a table {ok, summary, lines}, or a value)
    is the result unless --done-lua is given, then --done-lua is polled and its true value ends the run."""
    out = ['-- Generated by pz-autotest --lua.', 'local H = {}', 'function H.start(ctx)', '    local P = ctx.params',
           '    H.value = (function() ' + code + '\nend)()', '    return true', 'end']
    if done:
        out += ['function H.done(ctx)', '    local P = ctx.params', '    return (function() return ' + done + '\nend)()',
                'end']
    out += ['function H.result(ctx)', '    local v = H.value', '    if type(v) == "table" then return v end',
            '    return v ~= false, tostring(v)', 'end', 'return H']
    return '\n'.join(out) + '\n'


def hooks_text(project: Project, mode: str, lua_code: str | None = None, done_code: str | None = None) -> str:
    if lua_code:
        return code_hooks(lua_code, done_code)
    sect = project.section(mode)
    hooks = sect.get('hooks') or project.conf.get('hooks')
    lua = sect.get('lua') or project.conf.get('lua')
    if hooks:
        path = Path(hooks)
        path = path if path.is_absolute() else project.root / path
        if not path.is_file():
            raise ConfigError(f'hooks file not found: {path}')
        return path.read_text(encoding='utf-8')
    if lua:
        return inline_hooks(lua)
    raise ConfigError('no "hooks" file nor "lua" bodies in the configuration (or give --lua)')


# ---------------------------------------------------------------- status and result

def last_state(status_text: str, token: str) -> tuple[str | None, str]:
    state, detail = None, ''
    for line in status_text.splitlines():
        parts = line.split(' ', 2)
        if len(parts) >= 2 and parts[0] == token:
            state, detail = parts[1], parts[2] if len(parts) > 2 else ''
    return state, detail


def has_state(status_text: str, token: str, state: str) -> bool:
    return any(line.split(' ', 2)[:2] == [token, state] for line in status_text.splitlines())


GATE_STATES = ('world', 'players')  # readiness gates of the driver (PZDevKit/Driver.lua, "World gate")


def gate_warnings(status_text: str, token: str) -> list[str]:
    """Gate lines of the status file that timed out ("<token> world timeout ..."), as "<state>: <detail>"."""
    out = []
    for line in status_text.splitlines():
        parts = line.split(' ', 2)
        if len(parts) == 3 and parts[0] == token and parts[1] in GATE_STATES and parts[2].startswith('timeout'):
            out.append(f'{parts[1]} {parts[2]}')
    return out


def result_complete(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) >= 2 and lines[0].startswith('PZAT-RESULT ') and lines[-1] == 'PZAT-END'


def parse_result(text: str) -> dict:
    """{'ok', 'side', 'durationMs', 'error', 'summary', 'lines'} of a complete result.txt."""
    lines = [ln for ln in text.splitlines()]
    first = lines[0]
    m = re.match(r'PZAT-RESULT ok=(true|false) side=(\S+) durationMs=(\d+)(?: error=(.*?))? summary=(.*)$', first)
    if not m:
        return {'ok': False, 'side': '?', 'durationMs': 0, 'error': 'unreadable result line: ' + first[:200],
                'summary': '', 'lines': []}
    body = [ln for ln in lines[1:] if ln != 'PZAT-END']
    while body and not body[-1].strip():
        body.pop()
    return {'ok': m.group(1) == 'true', 'side': m.group(2), 'durationMs': int(m.group(3)), 'error': m.group(4),
            'summary': m.group(5), 'lines': body}


def result_exit_code(result: dict | None) -> int:
    if result is None or result.get('error'):
        return EXIT_ERROR
    return EXIT_OK if result['ok'] else EXIT_FAIL


def combine_codes(codes: list[int]) -> int:
    """Worst code wins: 2 (error/timeout) > 1 (tests failed) > 0."""
    return max(codes) if codes else EXIT_ERROR


# ---------------------------------------------------------------- redaction

def redact(text: str, literals: list[str] = ()) -> tuple[str, int]:
    count = 0
    for value in literals:
        if value and len(value) >= 8 and value in text:
            count += text.count(value)
            text = text.replace(value, '[REDACTED]')
    for pattern in SECRET_PATTERNS:
        text, n = re.subn(pattern, '[REDACTED]', text)
        count += n
    return text, count


def secret_literals(conf: dict) -> list[str]:
    """Values of the environment variables named in "redactEnv" (never printed; only hidden from the stored logs)."""
    return [os.environ.get(name, '') for name in conf.get('redactEnv', [])]


# ---------------------------------------------------------------- server

def server_ini(mod_ids: list[str], port: int, extra: dict | None = None) -> str:
    values = {'Public': 'false', 'Open': 'true', 'UPnP': 'false', 'PauseEmpty': 'true', 'DefaultPort': str(port),
              'UDPPort': str(port + 1), 'MaxPlayers': '8', 'Mods': ';'.join('\\' + m for m in mod_ids),
              'WorkshopItems': '', 'Map': 'Muldraugh, KY', 'SaveWorldEveryMinutes': '0'}
    for k, v in (extra or {}).items():
        values[k] = 'true' if v is True else 'false' if v is False else str(v)
    return '\n'.join(f'{k}={v}' for k, v in values.items()) + '\n'


def bridge_wanted(choice: str, bridge: dict | None, params: dict[str, str]) -> bool:
    """--bridge on/offline: yes; off: no; auto: when a parameter value (comma list) is related to a listed value of
    bridge.auto[param] (equal, or one is a dot prefix of the other). bridge.auto[param] = true: any value."""
    if not bridge or choice == 'off':
        return False
    if choice in ('on', 'offline'):
        return True
    rules = bridge.get('auto') or {}
    for name, listed in rules.items():
        value = params.get(name)
        if value is None:
            continue
        if listed is True:
            return True
        for item in (v.strip() for v in value.split(',') if v.strip()):
            for b in listed:
                if item == b or item.startswith(b + '.') or b.startswith(item + '.'):
                    return True
    return False


def expand_args(args: list[str], values: dict[str, str]) -> list[str]:
    return [a.format(**values) for a in args]
