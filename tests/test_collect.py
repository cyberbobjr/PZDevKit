"""pzdev scenario collect (formerly PZPuppeteer tools/collect_reports.py): file contracts only; no game or Lua
progression is simulated. Cases taken over from PZPuppeteer tests/test_collect_reports.py."""
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cli'))
from pzdev import collect as collector  # noqa: E402

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.user = Path(self.directory.name) / 'user'
        self.archive = Path(self.directory.name) / 'archive'
        self.archive.mkdir()
        self.raw = (b'PZPuppet 0.1.0\nOtherMod/real_action : passed\n'
                    b'Run token: 100-2\nBatch token: 100-1\n'
                    b'Persistent report: PZPuppet/reports/100-2.txt\n'
                    b'Player index: 0\nManual stop: false\n')
        self.metadata = collector.report_metadata(self.raw)
        self.persistent = self.user / 'Lua/PZPuppet/reports/100-2.txt'
        self.persistent.parent.mkdir(parents=True)
        self.persistent.write_bytes(self.raw)
        self.console = ('ERROR: Lua before batch\n[PZPuppet] Batch 100-1 starting | count: 1\n'
                        '[PZPuppet] OtherMod/real_action : passed\n'
                        '[PZPuppet] Batch archive requested: 100-2 | report: PZPuppet/reports/100-2.txt\n')

    def ack(self, console=None):
        return collector.acknowledge(self.metadata, self.raw, console or self.console, self.archive, self.user)

    def test_exact_closed_persistent_report_is_acknowledged(self):
        self.assertTrue(self.ack())
        self.assertEqual((self.user / 'Lua/PZPuppet/batch-ack.txt').read_text(), 'PZPuppet ACK 100-2 passed\n')
        self.assertTrue((self.archive / 'batch-ack.json').is_file())

    def test_partial_or_stale_report_never_acks(self):
        self.persistent.write_bytes(self.raw[:-1])
        self.assertFalse(self.ack())
        self.assertFalse((self.user / 'Lua/PZPuppet/batch-ack.txt').exists())

    def test_missing_archive_request_waits(self):
        self.assertFalse(self.ack(self.console.split('[PZPuppet] Batch archive requested:')[0]))

    def test_missing_batch_baseline_waits(self):
        self.assertFalse(self.ack(self.console.split('starting |')[1]))

    def test_lua_error_after_child_completion_rejects_batch(self):
        self.assertTrue(self.ack(self.console + 'ERROR: General at KahluaThread.flushErrorMessage\n'))
        self.assertIn('rejected new Lua error', (self.user / 'Lua/PZPuppet/batch-ack.txt').read_text())

    def test_other_mod_errors_between_children_are_included(self):
        self.assertTrue(self.ack(self.console.replace('count: 1', 'count: 2\nERROR: Lua other mod')))
        self.assertIn('rejected', (self.user / 'Lua/PZPuppet/batch-ack.txt').read_text())

    def test_native_tile_warning_is_not_a_lua_exception(self):
        self.assertTrue(self.ack(self.console + 'ERROR: General CellLoader> missing tile vegetation\n'))
        self.assertIn('passed', (self.user / 'Lua/PZPuppet/batch-ack.txt').read_text())

    def test_bad_persistent_path_is_rejected(self):
        self.metadata['fields']['Persistent report'] = '../personal-save.txt'
        with self.assertRaises(ValueError):
            self.ack()

    def test_options_are_runtime_metadata(self):
        self.assertEqual(self.metadata['fields']['Manual stop'], 'false')
        self.assertEqual(self.metadata['name'], 'OtherMod/real_action')

    def run_cli(self, raw, console):
        (self.user / 'Lua/PZPuppet/last-report.txt').write_bytes(raw)
        self.persistent.write_bytes(raw)
        (self.user / 'console.txt').write_text(console, encoding='utf-8')
        output = self.archive / 'runs'
        subprocess.run([sys.executable, str(ROOT / 'pzdev.py'), 'scenario', 'collect', '--user', str(self.user),
                        '--output', str(output), '--seconds', '0.7'], check=True, capture_output=True, timeout=5)
        return output

    def test_cli_archives_passed_child_then_acks(self):
        console = self.console.replace('[PZPuppet] OtherMod/',
                      '[PZPuppet] Run token: 100-2 | batch: 100-1 | index: 1 | path: OtherMod/test.lua\n[PZPuppet] OtherMod/')
        output = self.run_cli(self.raw, console)
        archives = list(output.iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / 'puppeteer.txt').read_bytes(), self.raw)
        self.assertTrue((archives[0] / 'batch-ack.json').exists())

    def test_cli_archives_failed_child_without_an_ack_request(self):
        raw = self.raw.replace(b': passed', b': failed')
        console = ('[PZPuppet] Batch 100-1 starting | count: 1\n'
                   '[PZPuppet] Run token: 100-2 | batch: 100-1 | index: 1 | path: OtherMod/test.lua\n'
                   '[PZPuppet] OtherMod/real_action : failed | Assertion failed\n')
        output = self.run_cli(raw, console)
        archives = list(output.iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads((archives[0] / 'result.json').read_text())['engine_status'], 'failed')
        self.assertFalse((self.user / 'Lua/PZPuppet/batch-ack.txt').exists())

if __name__ == '__main__':
    unittest.main()
