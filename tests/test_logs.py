"""pzdev logs on an anonymised sample of console.txt (tests/data/console-sample.txt)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import logs  # noqa: E402

SAMPLE = Path(__file__).resolve().parent / 'data' / 'console-sample.txt'


class LogsTest(unittest.TestCase):
    def setUp(self):
        self.lines = logs.read_lines(SAMPLE)

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = logs.main(list(args))
        return code, buf.getvalue()

    def test_session_summary(self):
        s = logs.summary(self.lines)
        self.assertEqual(s['start'], '11-11-2026 11:57:02')
        self.assertEqual(s['version'], '42.22.2 3d39148846')
        self.assertEqual(s['mods'], ['batman_SignalSmoke', 'batman_PZDevKit'])  # loaded twice, listed once
        self.assertEqual(s['luaLoads'], 2)
        self.assertEqual((s['luaErrors'], s['otherErrors'], s['warnings']), (1, 2, 1))

    def test_error_blocks_keep_the_message_and_lua_frames_only(self):
        blocks = logs.error_blocks(self.lines, lua_only=True)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], [
            'ERROR: General      f:6590> Lua(Vanilla).=pzdev> Exception thrown',
            '  se.krka.kahlua.vm.KahluaException: deliberate test error at BaseLib.error(BaseLib.java:307).',
            '  Lua(Vanilla).=pzdev(spawnpoints.lua:1)',
            '  Lua((MOD:batman_PZDevKit (DEV-ONLY))).run(Live.lua:105)'])
        self.assertEqual(len(logs.error_blocks(self.lines, lua_only=False)), 3)

    def test_results_and_grep(self):
        self.assertEqual(logs.results(self.lines),
                         ['PZAT-RESULT ok=true side=client durationMs=93605 summary=sp 41 PASS, 0 FAIL'])
        self.assertEqual(logs.grep(self.lines, r'\[PZDevKit\]'),
                         ['LOG  : Lua          f:6600> [PZDevKit] info still running'])

    def test_cli_default_is_a_summary_with_the_tail(self):
        code, out = self.run_cli('--file', str(SAMPLE), '--tail', '2')
        self.assertEqual(code, 0)
        self.assertIn('started 11-11-2026 11:57:02, version 42.22.2 3d39148846', out)
        self.assertIn('mods (2): batman_SignalSmoke, batman_PZDevKit', out)
        self.assertIn('Lua errors: 1', out)
        self.assertIn('summary=sp 41 PASS', out)
        self.assertTrue(out.rstrip().endswith("Adding stage 'STORM' with duration: 1.0%."), out)

    def test_cli_errors_exit_1_when_lua_errors_exist(self):
        code, out = self.run_cli('--file', str(SAMPLE), '--errors')
        self.assertEqual(code, 1)
        self.assertIn('deliberate test error', out)
        self.assertNotIn('AngelCodeFont', out)
        code, out = self.run_cli('--file', str(SAMPLE), '--all-errors')
        self.assertIn('AngelCodeFont', out)

    def test_cli_grep_and_missing_file(self):
        code, out = self.run_cli('--file', str(SAMPLE), '--grep', 'WeatherPeriod')
        self.assertEqual((code, out.count('\n')), (0, 1))
        code, out = self.run_cli('--file', str(SAMPLE.parent / 'missing.txt'))
        self.assertEqual(code, 2)

    def test_target_folder_and_server_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Lua').mkdir()
            (root / 'console.txt').write_text(SAMPLE.read_text(encoding='utf-8'), encoding='utf-8')
            (root / 'server-console.txt').write_text('LOG  : General      f:0> 01-01-2026 00:00:00\n', encoding='utf-8')
            self.assertEqual(logs.log_file(f'cache:{root}', server=False), root / 'console.txt')
            self.assertEqual(logs.log_file(f'cache:{root}', server=True), root / 'server-console.txt')
            code, out = self.run_cli('--target', f'cache:{root}', '--server')
            self.assertIn('started 01-01-2026 00:00:00', out)

    def test_tail_zero_prints_no_line(self):
        code, out = self.run_cli('--file', str(SAMPLE), '--tail', '0')
        self.assertTrue(out.rstrip().endswith('--- last 0 lines'), out)

    def test_long_mod_lists_are_shortened(self):
        self.assertEqual(logs.short_list([f'm{i}' for i in range(30)], 3), 'm0, m1, m2 (+27 more)')
        self.assertEqual(logs.short_list(['a', 'b'], 3), 'a, b')

    def test_long_lines_are_cut(self):
        self.assertEqual(len(logs.cut('x' * 1000)), 300)


if __name__ == '__main__':
    unittest.main()
