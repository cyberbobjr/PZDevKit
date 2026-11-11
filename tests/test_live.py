"""Command-line side of the live channel (cli/pzdev/live.py) against a simulated game that answers in out.txt."""

from __future__ import annotations

import io
import json
import os
import re
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import live  # noqa: E402


class FakeGame(threading.Thread):
    """Polls <root>/Lua/pzdev/cmd.lua like Live.lua and answers; `reply(id, code)` gives the answer body."""

    def __init__(self, root: Path, reply, delay=0.0, shot=True):
        super().__init__(daemon=True)
        self.root, self.reply, self.delay, self.shot = root, reply, delay, shot
        self.stop = threading.Event()
        self.seen = []

    def run(self):
        cmd = self.root / 'Lua' / 'pzdev' / 'cmd.lua'
        last = None
        while not self.stop.is_set():
            time.sleep(0.02)
            try:
                text = cmd.read_text(encoding='utf-8')
            except OSError:
                continue
            m = re.match(r'--pzdev 1 id=(\d+)(.*)\n', text)
            if not m or m.group(1) == last:
                continue
            last = m.group(1)
            self.seen.append(text)
            time.sleep(self.delay)
            body = self.reply(last, text.split('\n', 1)[1])
            lines = [f'--pzdev 1 id={last} {body[0]} durationMs=0'] + body[1:]
            if ' shot' in m.group(2) and self.shot:
                shots = self.root / 'Screenshots'
                shots.mkdir(exist_ok=True)
                (shots / f'pzdev_{last}.png').write_bytes(b'\x89PNG')
                lines.append(f'shot pzdev_{last}.png')
            (self.root / 'Lua' / 'pzdev' / 'out.txt').write_text('\n'.join(lines + ['--end']) + '\n',
                                                                 encoding='utf-8')


class LiveCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'cache'
        (self.root / 'Lua').mkdir(parents=True)
        self.out_dir = Path(self.tmp.name) / 'live'
        self.games = []

    def tearDown(self):
        for g in self.games:
            g.stop.set()
            g.join(2)
        self.tmp.cleanup()

    def game(self, reply, **kw):
        g = FakeGame(self.root, reply, **kw)
        g.start()
        self.games.append(g)
        return g

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = live.main(list(args), out_dir=self.out_dir)
        return code, buf.getvalue()

    def test_value_returned(self):
        self.game(lambda i, code: ['status=ok', '-> 2'])
        code, out = self.run_cli('lua', 'return 1+1', '--target', f'cache:{self.root}')
        self.assertEqual(code, 0, out)
        self.assertIn('-> 2', out)
        self.assertFalse((self.root / 'Lua' / 'pzdev' / 'cmd.lua.tmp').exists())

    def test_lua_error_gives_exit_2_and_the_message(self):
        self.game(lambda i, code: ['status=error', 'error pzdev:1: boom'])
        code, out = self.run_cli('lua', 'error("boom")', '--target', f'cache:{self.root}')
        self.assertEqual(code, 2)
        self.assertIn('boom', out)

    def test_file_argument_and_increasing_ids(self):
        g = self.game(lambda i, code: ['status=ok', '-> ' + code.strip()])
        script = Path(self.tmp.name) / 's.lua'
        script.write_text('return "from file"', encoding='utf-8')
        self.assertEqual(self.run_cli('lua', '-f', str(script), '--target', f'cache:{self.root}')[0], 0)
        self.assertEqual(self.run_cli('lua', 'return 2', '--target', f'cache:{self.root}')[0], 0)
        ids = [int(re.match(r'--pzdev 1 id=(\d+)', t).group(1)) for t in g.seen]
        self.assertEqual(len(ids), 2)
        self.assertLess(ids[0], ids[1])
        self.assertIn('return "from file"', g.seen[0])

    def test_screenshot_is_copied(self):
        self.game(lambda i, code: ['status=ok'])
        code, out = self.run_cli('lua', 'return 1', '--shot', '--target', f'cache:{self.root}')
        self.assertEqual(code, 0, out)
        pics = list(self.out_dir.glob('pzdev_*.png'))
        self.assertEqual(len(pics), 1, out)
        self.assertIn(str(pics[0]), out)

    def test_no_answer_gives_exit_2_with_progress_every_2_s(self):
        code, out = self.run_cli('lua', 'return 1', '--timeout', '3', '--target', f'cache:{self.root}')
        self.assertEqual(code, 2)
        self.assertIn('waiting', out)
        self.assertIn('no answer after 3 s', out)

    def test_partial_answer_is_not_read(self):
        out = self.root / 'Lua' / 'pzdev' / 'out.txt'
        self.assertIsNone(live.read_answer(out, '5'))
        out.parent.mkdir(parents=True)
        out.write_text('--pzdev 1 id=5 status=ok durationMs=0\n-> 1\n', encoding='utf-8')  # no --end yet
        self.assertIsNone(live.read_answer(out, '5'))
        out.write_text('--pzdev 1 id=5 status=ok durationMs=0\n-> 1\n--end\n', encoding='utf-8')
        self.assertEqual(live.read_answer(out, '5')['lines'], ['-> 1'])
        self.assertIsNone(live.read_answer(out, '6'))

    def test_attach_pings(self):
        self.game(lambda i, code: ['status=ok', '-> pong'] if 'pong' in code else ['status=error', 'error x'])
        code, out = self.run_cli('attach', '--target', f'cache:{self.root}')
        self.assertEqual(code, 0, out)
        self.assertIn('attached', out)

    def test_missing_target_folder_is_refused_without_creating_it(self):
        missing = Path(self.tmp.name) / 'gone'
        code, out = self.run_cli('lua', 'return 1', '--target', f'cache:{missing}')
        self.assertEqual(code, 2)
        self.assertIn('no Lua folder', out)
        self.assertFalse(missing.exists())

    def test_attach_without_game_gives_exit_2(self):
        code, out = self.run_cli('attach', '--timeout', '1', '--target', f'cache:{self.root}')
        self.assertEqual(code, 2)
        self.assertIn('-debug', out)

    def test_repl_runs_each_line_until_eof(self):
        self.game(lambda i, code: ['status=ok', '-> ' + code.strip()])
        sys_stdin = sys.stdin
        sys.stdin = io.StringIO('return 1\n\nreturn 2\n')
        try:
            code, out = self.run_cli('repl', '--target', f'cache:{self.root}')
        finally:
            sys.stdin = sys_stdin
        self.assertEqual(code, 0)
        self.assertIn('-> return 1', out)
        self.assertIn('-> return 2', out)


class TargetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_targets(self):
        self.assertEqual(live.resolve_target(f'cache:{self.base}'), self.base / 'Lua')
        user = self.base / 'Zomboid'
        self.assertEqual(live.resolve_target('real', user_dir=user), user / 'Lua')

    def test_default_is_the_last_live_cache_while_it_exists(self):
        pointer = self.base / 'last-live.json'
        cache = self.base / 'pzat-sp-x'
        user = self.base / 'Zomboid'
        self.assertEqual(live.resolve_target(None, pointer=pointer, user_dir=user), user / 'Lua')
        live.remember_cache(cache, pointer=pointer)
        self.assertEqual(json.loads(pointer.read_text(encoding='utf-8'))['cache'], str(cache))
        self.assertEqual(live.resolve_target(None, pointer=pointer, user_dir=user), user / 'Lua')  # gone
        (cache / 'Lua').mkdir(parents=True)
        self.assertEqual(live.resolve_target(None, pointer=pointer, user_dir=user), cache / 'Lua')

    def test_unknown_target_is_refused(self):
        with self.assertRaises(ValueError):
            live.resolve_target('elsewhere')


if __name__ == '__main__':
    unittest.main()
