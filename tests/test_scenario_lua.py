"""Lua cases of the scenario engine and of the productions (tests/lua/test_*.lua, taken over from PZPuppeteer
and PZDirector) in lupa (Lua 5.1) with a
simulated game API: one unittest per Lua function T.<case>, each in a fresh Lua state after T.setup()."""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None

ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / 'Contents' / 'mods' / 'batman_PZDevKit' / '42.21' / 'media' / 'lua'
CASES = Path(__file__).resolve().parent / 'lua'
EXAMPLES = ROOT / 'examples' / 'scenarios'
PRODUCTIONS = ROOT / 'examples' / 'productions'


def runtime():
    vm = lupa.LuaRuntime(unpack_returned_tuples=True)
    g = vm.globals()
    g.readMod = lambda name: (LUA / 'client' / f'{name}.lua').read_text(encoding='utf-8')
    g.readTests = lambda name: (CASES / name).read_text(encoding='utf-8')
    g.readExample = lambda name: (EXAMPLES / name).read_text(encoding='utf-8')
    g.readEngineTest = lambda: (CASES / 'test_engine.lua').read_text(encoding='utf-8')
    vm.execute('''
        local loaded = {}
        function dofileMod(name) return assert(loadstring(readMod(name), name))() end
        function require(name)
            if name:sub(1, 9) ~= "PZDevKit/" then return end
            if not loaded[name] then loaded[name] = dofileMod(name) or true end
            return loaded[name]
        end
        next = nil
    ''')
    return vm


def make_case(file: Path, name: str):
    def case(self):
        vm = runtime()
        suite = vm.execute(file.read_text(encoding='utf-8'))
        suite.setup()
        suite[name]()
    return case


class ScenarioLuaTest(unittest.TestCase):
    pass


if lupa is not None:
    for _file in sorted(CASES.glob('test_*.lua')):
        _suite = runtime().execute(_file.read_text(encoding='utf-8'))
        for _name in sorted(n for n in _suite.keys() if n != 'setup'):
            setattr(ScenarioLuaTest, f'test_{_file.stem[5:]}__{_name}', make_case(_file, _name))


@unittest.skipIf(lupa is None, 'lupa missing')
class ExamplesTest(unittest.TestCase):
    def test_examples_compile(self):
        for file in sorted(list(EXAMPLES.glob('*.lua')) + list(PRODUCTIONS.glob('*.lua'))):
            ok = runtime().eval('function(s) return loadstring(s) ~= nil end')(file.read_text(encoding='utf-8'))
            self.assertTrue(ok, file.name)


if __name__ == '__main__':
    unittest.main()
