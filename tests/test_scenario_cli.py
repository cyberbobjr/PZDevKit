"""pzdev scenario against a simulated game (the live channel replaced by a function)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))

from pzdev import scenario  # noqa: E402


class FakeGame:
    """Answers the start and poll chunks; polls walk through `states` (status, label, reason)."""

    def __init__(self, lua_dir: Path, states, token='100-2'):
        self.lua_dir, self.states, self.token = lua_dir, list(states), token
        self.sent = []

    def __call__(self, lua_dir, code, shot=False, timeout=30.0, out_dir=None, say=print):
        self.sent.append(code)
        if 'S.runFile(' in code or 'S.run(' in code:
            return 0, {'lines': [f'-> {self.token}']}
        if 'S.runBatchFile(' in code:
            return 0, {'lines': ['-> 100-1', '-> running']}
        if code == scenario.POLL_CODE:
            status, label, reason = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            if status != 'running':
                report = self.lua_dir / 'PZPuppet' / 'reports' / f'{self.token}.txt'
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(f'PZPuppet 0.1.0\nAller-retour : {status}\n', encoding='utf-8')
            return 0, {'lines': [f'-> {self.token}', f'-> {status}', f'-> {label}', f'-> {reason}']}
        if 'S.stop(' in code or 'Scenario.stop(' in code:
            return 0, {'lines': ['-> stopped']}
        return 2, None


class ScenarioCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'cache'
        self.lua = self.root / 'Lua'
        self.lua.mkdir(parents=True)
        self.file = Path(self.tmp.name) / '01-aller-retour.lua'
        self.file.write_text('return function(params) end\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, game, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = scenario.main(list(args) + ['--target', f'cache:{self.root}'], send=game,
                                 sleep=lambda s: None)
        return code, buf.getvalue()

    def test_run_file_copies_then_follows_to_the_report(self):
        game = FakeGame(self.lua, [('running', 'Walk 12 20 0', ''), ('running', 'Wait 1s', ''),
                                   ('passed', '', '')])
        code, out = self.run_cli(game, 'run', str(self.file), '-P', 'distance=3', '-P', 'who=Bob')
        self.assertEqual(code, 0, out)
        copied = self.lua / 'PZPuppet' / 'scenarios' / 'pzdev' / '01-aller-retour.lua'
        self.assertTrue(copied.is_file())
        self.assertIn('S.runFile("pzdev/01-aller-retour.lua", nil, { distance = 3, who = "Bob" })', game.sent[0])
        self.assertIn('running 0 s: Walk 12 20 0', out)
        self.assertIn('Wait 1s', out)
        self.assertIn('Aller-retour : passed', out)
        self.assertIn('scenario passed', out)

    def test_failed_scenario_gives_exit_1_with_its_reason(self):
        game = FakeGame(self.lua, [('failed', '', 'Timeout: Walk')])
        code, out = self.run_cli(game, 'run', '--path', 'OperationArtemis/case.lua')
        self.assertEqual(code, 1)
        self.assertIn('S.runFile("OperationArtemis/case.lua"', game.sent[0])
        self.assertIn('scenario failed: Timeout: Walk', out)

    def test_timeout_stops_the_scenario(self):
        game = FakeGame(self.lua, [('running', 'Walk', '')])
        code, out = self.run_cli(game, 'run', '--name', 'MonMod.equipment', '--timeout', '0')
        self.assertEqual(code, 2)
        self.assertIn('S.run("MonMod.equipment"', game.sent[0])
        self.assertTrue(any('stop(' in c for c in game.sent))
        self.assertIn('timeout', out)

    def test_stalled_step_is_stopped_with_the_given_stop_code(self):
        game = FakeGame(self.lua, [('running', 'Walk', '')])
        ticks = iter(range(0, 1000, 10))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = scenario.follow(self.lua, '100-2', timeout=600, send=game, clock=lambda: next(ticks),
                                   sleep=lambda s: None, stall=30, stop_code='PZDevKit.Production.stop("x")')
        self.assertEqual(code, 2)
        self.assertIn('PZDevKit.Production.stop("x")', game.sent[-1])
        self.assertIn('no change for 30 s', buf.getvalue())

    def test_bad_paths_and_params_are_refused_before_sending(self):
        game = FakeGame(self.lua, [('passed', '', '')])
        for args in (['run', '--path', '../save.lua'], ['run', '--path', 'a b.lua'], ['run', '-P', 'x'],
                     ['run'], ['batch']):
            code, out = self.run_cli(game, *args)
            self.assertEqual(code, 2, args)
        self.assertEqual(game.sent, [])

    def test_another_report_ends_following(self):
        game = FakeGame(self.lua, [('running', 'x', '')], token='100-2')
        game_token = game.token

        def other(lua_dir, code, **kw):
            if code == scenario.POLL_CODE:
                return 0, {'lines': ['-> 999-9', '-> running', '-> x', '-> ']}
            return game(lua_dir, code, **kw)
        code, out = self.run_cli(other, 'run', '--path', 'a.lua')
        self.assertEqual(code, 2)
        self.assertIn(game_token, out)

    def test_batch_and_status(self):
        game = FakeGame(self.lua, [('running', 'Equip item', '')])
        code, out = self.run_cli(game, 'batch', '--path', 'MonMod/campaign.lua')
        self.assertEqual(code, 0)
        self.assertIn('S.runBatchFile("MonMod/campaign.lua"', game.sent[0])
        code, out = self.run_cli(game, 'status')
        self.assertEqual((code, out.strip()), (0, 'running 100-2 Equip item'))

    def test_param_literals(self):
        self.assertEqual(scenario.lua_params(['a=1', 'b=1.5', 'c=x"y']), '{ a = 1, b = 1.5, c = "x\\"y" }')


if __name__ == '__main__':
    unittest.main()
