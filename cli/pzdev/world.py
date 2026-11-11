"""pzdev world <action> ...: world helpers (PZDevKit.World, client/PZDevKit/World.lua) through the live channel.

    pos                                   player position
    tp X Y [Z]                            teleport (idle player, outside a vehicle)
    item TYPE [N] [--at X Y Z]            items in the inventory, or on the ground at X Y Z
    zombies X Y Z [N] [--outfit O] [--frozen]
    vehicle TYPE X Y [--dir N|S|E|W] [--skin K] [--key]
    time H                                hour of day 0..23.99
    weather clear|storm|tropical|blizzard [HOURS]
    weather hold [--clouds V] [--wind V]  dry weather held for a shot (values 0..1)
    night V|off                           night darkness held (1 = darkest), off = the game's own
    stat NAME=VALUE ...                   CharacterStat values (e.g. Hunger=0)
    skill PERK LEVEL                      e.g. skill Electricity 5
    flags NAME=on|off ...                 god, ghost, invisible, instantActions, unlimitedCarry
    heal
    clean zombies|bodies [RADIUS]
    speed N | zoom STEPS
    types item|vehicle [TEXT]             script names containing TEXT

Common options: --target cache:<dir>|real, --timeout S, --shot (as pzdev lua). Changes need a solo game started
with -debug. Exit codes as pzdev lua.
"""
from __future__ import annotations

import argparse

from pzdev import live

FLAGS = ('god', 'ghost', 'invisible', 'instantActions', 'unlimitedCarry')


def lua_str(text: str) -> str:
    """A Lua string literal (ASCII only: the game's Lua reads bytes)."""
    if not text.isascii():
        raise ValueError(f'non-ASCII text: {text!r}')
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def pairs(items: list[str], convert) -> str:
    out = []
    for item in items:
        if '=' not in item:
            raise ValueError(f'expected NAME=VALUE, got {item!r}')
        name, value = item.split('=', 1)
        if not name.isidentifier():
            raise ValueError(f'bad name {name!r}')
        out.append(f'{name} = {convert(value)}')
    return '{ ' + ', '.join(out) + ' }'


def on_off(value: str) -> str:
    if value not in ('on', 'off'):
        raise ValueError(f'expected on or off, got {value!r}')
    return 'true' if value == 'on' else 'false'


def code_for(args: argparse.Namespace) -> str:
    """Lua chunk of a world action (returns readable values, never raw Java lists)."""
    W, a = 'local W = PZDevKit.World\n', args.action
    if a == 'pos':
        return W + 'local p = W.position(); return p.x, p.y, p.z'
    if a == 'tp':
        return W + f'W.teleport({num(args.x)}, {num(args.y)}, {num(args.z)}); return "teleported"'
    if a == 'item':
        if args.at:
            x, y, z = args.at
            call = f'W.spawnWorldItem({lua_str(args.type)}, {num(x)}, {num(y)}, {num(z)}, {args.count})'
        else:
            call = f'W.spawnItem({lua_str(args.type)}, {args.count})'
        return W + f'local t = {call}; return #t .. " x " .. {lua_str(args.type)}'
    if a == 'zombies':
        opts = []
        if args.outfit:
            opts.append(f'outfit = {lua_str(args.outfit)}')
        code = W + (f'local t = W.spawnZombies({num(args.x)}, {num(args.y)}, {num(args.z)}, {args.count}, '
                    f'{{ {", ".join(opts)} }})\n')
        if args.frozen:
            code += 'for _, z in ipairs(t) do W.freezeZombie(z, true) end\n'
        return code + 'return #t .. " zombie(s)"'
    if a == 'vehicle':
        opts = [f'direction = {lua_str(args.dir)}'] + ([f'skin = {args.skin}'] if args.skin is not None else [])
        code = W + f'local v = W.spawnVehicle({lua_str(args.type)}, {num(args.x)}, {num(args.y)}, 0, {{ {", ".join(opts)} }})\n'
        if args.key:
            code += 'W.vehicleKey(v)\n'
        return code + f'return {lua_str(args.type)} .. " id " .. tostring(v:getSqlId())'
    if a == 'time':
        return W + f'return "previous " .. W.setTime({num(args.hours)})'
    if a == 'weather':
        if args.kind == 'hold':
            clouds = 'nil' if args.clouds is None else num(args.clouds)
            wind = 'nil' if args.wind is None else num(args.wind)
            return W + f'W.holdWeather({clouds}, {wind}); return "weather held"'
        hours = '' if args.hours is None else f', {num(args.hours)}'
        return W + f'W.weather({lua_str(args.kind)}{hours}); return "weather {args.kind}"'
    if a == 'night':
        value = 'nil' if args.value == 'off' else num(float(args.value))
        return W + f'W.night({value}); return "night {args.value}"'
    if a == 'stat':
        return W + f'return W.setStats({pairs(args.values, lambda v: num(float(v)))})'
    if a == 'skill':
        return W + f'return "previous " .. W.setSkill({lua_str(args.perk)}, {args.level})'
    if a == 'flags':
        for item in args.values:
            if item.split('=', 1)[0] not in FLAGS:
                raise ValueError(f'unknown flag in {item!r} (known: {", ".join(FLAGS)})')
        return W + f'return W.setFlags({pairs(args.values, on_off)})'
    if a == 'heal':
        return W + 'W.heal(); return "healed"'
    if a == 'clean':
        fn = 'clearZombies' if args.what == 'zombies' else 'clearBodies'
        radius = '' if args.radius is None else str(args.radius)
        return W + f'return W.{fn}({radius}) .. " removed"'
    if a == 'speed':
        return W + f'return W.speed({args.n})'
    if a == 'zoom':
        return W + f'W.zoom({args.steps}); return "zoom {args.steps}"'
    if a == 'types':
        fn = 'itemTypes' if args.kind == 'item' else 'vehicleTypes'
        query = '' if args.text is None else lua_str(args.text)
        return W + f'local t = W.{fn}({query}); return #t .. " found", table.concat(t, " ", 1, math.min(#t, 60))'
    raise ValueError(f'unknown action {a!r}')


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='pzdev world', description=__doc__.splitlines()[0])
    p.add_argument('--target')
    p.add_argument('--timeout', type=float, default=30.0)
    p.add_argument('--shot', action='store_true')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('pos')
    s = sub.add_parser('tp'); s.add_argument('x', type=float); s.add_argument('y', type=float)
    s.add_argument('z', type=int, nargs='?', default=0)
    s = sub.add_parser('item'); s.add_argument('type'); s.add_argument('count', type=int, nargs='?', default=1)
    s.add_argument('--at', type=float, nargs=3, metavar=('X', 'Y', 'Z'))
    s = sub.add_parser('zombies')
    for name in ('x', 'y'):
        s.add_argument(name, type=float)
    s.add_argument('z', type=int); s.add_argument('count', type=int, nargs='?', default=1)
    s.add_argument('--outfit'); s.add_argument('--frozen', action='store_true')
    s = sub.add_parser('vehicle'); s.add_argument('type'); s.add_argument('x', type=float); s.add_argument('y', type=float)
    s.add_argument('--dir', choices=('N', 'S', 'E', 'W'), default='N'); s.add_argument('--skin', type=int)
    s.add_argument('--key', action='store_true')
    s = sub.add_parser('time'); s.add_argument('hours', type=float)
    s = sub.add_parser('weather'); s.add_argument('kind', choices=('clear', 'storm', 'tropical', 'blizzard', 'hold'))
    s.add_argument('hours', type=float, nargs='?'); s.add_argument('--clouds', type=float)
    s.add_argument('--wind', type=float)
    s = sub.add_parser('night'); s.add_argument('value')
    s = sub.add_parser('stat'); s.add_argument('values', nargs='+')
    s = sub.add_parser('skill'); s.add_argument('perk'); s.add_argument('level', type=int)
    s = sub.add_parser('flags'); s.add_argument('values', nargs='+')
    sub.add_parser('heal')
    s = sub.add_parser('clean'); s.add_argument('what', choices=('zombies', 'bodies'))
    s.add_argument('radius', type=int, nargs='?')
    s = sub.add_parser('speed'); s.add_argument('n', type=int)
    s = sub.add_parser('zoom'); s.add_argument('steps', type=int)
    s = sub.add_parser('types'); s.add_argument('kind', choices=('item', 'vehicle')); s.add_argument('text', nargs='?')
    return p


def main(argv: list[str] | None = None, out_dir=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code = code_for(args)
        lua_dir = live.resolve_target(args.target)
    except ValueError as e:
        print(f'ERROR: {e}')
        return 2
    return live.send(lua_dir, code, shot=args.shot, timeout=args.timeout, out_dir=out_dir)[0]
