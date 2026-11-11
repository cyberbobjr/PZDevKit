"""Benches of the pzdev launcher with a simulated game (fake_game.py): sp, server, mp, timeouts, busy machine, redaction.

    python -m unittest discover -s PZDevKit/tests
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / 'cli'))

from pzdev import core  # noqa: E402
from pzdev.launcher import Env, Options, Runner  # noqa: E402

FAKE = Path(__file__).resolve().parent / 'fake_game.py'


class Sandbox:
    """Temporary game, Zomboid, Workshop and project folders."""

    def __init__(self, conf_extra=None):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.game, self.zomboid, self.workshop = root / 'game', root / 'Zomboid', root / 'workshop'
        self.project = root / 'MyMod'
        self.game.mkdir()
        save = self.zomboid / 'Saves' / 'Sandbox' / 'test-save'
        save.mkdir(parents=True)
        (save / 'map_ver.bin').write_bytes(b'x')
        (save / 'mods.txt').write_text('old', encoding='utf-8')
        (self.zomboid / 'options.ini').write_text('fullScreen=true\nlanguage=FR\n', encoding='utf-8')
        mod = self.project / 'Contents' / 'mods' / 'MyMod' / '42'
        mod.mkdir(parents=True)
        (mod / 'mod.info').write_text('name=My Mod\nid=MyMod\n', encoding='utf-8')
        wmod = self.workshop / '123' / 'mods' / 'Lib' / 'common'
        wmod.mkdir(parents=True)
        (wmod / 'mod.info').write_text('name=Lib\nid=LibMod\n', encoding='utf-8')
        conf = {'name': 'MyMod', 'mods': [{'workshop': '123', 'id': 'LibMod'}, {'path': 'Contents/mods/MyMod'}],
                'lua': {'start': 'return true'}, 'sp': {'save': 'test*'}, 'collect': ['mymod/*.txt'],
                'server': {'serverName': 'pzat_test'}}
        conf.update(conf_extra or {})
        (self.project / 'autotest.json').write_text('// comment line\n' + json.dumps(conf), encoding='utf-8')
        self.caches = []

    def env(self, busy=()):
        sandbox = self

        def click(hwnd):
            for cache in sandbox.caches:
                (cache / 'clicked.flag').write_text('1')
        return Env(game=self.game, zomboid=self.zomboid, workshop=self.workshop, busy=lambda: list(busy),
                   find_window=lambda pid: pid, click=click, free_memory_mb=lambda: 0,
                   client_command=lambda env, cache, xmx: [sys.executable, str(FAKE), 'client', f'-cachedir={cache}'],
                   server_command=lambda env, cache, *a: [sys.executable, str(FAKE), 'server', f'-cachedir={cache}'],
                   poll=0.05, click_every=0.1, idle_poll=0.05,
                   live_pointer=Path(self.tmp.name) / 'last-live.json')

    def run(self, mode, scenario='ok', busy=(), extra=None, **opts):
        project = core.load_project(self.project)
        out = Path(self.tmp.name) / 'out'
        o = Options(mode=mode, params={'scenario': scenario, **(extra or {})}, out=out, quit_timeout=10, **opts)
        runner = Runner(project, o, self.env(busy))
        self.caches = runner.caches
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = runner.run()
        self.log = buf.getvalue()
        return code, out, runner

    def close(self):
        for cache in self.caches:
            shutil.rmtree(cache, ignore_errors=True)
        self.tmp.cleanup()


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def test_sp_ok(self):
        code, out, runner = self.sb.run('sp', timeout=30)
        self.assertEqual(code, 0, self.sb.log)
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['exitCode'], 0)
        proc = summary['processes'][0]
        self.assertTrue(proc['result']['ok'])
        self.assertGreaterEqual(proc['clicks'], 1)
        self.assertTrue((out / 'console.txt').exists())
        self.assertTrue(any(p.suffix == '.png' for p in out.iterdir()))
        # stored result redacted, original save untouched, cache removed on success
        self.assertNotIn('sk-ABCDEFGHIJ', (out / 'result.txt').read_text(encoding='utf-8'))
        self.assertGreater(summary['redactedStrings'], 0)
        self.assertEqual((self.sb.zomboid / 'Saves' / 'Sandbox' / 'test-save' / 'mods.txt').read_text(), 'old')
        self.assertFalse(runner.caches[0].exists())
        self.assertIn('FAIL c :: d broken', (out / 'summary.txt').read_text(encoding='utf-8'))

    def test_sp_cache_layout(self):
        code, out, runner = self.sb.run('sp', dry_run=True, keep_cache=True)
        self.assertEqual(code, 0, self.sb.log)
        cache = runner.caches[0]
        self.assertEqual(sorted(p.name for p in (cache / 'mods').iterdir()),
                         ['LibMod', 'MyMod', 'batman_PZDevKit', 'default.txt', 'reset-mods-42_00.txt'])
        mods = (cache / 'Saves' / 'Sandbox' / 'test-save' / 'mods.txt').read_text(encoding='utf-8')
        self.assertLess(mods.index('LibMod'), mods.index('MyMod'))
        self.assertIn('batman_PZDevKit', mods)
        options = (cache / 'options.ini').read_text(encoding='utf-8')
        self.assertIn('fullScreen=false', options)
        self.assertIn('language=FR', options)
        command = (cache / 'Lua' / 'pz-autotest' / 'command.txt').read_bytes()
        self.assertFalse(command.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'param.scenario=ok', command)
        self.assertIn(b'role=sp', command)

    def test_sp_no_quit_becomes_the_default_live_target(self):
        code, out, runner = self.sb.run('sp', dry_run=True, keep_cache=True, no_quit=True)
        self.assertEqual(code, 0, self.sb.log)
        pointer = json.loads((Path(self.sb.tmp.name) / 'last-live.json').read_text(encoding='utf-8'))
        self.assertEqual(pointer['cache'], str(runner.caches[0]))

    def test_sp_failed_tests(self):
        code, out, _ = self.sb.run('sp', scenario='fail', timeout=30)
        self.assertEqual(code, 1, self.sb.log)

    def test_sp_error_in_lua(self):
        code, _, runner = self.sb.run('sp', scenario='error', timeout=30)
        self.assertEqual(code, 2, self.sb.log)
        self.assertTrue(runner.caches[0].exists())  # kept on failure

    def test_sp_timeout_kills_own_process(self):
        code, out, _ = self.sb.run('sp', scenario='hang', timeout=3)
        self.assertEqual(code, 2, self.sb.log)
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        self.assertTrue(summary['processes'][0]['killed'])
        self.assertIn('no complete result', summary['reason'])

    def test_sp_crash(self):
        code, out, _ = self.sb.run('sp', scenario='crash', timeout=30)
        self.assertEqual(code, 2, self.sb.log)

    def test_busy_machine(self):
        code, _, _ = self.sb.run('sp', busy=('java.exe (pid 1)',), wait_idle=0)
        self.assertEqual(code, 3)

    def test_server_ok(self):
        code, out, _ = self.sb.run('server', timeout=30)
        self.assertEqual(code, 0, self.sb.log)
        self.assertIn('sent "quit"', self.sb.log)
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['processes'][0]['exitCode'], 0)  # stopped by "quit", not killed
        self.assertFalse(summary['processes'][0]['killed'])

    def test_server_debug_property_is_off_by_default_and_opt_in(self):
        """`-Ddebug` est la **seule** facon de rendre `isDebugEnabled()` vrai sur un serveur dedie :
        l'argument `-debug` du client y est ignore. Un serveur de production n'est pas en debug, donc
        l'option est fausse par defaut ; une suite qui exerce une fonction reservee au debug l'active."""
        from pzdev.launcher import server_java_command

        env, root = self.sb.env(), Path(self.sb.tmp.name)
        plain = server_java_command(env, root, 'w', 'a', 'p', '1m')
        debugged = server_java_command(env, root, 'w', 'a', 'p', '1m', debug=True)
        self.assertNotIn('-Ddebug', plain)
        self.assertIn('-Ddebug', debugged)

        code, _, runner = self.sb.run('server', timeout=30)
        self.assertEqual(code, 0, self.sb.log)
        self.assertFalse(runner.server_debug())
        code, _, runner = self.sb.run('server', timeout=30, server_debug=True)
        self.assertEqual(code, 0, self.sb.log)
        self.assertTrue(runner.server_debug())

    def test_server_fail(self):
        code, _, _ = self.sb.run('server', scenario='fail', timeout=30)
        self.assertEqual(code, 1)

    def test_mp_two_clients(self):
        code, out, _ = self.sb.run('mp', clients=2, client_run=True, timeout=60)
        self.assertEqual(code, 0, self.sb.log)
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        names = [p['name'] for p in summary['processes']]
        self.assertEqual(names, ['server', 'client1', 'client2'])
        self.assertTrue(summary['processes'][0]['result']['ok'])
        self.assertTrue(summary['processes'][1]['result']['ok'])
        self.assertIsNone(summary['processes'][2]['result'])  # idle second player
        self.assertTrue((out / 'client2' / 'status.txt').exists())
        self.assertIn('idle', (out / 'client2' / 'status.txt').read_text(encoding='utf-8'))

    def test_mp_both_clients_execute_hooks_when_enabled(self):
        sb = Sandbox({'mp': {'clientRunAll': True}})
        try:
            code, out, _ = sb.run('mp', clients=2, client_run=True, timeout=60)
            self.assertEqual(code, 0, sb.log)
            summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
            self.assertTrue(summary['processes'][1]['result']['ok'])
            self.assertTrue(summary['processes'][2]['result']['ok'])
        finally:
            sb.close()

    def test_mp_reconnect_keeps_both_connections_results(self):
        sb = Sandbox({'mp': {'reconnectClient1': True}})
        try:
            code, out, _ = sb.run('mp', clients=2, client_run=True, timeout=60)
            self.assertEqual(code, 0, sb.log)
            summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual([p['name'] for p in summary['processes']],
                ['server', 'client1', 'client2', 'client1-reconnected'])
            self.assertTrue(summary['processes'][1]['result']['ok'])
            self.assertTrue(summary['processes'][3]['result']['ok'])
            self.assertIn('first client disconnected cleanly', sb.log)
        finally:
            sb.close()

    def test_mp_server_go_after_client_hooks(self):
        code, out, runner = self.sb.run('mp', clients=2, client_run=True, timeout=60, keep_cache=True,
                                        extra={'world': 'late'})
        self.assertEqual(code, 0, self.sb.log)
        server_cache, client1 = runner.caches[0], runner.caches[1]
        run_at = float((client1 / 'run.time').read_text())
        go_at = float((server_cache / 'go.time').read_text())
        self.assertLess(run_at, go_at)  # client 1 hooks started before the server got "go"
        self.assertIn('players=2', (server_cache / 'Lua' / 'pz-autotest' / 'command.txt').read_text())
        self.assertLess(self.sb.log.index('"go" to the clients'), self.sb.log.index('"go" to the server'))
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['warnings'], [])

    def test_mp_world_timeout_warns(self):
        code, out, _ = self.sb.run('mp', timeout=60, client_run=True, extra={'world': 'timeout'})
        self.assertEqual(code, 0, self.sb.log)
        summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
        self.assertTrue(any('client1: world timeout' in w for w in summary['warnings']), summary['warnings'])
        self.assertIn('warning: client1: world timeout', (out / 'summary.txt').read_text(encoding='utf-8'))

    def test_mp_client_start_late_warns_then_goes(self):
        sb = Sandbox({'mp': {'clientStartTimeoutSec': 1}})
        try:
            code, out, runner = sb.run('mp', timeout=60, client_run=True, keep_cache=True,
                                       extra={'clientstart': 'late'})
            self.assertEqual(code, 0, sb.log)
            summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
            self.assertTrue(any('hooks not started' in w for w in summary['warnings']), summary['warnings'])
            go_at = float((runner.caches[0] / 'go.time').read_text())
            run_at = float((runner.caches[1] / 'run.time').read_text())
            self.assertLess(go_at, run_at)  # the server was not held back for ever
        finally:
            sb.close()

    def test_mp_server_fail(self):
        code, _, _ = self.sb.run('mp', scenario='fail', timeout=60)
        self.assertEqual(code, 1, self.sb.log)


if __name__ == '__main__':
    unittest.main()
