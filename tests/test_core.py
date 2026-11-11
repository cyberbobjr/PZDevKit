"""Benches of the pure helpers of the pzdev launcher (cli/pzdev/core.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import core  # noqa: E402


class CoreTest(unittest.TestCase):
    def test_active_mod_info_variants(self):
        with tempfile.TemporaryDirectory() as d:
            mod = Path(d)
            for name, mid in (('42', 'a42'), ('42.21', 'a4221'), ('42.30', 'future'), ('common', 'common')):
                (mod / name).mkdir()
                (mod / name / 'mod.info').write_text(f'id={mid}\n')
            self.assertEqual(core.mod_id(mod, (42, 21)), 'a4221')
            self.assertEqual(core.mod_id(mod, (42, 20)), 'a42')
            for name in ('42', '42.21', '42.30'):
                (mod / name / 'mod.info').unlink()
            self.assertEqual(core.mod_id(mod), 'common')

    def test_command_text(self):
        text = core.command_text('abc1', 'sp', params={'suite': 'rs.env', 'exclude': ''}, save='s', control=False,
                                 timeoutSec=None)
        self.assertIn('role=sp\n', text)
        self.assertIn('control=false\n', text)
        self.assertIn('param.exclude=\n', text)
        self.assertNotIn('timeoutSec', text)
        with self.assertRaises(ValueError):
            core.command_text('a-b', 'sp')
        with self.assertRaises(ValueError):
            core.command_text('ab', 'sp', params={'x': 'a\nb'})

    def test_parse_result(self):
        r = core.parse_result('PZAT-RESULT ok=false side=client durationMs=5 error=boom x summary=s y\nL1\nPZAT-END\n')
        self.assertEqual((r['ok'], r['error'], r['summary'], r['lines']), (False, 'boom x', 's y', ['L1']))
        self.assertEqual(core.result_exit_code(r), 2)
        r = core.parse_result('PZAT-RESULT ok=true side=server durationMs=5 summary=\nPZAT-END')
        self.assertEqual(core.result_exit_code(r), 0)
        self.assertFalse(core.result_complete('PZAT-RESULT ok=true side=x durationMs=1 summary=\nhalf'))

    def test_states(self):
        text = 't1 menu a\nt2 load b\nt1 load c d\n'
        self.assertEqual(core.last_state(text, 't1'), ('load', 'c d'))
        self.assertTrue(core.has_state(text, 't2', 'load'))
        self.assertFalse(core.has_state(text, 't2', 'menu'))

    def test_bridge_wanted(self):
        bridge = {'auto': {'suite': ['rs.npctalk'], 'campaign': ['solo-rs']}}
        self.assertTrue(core.bridge_wanted('auto', bridge, {'suite': 'rs.env,rs.npctalk'}))
        self.assertTrue(core.bridge_wanted('auto', bridge, {'suite': 'rs'}))  # prefix selects rs.npctalk
        self.assertTrue(core.bridge_wanted('auto', bridge, {'suite': 'rs.npctalk.world'}))
        self.assertFalse(core.bridge_wanted('auto', bridge, {'suite': 'rs.env'}))
        self.assertTrue(core.bridge_wanted('auto', bridge, {'campaign': 'solo-rs'}))
        self.assertFalse(core.bridge_wanted('auto', bridge, {'campaign': 'solo-lk'}))
        self.assertTrue(core.bridge_wanted('on', bridge, {}))
        self.assertFalse(core.bridge_wanted('off', bridge, {'campaign': 'solo-rs'}))
        self.assertFalse(core.bridge_wanted('on', None, {}))

    def test_redact(self):
        text, n = core.redact('a sk-abcdefghijklmnopqrstuv b OPENAI_KEY=xyz Bearer abcdefghij DEEPSEEK_API_KEY: q '
                              'lit=supersecretvalue token=abc', ['supersecretvalue'])
        self.assertNotIn('sk-abc', text)
        self.assertNotIn('xyz', text)
        self.assertNotIn('supersecretvalue', text)
        self.assertNotIn(': q', text)
        self.assertIn('token=abc', text)  # the run token is not a credential
        self.assertGreaterEqual(n, 5)

    def test_server_ini(self):
        ini = core.server_ini(['A', 'B'], 17000, {'PauseEmpty': False, 'Map': 'X'})
        self.assertIn('Mods=\\A;\\B\n', ini)
        self.assertIn('UDPPort=17001\n', ini)
        self.assertIn('PauseEmpty=false\n', ini)
        self.assertIn('Map=X\n', ini)

    def test_hooks_generation(self):
        h = core.inline_hooks({'start': ['local x = 1', 'return x == 1'], 'done': 'return true'})
        self.assertIn('function H.start(ctx)', h)
        self.assertIn('function H.done(ctx)', h)
        self.assertNotIn('H.result', h)
        self.assertIn('return H', core.code_hooks('print(1)', 'MyMod.done'))

    def test_project_config_files(self):
        """The shipped configurations load (comments stripped) and their hooks exist."""
        root = Path(__file__).resolve().parents[1]
        example = core.load_project(root / 'examples' / 'autotest.example.json')
        self.assertTrue(example.conf['mods'])
        rs = root.parent / 'RadioSurvivor' / 'autotest.json'
        if rs.exists():
            project = core.load_project(rs)
            for mode in core.MODES:
                self.assertIn('RST', core.hooks_text(project, mode))

    def test_pick_save(self):
        with tempfile.TemporaryDirectory() as d:
            saves = Path(d)
            for name in ('rstest-a', 'rstest-b', 'other'):
                (saves / name).mkdir()
                (saves / name / 'map_ver.bin').write_bytes(b'x')
            self.assertIn(core.pick_save(saves, 'rstest*'), ('rstest-a', 'rstest-b'))
            self.assertEqual(core.pick_save(saves, 'other'), 'other')
            self.assertIsNone(core.pick_save(saves, 'missing'))
            self.assertIsNone(core.pick_save(saves, 'zz*'))

    def test_strip_comments(self):
        self.assertEqual(json.loads(core.strip_comments('// c\n{"a": "http://x"}\n  // d')), {'a': 'http://x'})


if __name__ == '__main__':
    unittest.main()
