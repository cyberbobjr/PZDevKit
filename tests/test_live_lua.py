"""Bench of the live channel of batman_PZDevKit (client/PZDevKit/Live.lua) in lupa (Lua 5.1) with game doubles:
Lua/pzdev/cmd.lua is read on OnTickEvenPaused, the answer is written to Lua/pzdev/out.txt."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None

LUA = Path(__file__).resolve().parents[1] / 'Contents' / 'mods' / 'batman_PZDevKit' / '42.21' / 'media' / 'lua'
FILES = [LUA / 'shared' / 'PZDevKit' / 'Driver.lua', LUA / 'client' / 'PZDevKit' / 'Live.lua']

FAKES = r"""
CLOCK = 1000
LOGS = {}
print = function(...) local t = {} for i = 1, select("#", ...) do t[#t + 1] = tostring(select(i, ...)) end
    LOGS[#LOGS + 1] = table.concat(t, " ") end
require = function() end
getTimestampMs = function() return CLOCK end
local function fakeEvent()
    local e = { handlers = {} }
    e.Add = function(f) e.handlers[#e.handlers + 1] = f end
    e.Remove = function(f)
        for i, h in ipairs(e.handlers) do if h == f then table.remove(e.handlers, i); return end end
    end
    e.fire = function(...) for _, h in ipairs(e.handlers) do h(...) end end
    return e
end
Events = { OnTickEvenPaused = fakeEvent(), OnFETick = fakeEvent(), OnMainMenuEnter = fakeEvent(),
    OnGameStart = fakeEvent(), OnConnectFailed = fakeEvent() }
DEBUG = true
isDebugEnabled = function() return DEBUG end
SHOW_DEBUGGER = true
UIManager = { setShowLuaDebuggerOnError = function(v) SHOW_DEBUGGER = v end,
    isShowLuaDebuggerOnError = function() return SHOW_DEBUGGER end }
SHOTS = {}
takeScreenshot = function(name) SHOTS[#SHOTS + 1] = name end
getFileWriter = function(name, create, append)
    local f = assert(io.open(FILE_ROOT .. "/" .. name, append and "a" or "w"))
    return { writeln = function(self, s) f:write(s .. "\n") end, write = function(self, s) f:write(s) end,
        close = function() f:close() end }
end
getFileReader = function(name, create)
    local f = io.open(FILE_ROOT .. "/" .. name, "r")
    if not f then return nil end
    return { readLine = function() return f:read("*l") end, close = function() f:close() end }
end
function tick(n, step) for _ = 1, n or 1 do CLOCK = CLOCK + (step or 300); Events.OnTickEvenPaused.fire() end end
"""


@unittest.skipIf(lupa is None, 'lupa missing')
class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'pzdev').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def new_state(self, debug=True):
        """A fresh Lua state (game start or Lua reload) with the mod loaded; the files persist."""
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        lua.globals().FILE_ROOT = str(self.root).replace('\\', '/')
        lua.execute(FAKES)
        lua.globals().DEBUG = debug
        for f in FILES:
            lua.execute(f.read_text(encoding='utf-8'))
        return lua

    def send(self, n, code, extra=''):
        (self.root / 'pzdev' / 'cmd.lua').write_text(f'--pzdev 1 id={n}{extra}\n{code}\n', encoding='utf-8')

    def out(self):
        p = self.root / 'pzdev' / 'out.txt'
        return p.read_text(encoding='utf-8').splitlines() if p.exists() else []

    def test_value_returned(self):
        lua = self.new_state()
        self.send(5, 'return 1 + 1')
        lua.execute('tick(2)')
        out = self.out()
        self.assertTrue(out[0].startswith('--pzdev 1 id=5 status=ok durationMs='), out)
        self.assertEqual(out[1:], ['-> 2', '--end'])

    def test_error_is_reported_and_the_channel_goes_on(self):
        lua = self.new_state()
        self.send(1, 'error("boom")')
        lua.execute('tick(2)')
        out = self.out()
        self.assertIn('status=error', out[0])
        self.assertTrue(any(line.startswith('error ') and 'boom' in line for line in out), out)
        self.assertEqual(out[-1], '--end')
        self.assertTrue(lua.globals().SHOW_DEBUGGER)  # the user's setting is restored
        self.send(2, 'return "still alive"')
        lua.execute('tick(2)')
        self.assertEqual(self.out()[1:], ['-> still alive', '--end'])

    def test_compile_error_is_distinguished(self):
        lua = self.new_state()
        self.send(1, 'return (')
        lua.execute('tick(2)')
        out = self.out()
        self.assertIn('status=compile-error', out[0])
        self.assertTrue(out[1].startswith('error '), out)

    def test_each_id_runs_once_even_after_a_lua_reload(self):
        lua = self.new_state()
        self.send(3, 'COUNT = (COUNT or 0) + 1; return COUNT')
        lua.execute('tick(5)')
        self.assertEqual(lua.globals().COUNT, 1)
        lua = self.new_state()  # Lua reload: the answered id is read back from out.txt
        lua.execute('tick(5)')
        self.assertIsNone(lua.globals().COUNT)
        self.send(4, 'COUNT = (COUNT or 0) + 1; return COUNT')
        lua.execute('tick(2)')
        self.assertEqual(lua.globals().COUNT, 1)

    def test_screenshot_and_info_lines(self):
        lua = self.new_state()
        self.send(7, 'PZDevKit.info("hello", 3); return nil, "x"', ' shot timeoutMs=5000')
        lua.execute('tick(2)')
        self.assertEqual(list(lua.globals().SHOTS.values()), ['pzdev_7.png'])
        self.assertEqual(self.out()[1:], ['-> nil', '-> x', 'info hello 3', 'shot pzdev_7.png', '--end'])

    def test_tables_are_serialized_with_bounds(self):
        lua = self.new_state()
        self.send(1, 'return { b = { c = 2, d = { e = 1 } }, a = 1, [1] = "z" }')
        lua.execute('tick(2)')
        self.assertEqual(self.out()[1], '-> {1="z", a=1, b={c=2, d={...}}}')
        self.send(2, 'return string.rep("x", 9000)')
        lua.execute('tick(2)')
        line = self.out()[1]
        self.assertLessEqual(len(line), 4096 + 3)
        self.assertTrue(line.endswith('...'))

    def test_multiline_values_stay_on_one_line(self):
        lua = self.new_state()
        self.send(1, 'return "a\\nb"')
        lua.execute('tick(2)')
        self.assertEqual(self.out()[1:], ['-> a / b', '--end'])

    def test_inert_without_debug(self):
        lua = self.new_state(debug=False)
        self.send(1, 'RAN = true')
        lua.execute('tick(5)')
        self.assertIsNone(lua.globals().RAN)
        self.assertEqual(self.out(), [])

    def test_unknown_header_is_ignored(self):
        lua = self.new_state()
        (self.root / 'pzdev' / 'cmd.lua').write_text('RAN = true\n', encoding='utf-8')
        lua.execute('tick(5)')
        self.assertIsNone(lua.globals().RAN)


if __name__ == '__main__':
    unittest.main()
