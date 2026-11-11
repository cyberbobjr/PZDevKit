"""pzdev record (hooks and autotest.json of a tutorial video) and pzdev take / quit (formerly live.py take|quit)."""

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

from pzdev import record  # noqa: E402

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None


class RecordBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / '01-demo'
        self.video.mkdir()
        (self.video / 'video.json').write_text(json.dumps({
            'slug': '01-demo', 'mods': ['SignalSmoke/Contents/mods/batman_SignalSmoke'], 'save': 'base',
            'gameMode': 'Sandbox', 'params': {'who': 'me'}}), encoding='utf-8')
        (self.video / 'scene.lua').write_text('T.step{ caption = "intro", wait = 1 }\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_hooks_take_a_fresh_tuto_table_from_the_mod(self):
        out = record.build(self.video, rehearse=False, extra=['shot=2'])
        hooks = (out / 'hooks.lua').read_text(encoding='utf-8')
        self.assertTrue(hooks.startswith('T = PZDevKit.Tuto.new()\nT.name = "01-demo"\n'))
        self.assertTrue(hooks.endswith('return T.hooks()\n'))
        self.assertIn('T.step{ caption = "intro", wait = 1 }', hooks)
        conf = json.loads((out / 'autotest.json').read_text(encoding='utf-8'))
        self.assertEqual(conf['hooks'], 'hooks.lua')
        self.assertEqual(conf['params'], {'who': 'me', 'shot': '2'})
        self.assertEqual((conf['sp']['save'], conf['sp']['gameMode']), ('base', 'Sandbox'))
        self.assertTrue(conf['mods'][0]['path'].endswith('batman_SignalSmoke'))
        self.assertNotIn('PZDevKit', json.dumps(conf['mods']))  # the launcher adds the driver mod itself

    def test_rehearse_and_live_parameters(self):
        out = record.build(self.video, rehearse=True, extra=[], live=True)
        conf = json.loads((out / 'autotest.json').read_text(encoding='utf-8'))
        self.assertEqual((conf['params']['shots'], conf['params']['dry'], conf['params']['live']), ('1', '1', '1'))
        self.assertEqual(conf['sp']['timeoutSec'], 14400)

    def test_non_ascii_scene_is_refused(self):
        (self.video / 'scene.lua').write_text('T.info("café")\n', encoding='utf-8')
        with self.assertRaises(SystemExit):
            record.build(self.video, rehearse=False, extra=[])

    @unittest.skipIf(lupa is None, 'lupa missing')
    def test_hooks_compile_in_lua(self):
        out = record.build(self.video, rehearse=False, extra=[])
        vm = lupa.LuaRuntime()
        ok = vm.eval('function(s) return loadstring(s) ~= nil end')((out / 'hooks.lua').read_text(encoding='utf-8'))
        self.assertTrue(ok)


class TakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.video = Path(self.tmp.name) / '01-demo'
        self.build = self.video / 'build'
        self.build.mkdir(parents=True)
        self.cache = Path(self.tmp.name) / 'pzat-sp-x'
        (self.cache / 'Lua').mkdir(parents=True)
        (self.build / 'run.log').write_text(f'12:00:00 PZAT_CACHE={self.cache}\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_take(self, fails=(), answer=True, timeout=5):
        sent = []
        timeline = self.build / 'timeline.json'

        def send(lua_dir, code, **kw):
            sent.append((lua_dir, code))
            if not answer:
                return 2, None
            if 'T.take()' in code:
                time.sleep(0.05)
                timeline.write_text(json.dumps({'end': 12.5, 'cuts': [3.0], 'fails': list(fails),
                                                'captions': [{'id': 'intro', 't': 0.4}]}), encoding='utf-8')
            return 0, {'lines': ['-> take requested']}
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = record.take(self.video, send=send, timeout=timeout, sleep=lambda s: time.sleep(0.01))
        return code, buf.getvalue(), sent

    def test_take_targets_the_cache_of_the_recording_and_waits_for_the_timeline(self):
        code, out, sent = self.run_take()
        self.assertEqual(code, 0, out)
        self.assertEqual(sent[0][0], self.cache / 'Lua')
        self.assertIn('take done: 12.5 s, cuts [3.0], captions [\'intro\']', out)
        self.assertIn('no FAIL', out)

    def test_rejected_take_gives_exit_1(self):
        code, out, _ = self.run_take(fails=['step 3 ran - boom'])
        self.assertEqual(code, 1)
        self.assertIn('FAILS: step 3 ran - boom', out)

    def test_no_answer_gives_exit_2(self):
        code, out, _ = self.run_take(answer=False)
        self.assertEqual(code, 2)

    def test_quit_sends_quit_to_desktop(self):
        sent = []
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = record.quit_game(self.video, send=lambda d, c, **kw: sent.append(c) or (0, {'lines': []}))
        self.assertEqual(code, 0)
        self.assertIn('quitToDesktop', sent[0])


if __name__ == '__main__':
    unittest.main()
