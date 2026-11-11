"""Simulated game for the pz-autotest benches: plays the part of the driver (status, result, control files).

    python fake_game.py client|server -cachedir=<cache>

Scenario from the command parameter "scenario": ok (default), fail, hang (no result), crash (exit without result),
error (result with error=). A client in state "load" waits for <cache>/clicked.flag (the posted click).
Gates as the driver: client "world" (param world=late: 1.5 s; world=timeout: "world timeout ..."), server "players"
after "go" when players= is set. Param clientstart=late: client 1 writes "run" 3 s after "go". Times of the first
"run" (client) and of "go" (server) go to <cache>/run.time and <cache>/go.time for the order checks.
"""
import os
import sys
import threading
import time
from pathlib import Path


def main():
    kind = sys.argv[1]
    cache = Path(next(a.split('=', 1)[1] for a in sys.argv if a.startswith('-cachedir=')))
    lua = cache / 'Lua' / 'pz-autotest'
    cmd = {}
    params = {}
    for line in (lua / 'command.txt').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            if k.startswith('param.'):
                params[k[6:]] = v
            else:
                cmd[k] = v
    token, scenario = cmd['token'], params.get('scenario', 'ok')
    run = cmd.get('run', 'true') == 'true'

    def status(state, detail=''):
        with open(lua / 'status.txt', 'a', encoding='utf-8') as f:
            f.write(f'{token} {state} {detail}\n')

    def control(word):
        p = lua / 'control.txt'
        return p.exists() and word in p.read_text(encoding='utf-8').split()

    def result():
        if scenario == 'hang':
            while True:
                time.sleep(1)
        if scenario == 'crash':
            sys.exit(5)
        ok = 'true' if scenario == 'ok' else 'false'
        err = ' error=start hook error: boom' if scenario == 'error' else ''
        text = (f'PZAT-RESULT ok={ok} side={kind} durationMs=12{err} summary=fake {scenario} '
                f'secret sk-ABCDEFGHIJKLMNOPQRSTUV\nPASS a :: b\nFAIL c :: d broken\nPZAT-END\n')
        (lua / 'result.txt').write_text(text, encoding='utf-8')
        status('done', text.splitlines()[0])

    def stamp(name):
        (cache / name).write_text(repr(time.time()), encoding='utf-8')

    if kind == 'server':
        quit_event = threading.Event()

        def reader():
            for line in sys.stdin:
                if line.strip() == 'quit':
                    quit_event.set()
                    return
        threading.Thread(target=reader, daemon=True).start()
        print('*** SERVER STARTED ***', flush=True)
        print('server is listening on port 1', flush=True)
        status('started', 'server started')
        if cmd.get('control') == 'true':
            while not control('go'):
                time.sleep(0.05)
            stamp('go.time')
        if int(cmd.get('players', '0')) > 0:
            status('players', 'ok after 1 ms, 1 ticks: fake')
        if run:
            status('run', 'started')
            result()
        quit_event.wait(30)
        sys.exit(0)

    (cache / 'console.txt').write_text('fake console\n', encoding='utf-8')
    status('menu', 'main menu reached')
    if cmd['role'] == 'mpclient':
        status('connect', cmd['connect'])
    status('load', 'loading')
    while not (cache / 'clicked.flag').exists():
        time.sleep(0.05)
    status('ingame', 'world')
    world = params.get('world', 'ok')
    if world == 'late':
        time.sleep(1.5)
    if world == 'timeout':
        status('world', 'timeout after 1 s, 3 ticks: player square nil at 1,2,0')
    else:
        status('world', 'ok after 5 ms, 10 ticks: fake')
    if cmd.get('control') == 'true':
        status('ready', 'waiting for go')
        while not control('go'):
            time.sleep(0.05)
    if run:
        if params.get('clientstart') == 'late':
            time.sleep(3)
        stamp('run.time')
        status('run', 'started')
        result()
    else:
        status('idle', 'nothing to run')
    if cmd.get('control') == 'true':
        while not control('quit'):
            time.sleep(0.05)
    shots = cache / 'Screenshots'
    shots.mkdir(exist_ok=True)
    (shots / f'pz-autotest-{token}.png').write_bytes(b'\x89PNG fake')
    status('quit', 'quitToDesktop')
    os._exit(0)


if __name__ == '__main__':
    main()
