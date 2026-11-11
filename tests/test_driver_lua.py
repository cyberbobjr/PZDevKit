"""Bench of the Lua driver of batman_PZDevKit in lupa (Lua 5.1) with doubles of the game: events, files,
main menu, character creation, screenshot, quit. Simulation only: the real load, click and exit are checked by a
real run (README.md). Skipped when lupa is missing.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None

LUA = Path(__file__).resolve().parents[1] / 'Contents' / 'mods' / 'batman_PZDevKit' / '42.21' / 'media' / 'lua'
FILES = [LUA / 'shared' / 'PZDevKit' / 'Driver.lua', LUA / 'client' / 'PZDevKit' / 'DriverClient.lua',
         LUA / 'server' / 'PZDevKit' / 'DriverServer.lua']

FAKES = r"""
next = nil
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
    e.fire = function(...) local copy = {} for i, h in ipairs(e.handlers) do copy[i] = h end
        for _, h in ipairs(copy) do h(...) end end
    return e
end
Events = { OnTickEvenPaused = fakeEvent(), OnFETick = fakeEvent(), OnMainMenuEnter = fakeEvent(),
    OnGameStart = fakeEvent(), OnConnectFailed = fakeEvent(), OnServerStarted = fakeEvent(),
    OnClientCommand = fakeEvent() }
QUITS = 0
getCore = function() return { quitToDesktop = function() QUITS = QUITS + 1 end } end
getWorld = function() return { getWorld = function() return "save-x" end,
    getGameMode = function() return GAMEMODE end } end
UIManager = { setShowLuaDebuggerOnError = function(v) BREAK = v end }
SHOTS = {}
takeScreenshot = function(name) SHOTS[#SHOTS + 1] = name end
LOADS = {}
MainScreen = { continueLatestSave = function(mode, save) LOADS[#LOADS + 1] = mode .. "/" .. save end }
CONNECTS = {}
ConnectToServer = { instance = { connect = function(self, panel, a, user, pw, host, b, port)
    CONNECTS[#CONNECTS + 1] = user .. "@" .. host .. ":" .. port end } }
SERVER = false
isServer = function() return SERVER end
-- World seen by the gates: WORLD.square / WORLD.chunk / WORLD.onlineId (client), ONLINE (server players).
WORLD = { square = true, chunk = true, onlineId = 3 }
local function fakePlayer(name)
    return { name = name, getX = function() return 10.5 end, getY = function() return 20.5 end,
        getZ = function() return 0 end, getOnlineID = function() return WORLD.onlineId end,
        getUsername = function() return name end,
        getCurrentSquare = function()
            if not WORLD.square then return nil end
            return { getChunk = function() return WORLD.chunk and {} or nil end }
        end }
end
getPlayer = function() return fakePlayer("p0") end
getCell = function() return { getChunk = function() return WORLD.chunk and {} or nil end } end
ONLINE = 1
getOnlinePlayers = function() return { size = function() return ONLINE end,
    get = function() return fakePlayer("op") end } end
getFileWriter = function(name, create, append)
    local f = assert(io.open(FILE_ROOT .. "/" .. name, append and "a" or "w"))
    return { writeln = function(self, s) f:write(s .. "\n") end, close = function() f:close() end }
end
getFileReader = function(name)
    local f = io.open(FILE_ROOT .. "/" .. name, "r")
    if not f then return nil end
    return { readLine = function() return f:read("*l") end, close = function() f:close() end }
end
function tick(n, step) for _ = 1, n or 1 do CLOCK = CLOCK + (step or 300); Events.OnTickEvenPaused.fire() end end
function fe(n, step) for _ = 1, n or 1 do CLOCK = CLOCK + (step or 300); Events.OnFETick.fire() end end
"""

HOOKS_OK = """
local H = {}
function H.start(ctx) HOOK_PARAMS = ctx.params; HOOK_SIDE = ctx.side; HOOK_READY = ctx.ready; H.t = 0
    return true end
function H.done(ctx) H.t = H.t + 1; return H.t >= 3 end
function H.result(ctx) return { ok = true, summary = "3 polls", lines = { "PASS x", "line\\nbreak" } } end
return H
"""


@unittest.skipIf(lupa is None, 'lupa missing')
class DriverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'pz-autotest').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        (self.root / 'pz-autotest' / name).write_bytes(text.encode('utf-8'))

    def read(self, name):
        p = self.root / 'pz-autotest' / name
        return p.read_text(encoding='utf-8') if p.exists() else ''

    def new_state(self, server=False):
        """A fresh Lua state (as after a Lua reset) with the driver loaded; the files persist."""
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        lua.globals().FILE_ROOT = str(self.root).replace('\\', '/')
        lua.execute(FAKES)
        lua.globals().SERVER = server
        for f in FILES:
            lua.execute(f.read_text(encoding='utf-8'))
        return lua

    def command(self, **keys):
        lines = ['token=tok1'] + [f'{k}={v}' for k, v in keys.items()]
        self.write('command.txt', '\n'.join(lines) + '\n')

    def test_sp_full_sequence(self):
        self.command(role='sp', save='save-x', startDelaySec='1', readyFrames='1',
                     **{'param.suite': 'rs.env', 'param.exclude': ''})
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(3)')
        self.assertEqual(list(lua.globals().LOADS.values()), [])  # waits for MainScreen.instance
        lua.execute('MainScreen.instance = {}')
        lua.execute('fe(12)')
        self.assertEqual(list(lua.globals().LOADS.values()), ['Sandbox/save-x'])
        self.assertIn('tok1 load Sandbox/save-x', self.read('status.txt'))
        # Lua reset for the save mods: a new state must not load again
        lua = self.new_state()
        lua.execute('MainScreen.instance = {}')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(20)')
        self.assertEqual(len(lua.globals().LOADS), 0)
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(10)')
        result = self.read('result.txt').splitlines()
        self.assertTrue(result[0].startswith('PZAT-RESULT ok=true side=client durationMs='), result)
        self.assertTrue(result[0].endswith('summary=3 polls'))
        self.assertEqual(result[1:], ['PASS x', 'line / break', 'PZAT-END'])
        self.assertEqual(lua.eval('HOOK_PARAMS.suite'), 'rs.env')
        self.assertEqual(lua.eval('HOOK_PARAMS.exclude'), '')
        self.assertEqual(lua.eval('HOOK_SIDE'), 'client')
        lua.execute('tick(10)')
        self.assertEqual(list(lua.globals().SHOTS.values()), ['pz-autotest-tok1.png'])
        self.assertEqual(lua.globals().QUITS, 1)
        self.assertFalse(lua.globals().BREAK)

    def test_save_refused_by_menu(self):
        self.command(role='sp', save='save-x')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('MainScreen.instance = {}')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(12)')
        lua.execute('MainScreen.instance.checkSavefileModal = {}')
        lua.execute('fe(1)')
        self.assertIn('error=the main menu refused the save', self.read('result.txt'))
        self.assertEqual(lua.globals().QUITS, 1)

    def test_save_conversion_warning_is_accepted_once(self):
        """42.22 asks to convert an older world (UI_worldscreen_SavefileConversion): YES on the cache copy."""
        self.command(role='sp', save='save-x')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('getText = function(key) return "text:" .. key end')
        lua.execute('MainScreen.instance = {}')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(12)')
        lua.execute('''CLICKS = {}
            MainScreen.instance.checkSavefileModal = { text = "text:UI_worldscreen_SavefileConversion",
                yes = { internal = "YES" },
                -- the vanilla callback clears checkSavefileModal
                onClick = function(self, b) CLICKS[#CLICKS + 1] = b.internal
                    MainScreen.instance.checkSavefileModal = nil end }''')
        lua.execute('fe(3)')
        self.assertEqual(list(lua.globals().CLICKS.values()), ['YES'])
        self.assertIn('save conversion accepted', self.read('status.txt'))
        self.assertEqual(self.read('result.txt'), '')
        lua.execute('MainScreen.instance.checkSavefileModal = {}')  # any other dialog is still a refusal
        lua.execute('fe(1)')
        self.assertIn('error=the main menu refused the save', self.read('result.txt'))

    def test_start_refused_and_hook_errors(self):
        for hooks, expected in (
                ('return { start = function() return false, "nope" end }', 'error=run not started: nope'),
                ('return { start = function() error("boom") end }', 'error=start hook error:'),
                ('return { start = function() end, done = function() error("bad") end }', 'error=done hook error:'),
                ('return {', 'error=hooks do not compile'),
                ('return { client = {} }', 'error=no start hook for side client')):
            with self.subTest(hooks=hooks):
                self.write('status.txt', '')
                self.write('result.txt', '')
                self.command(role='sp', save='s', startDelaySec='0', screenshot='false', readyFrames='1')
                self.write('status.txt', 'tok1 load x\n')
                self.write('hooks.lua', hooks)
                lua = self.new_state()
                lua.globals().Events.OnGameStart.fire()
                lua.execute('tick(5)')
                self.assertIn(expected, self.read('result.txt'))

    def test_lua_timeout(self):
        self.command(role='sp', save='s', startDelaySec='0', timeoutSec='2', readyFrames='1')
        self.write('status.txt', 'tok1 load x\n')
        self.write('hooks.lua', 'return { start = function() end, done = function() return false end }')
        lua = self.new_state()
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(5)')
        self.assertEqual(self.read('result.txt'), '')
        lua.execute('tick(10)')
        self.assertIn('error=no end after 2 s (timeoutSec)', self.read('result.txt'))

    def test_invalid_command(self):
        self.write('command.txt', 'token=tok1\nrole=boat\n')
        lua = self.new_state()
        lua.globals().Events.OnMainMenuEnter.fire()
        self.assertIn('error=command.txt refused: role must be', self.read('result.txt'))

    def test_server_side_tables(self):
        self.command(role='server', startDelaySec='0')
        self.write('hooks.lua', 'return { client = { start = function() return false, "wrong side" end },'
                                ' server = { start = function(ctx) PLAYERS = #ctx.players() end,'
                                ' result = function() return true, "server ok" end } }')
        lua = self.new_state(server=True)
        lua.globals().Events.OnServerStarted.fire()
        lua.execute('tick(3)')
        self.assertIn('PZAT-RESULT ok=true side=server', self.read('result.txt'))
        self.assertEqual(lua.globals().PLAYERS, 1)
        self.assertEqual(lua.globals().QUITS, 0)  # the launcher stops the server

    def test_server_ignores_client_and_solo(self):
        self.command(role='server', startDelaySec='0')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state(server=False)  # a solo game or MP client also loads media/lua/server
        lua.globals().Events.OnServerStarted.fire()
        lua.execute('tick(5)')
        self.assertEqual(self.read('result.txt'), '')

    def test_mp_client_waits_when_game_mode_is_an_object(self):
        """42.22: getWorld():getGameMode() returns a GameMode object (toString = its id), not a string."""
        self.command(role='mpclient', connect='127.0.0.1:17391', user='pzat1', password='pw', control='true',
                     run='false', startDelaySec='0', readyFrames='1')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('MainScreen.instance = { bottomPanel = {} }')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(12)')
        lua = self.new_state()  # connection reset, still connected, no character creation shown yet
        lua.execute('GAMEMODE = setmetatable({}, { __tostring = function() return "Multiplayer" end })')
        lua.execute('MainScreen.instance = {}')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(80)')  # 24 s > JOIN_MENU_MS
        self.assertNotIn('connection lost', self.read('status.txt'))
        self.assertEqual(self.read('result.txt'), '')

    def test_mp_client_join_control(self):
        self.command(role='mpclient', connect='127.0.0.1:17391', user='pzat1', password='pw', control='true',
                     run='false', startDelaySec='0', readyFrames='1')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('MainScreen.instance = { bottomPanel = {} }')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(12)')
        self.assertEqual(list(lua.globals().CONNECTS.values()), ['pzat1@127.0.0.1:17391'])
        # connection reset: new state, character creation shown
        lua = self.new_state()
        lua.execute('PRESSED = {}')
        lua.execute('''MainScreen.instance = {
            charCreationProfession = { getIsVisible = function() return true end,
                onOptionMouseDown = function(self, b) PRESSED[#PRESSED + 1] = "prof:" .. b.internal end },
            charCreationMain = { onOptionMouseDown = function(self, b) PRESSED[#PRESSED + 1] = "main:" .. b.internal end } }''')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(10)')
        self.assertEqual(list(lua.globals().PRESSED.values()), ['prof:NEXT', 'main:NEXT'])
        self.assertIn('tok1 load character created', self.read('status.txt'))
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(5)')
        self.assertIn('tok1 ready', self.read('status.txt'))
        self.assertNotIn('tok1 idle', self.read('status.txt'))
        self.write('control.txt', 'go\n')
        lua.execute('tick(5, 1100)')
        self.assertIn('tok1 idle', self.read('status.txt'))
        self.assertEqual(lua.globals().QUITS, 0)
        self.write('control.txt', 'go\nquit\n')
        lua.execute('tick(10, 1100)')
        self.assertEqual(lua.globals().QUITS, 1)

    def test_client_world_gate(self):
        self.command(role='sp', save='s', startDelaySec='0', readyFrames='4', readyTimeoutSec='30',
                     screenshot='false')
        self.write('status.txt', 'tok1 load x\n')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('WORLD.square = false')
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(20)')
        self.assertNotIn('tok1 world', self.read('status.txt'))
        self.assertIsNone(lua.eval('HOOK_SIDE'))  # no hook before the world
        lua.execute('WORLD.square = true; WORLD.chunk = false')
        lua.execute('tick(5)')
        self.assertNotIn('tok1 world', self.read('status.txt'))
        lua.execute('WORLD.chunk = true')
        lua.execute('tick(1)')
        self.assertIn('tok1 world ok after', self.read('status.txt'))
        self.assertIn('square 10,20,0, chunk 1,2 loaded (9/9 around)', self.read('status.txt'))
        lua.execute('tick(10)')
        self.assertIn('PZAT-RESULT ok=true', self.read('result.txt'))
        self.assertEqual(lua.eval('HOOK_READY.ok'), True)

    def test_client_world_min_frames_and_timeout(self):
        self.command(role='mpclient', connect='h:1', user='u', startDelaySec='0', readyFrames='5',
                     readyTimeoutSec='2', screenshot='false', quit='false')
        self.write('status.txt', 'tok1 connect x\ntok1 load x\n')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.execute('WORLD.onlineId = -1')
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(4, 100)')
        self.assertNotIn('tok1 world', self.read('status.txt'))
        lua.execute('tick(20, 100)')
        status = self.read('status.txt')
        self.assertIn('tok1 world timeout after 2 s', status)
        self.assertIn('no online id yet', status)
        self.assertTrue(any('WARNING: world not ready' in line for line in lua.globals().LOGS.values()))
        lua.execute('tick(10)')
        self.assertIn('PZAT-RESULT ok=true', self.read('result.txt'))  # the run goes on
        self.assertEqual(lua.eval('HOOK_READY.ok'), False)

    def test_client_world_needs_frames(self):
        self.command(role='sp', save='s', startDelaySec='0', readyFrames='6', screenshot='false')
        self.write('status.txt', 'tok1 load x\n')
        self.write('hooks.lua', HOOKS_OK)
        lua = self.new_state()
        lua.globals().Events.OnGameStart.fire()
        lua.execute('tick(5)')
        self.assertNotIn('tok1 world', self.read('status.txt'))
        lua.execute('tick(1)')
        self.assertIn('tok1 world ok after 1500 ms, 6 ticks', self.read('status.txt'))

    def test_server_players_gate_and_inbox_replay(self):
        self.command(role='server', control='true', startDelaySec='0', players='2', playerWaitSec='30')
        self.write('hooks.lua', """
            return { server = {
                start = function(ctx)
                    GOT = {}
                    Events.OnClientCommand.Add(function(m, c, p, a) GOT[#GOT + 1] = m .. "/" .. c .. "/" .. a.n end)
                    return true
                end,
                done = function() return #GOT >= 3 end } }""")
        lua = self.new_state(server=True)
        lua.execute('ONLINE = 1')
        lua.globals().Events.OnServerStarted.fire()
        lua.execute('tick(3)')
        # a client whose hooks started first: commands before the server hooks
        lua.execute('Events.OnClientCommand.fire("M", "ready", {}, { n = 1 })')
        lua.execute('Events.OnClientCommand.fire("M", "ready", {}, { n = 2 })')
        self.write('control.txt', 'go\n')
        lua.execute('tick(5, 1100)')
        self.assertIn('tok1 go', self.read('status.txt'))
        self.assertNotIn('tok1 run', self.read('status.txt'))  # one player of two
        lua.execute('ONLINE = 2; WORLD.square = false')
        lua.execute('tick(3)')
        self.assertNotIn('tok1 run', self.read('status.txt'))  # square not loaded on the server
        lua.execute('WORLD.square = true')
        lua.execute('tick(1)')
        self.assertIn('tok1 players ok after', self.read('status.txt'))
        self.assertIn('tok1 run started', self.read('status.txt'))
        self.assertEqual(list(lua.eval('GOT').values()), ['M/ready/1', 'M/ready/2'])
        lua.execute('Events.OnClientCommand.fire("M", "live", {}, { n = 3 })')
        self.assertEqual(list(lua.eval('GOT').values()), ['M/ready/1', 'M/ready/2', 'M/live/3'])
        self.assertEqual(len(lua.eval('Events.OnClientCommand.handlers')), 1)  # inbox listener removed
        lua.execute('tick(3)')
        self.assertIn('PZAT-RESULT ok=true side=server', self.read('result.txt'))

    def test_server_players_timeout_goes_on(self):
        self.command(role='server', control='true', startDelaySec='0', players='1', playerWaitSec='2')
        self.write('hooks.lua', 'return { start = function() return true end }')
        lua = self.new_state(server=True)
        lua.execute('ONLINE = 0')
        lua.globals().Events.OnServerStarted.fire()
        self.write('control.txt', 'go\n')
        lua.execute('tick(10, 400)')
        self.assertIn('tok1 players timeout after 2 s', self.read('status.txt'))
        self.assertIn('0/1 player(s) online', self.read('status.txt'))
        self.assertIn('PZAT-RESULT ok=true side=server', self.read('result.txt'))

    def test_connect_failed(self):
        self.command(role='mpclient', connect='h:1', user='u')
        lua = self.new_state()
        lua.execute('MainScreen.instance = {}')
        lua.globals().Events.OnMainMenuEnter.fire()
        lua.execute('fe(12)')
        lua.globals().Events.OnConnectFailed.fire('refused', 'bad password')
        self.assertIn('error=connection refused: refused (bad password)', self.read('result.txt'))


if __name__ == '__main__':
    unittest.main()
