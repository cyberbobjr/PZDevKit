"""pzdev film (formerly PZDirector tools/tournage.py) against a simulated game."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import film, scenario  # noqa: E402


class FakeGame:
    def __init__(self, root: Path, final='passed', version='0.4.0', shots=('serre', 'large')):
        self.root, self.final, self.version, self.shots = root, final, version, shots
        self.sent, self.polls = [], 0

    def __call__(self, lua_dir, code, shot=False, timeout=30.0, out_dir=None, say=print):
        self.sent.append(code)
        if 'Production.VERSION' in code:
            return (0, {'lines': [f'-> {self.version}']}) if self.version else (2, None)
        if 'setShowLuaDebuggerOnError(false)' in code:
            return 0, {'lines': ['-> true', '-> true']}
        if 'S.runFile(' in code:
            return 0, {'lines': ['-> 100-2']}
        if code == scenario.POLL_CODE:
            self.polls += 1
            if self.polls < 3:
                return 0, {'lines': ['-> 100-2', '-> running', '-> REPERE: serre', '-> ']}
            shots = self.root / 'Screenshots'
            shots.mkdir(exist_ok=True)
            for name in self.shots:
                (shots / f'PZDirector_{name}.png').write_bytes(b'\x89PNG')
            return 0, {'lines': ['-> 100-2', f'-> {self.final}', '-> ', '-> ']}
        return 0, {'lines': ['-> true']}


class FilmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'cache'
        (self.root / 'Lua').mkdir(parents=True)
        (self.root / 'Screenshots').mkdir()
        old = self.root / 'Screenshots' / 'PZDirector_old.png'
        old.write_bytes(b'old')
        past = time.time() - 3600
        import os
        os.utime(old, (past, past))
        self.file = Path(self.tmp.name) / 'stills.lua'
        self.file.write_text('return function(params) end\n', encoding='utf-8')
        self.out = Path(self.tmp.name) / 'take'

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, game, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = film.main(list(args) + ['--target', f'cache:{self.root}', '--out', str(self.out)], send=game,
                             sleep=lambda s: None)
        return code, buf.getvalue()

    def test_take_without_video_collects_the_new_screenshots(self):
        game = FakeGame(self.root)
        code, out = self.run_cli(game, str(self.file), '-P', 'close=2')
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / 'Lua' / 'PZPuppet' / 'scenarios' / 'pzdev' / 'stills.lua').is_file())
        self.assertIn('{ close = 2 }', next(c for c in game.sent if 'S.runFile(' in c))
        self.assertEqual(sorted(p.name for p in self.out.glob('*.png')), ['PZDirector_large.png', 'PZDirector_serre.png'])
        take = json.loads((self.out / 'take.json').read_text(encoding='utf-8'))
        self.assertEqual((take['status'], take['exitCode'], take['video']), ('passed', 0, None))
        self.assertEqual(take['screenshots'], ['PZDirector_large.png', 'PZDirector_serre.png'])
        self.assertIn('setShowLuaDebuggerOnError(true)', game.sent[-1])  # the user's setting is restored

    def test_failed_take_gives_exit_1(self):
        code, out = self.run_cli(FakeGame(self.root, final='failed'), str(self.file))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads((self.out / 'take.json').read_text(encoding='utf-8'))['status'], 'failed')

    def test_no_production_engine_in_the_game_gives_exit_2(self):
        game = FakeGame(self.root, version=None)
        code, out = self.run_cli(game, str(self.file))
        self.assertEqual(code, 2)
        self.assertIn('pzdev sp', out)
        self.assertFalse(any('S.runFile(' in c for c in game.sent))

    def test_video_needs_ffmpeg(self):
        game = FakeGame(self.root)
        film.recorder.ffmpeg_available, saved = (lambda: False), film.recorder.ffmpeg_available
        try:
            code, out = self.run_cli(game, str(self.file), '--video')
        finally:
            film.recorder.ffmpeg_available = saved
        self.assertEqual(code, 2)
        self.assertIn('ffmpeg', out)
        self.assertEqual(game.sent, [])

    def test_bad_size_is_refused(self):
        code, out = self.run_cli(FakeGame(self.root), str(self.file), '--video', '--size', 'big')
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
