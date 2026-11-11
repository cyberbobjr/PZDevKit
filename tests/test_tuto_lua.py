"""PZDevKit.Tuto (client/PZDevKit/Tuto.lua, formerly pz-tutorial tuto_lib.lua) in lupa (Lua 5.1) with game doubles:
the hooks of a scene as `pzdev record` writes them, driven poll by poll like the test driver does."""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None

CLIENT = Path(__file__).resolve().parents[1] / 'Contents' / 'mods' / 'batman_PZDevKit' / '42.21' / 'media' / 'lua' / 'client'

FAKES = r"""
require = function() end
LOGS = {}
print = function(s) LOGS[#LOGS + 1] = tostring(s) end
CLOCK = 0
getTimestampMs = function() return CLOCK end
local function fakeEvent()
    local e = { handlers = {} }
    e.Add = function(f) e.handlers[#e.handlers + 1] = f end
    e.Remove = function(f) for i, h in ipairs(e.handlers) do if h == f then table.remove(e.handlers, i) return end end end
    return e
end
Events = { OnTick = fakeEvent() }
isDebugEnabled = function() return true end
isClient = function() return false end
isServer = function() return false end
ERRORS = 0
getLuaDebuggerErrorCount = function() return ERRORS end
local function list(t) return { size = function() return #t end, get = function(_, i) return t[i + 1] end } end
LIST = list
QUEUE = {}
PLAYER = { x = 10.5, y = 20.5, z = 0, god = false, isDead = function() return false end,
    getX = function(s) return s.x end, getY = function(s) return s.y end, getZ = function(s) return s.z end,
    setX = function(s, v) s.x = v end, setY = function(s, v) s.y = v end, setZ = function(s, v) s.z = v end,
    setLastX = function() end, setLastY = function() end, setLastZ = function() end,
    setGodMod = function(s, v) s.god = v end, getPlayerNum = function() return 0 end,
    getVehicle = function() return nil end }
getPlayer = function() return PLAYER end
getSpecificPlayer = function(i) if i == 0 then return PLAYER end end
ISTimedActionQueue = { queues = { [PLAYER] = { queue = QUEUE } },
    isPlayerDoingAction = function() return #QUEUE > 0 end }
getSandboxOptions = function() return { getOptionByName = function() return { setValue = function() end } end } end
getPlayerInventory = function() return nil end
getPlayerLoot = function() return nil end
UIManager = { getUI = function() return list({}) end, getSpeedControls = function()
    return { SetCurrentGameSpeed = function(_, n) SPEED = n end } end }
ZOMBIES = {}
getCell = function() return { getZombieList = function() return list(ZOMBIES) end,
    getGridSquare = function() return SQUARE end } end
SQUARE = { getX = function() return 15 end, getY = function() return 20 end, getZ = function() return 0 end,
    getObjects = function() return list(OBJECTS) end,
    transmitRemoveItemFromSquare = function(_, o) for i, x in ipairs(OBJECTS) do if x == o then table.remove(OBJECTS, i) end end end }
OBJECTS = {}
"""

SCENE = r"""
T = PZDevKit.Tuto.new()
T.name = "demo"
T.step{ prep = true, run = function() T.teleport(30.5, 40.5) end }
T.step{ caption = "intro", run = function() T.teleport(31.5, 41.5) end }
T.step{ nocaption = true, wait = 1 }
return T.hooks()
"""


@unittest.skipIf(lupa is None, 'lupa missing')
class TutoTest(unittest.TestCase):
    def setUp(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(FAKES)
        for name in ('World', 'Tuto'):
            self.lua.execute((CLIENT / 'PZDevKit' / f'{name}.lua').read_text(encoding='utf-8'))

    def hooks(self, scene=SCENE, **params):
        self.lua.globals().PARAMS = self.lua.table_from(params)
        H = self.lua.execute(scene)
        ctx = self.lua.eval('{ params = PARAMS }')
        return H, ctx

    def drive(self, H, ctx, polls=40, step_ms=300):
        g = self.lua.globals()
        for _ in range(polls):
            g.CLOCK = g.CLOCK + step_ms
            if H.done(ctx):
                return True
        return False

    def logs(self):
        return list(self.lua.globals().LOGS.values())

    def test_each_run_gets_a_fresh_table(self):
        self.assertTrue(self.lua.eval('PZDevKit.Tuto.new() ~= PZDevKit.Tuto.new()'))
        self.assertTrue(self.lua.eval('#PZDevKit.Tuto.new().steps == 0'))

    def test_prep_then_recorded_steps_with_cut_and_captions(self):
        H, ctx = self.hooks()
        self.assertTrue(H.start(ctx))
        self.assertTrue(self.lua.globals().PLAYER.god)
        self.assertTrue(self.drive(H, ctx))
        logs = self.logs()
        start = logs.index('[PZTUTO] start')
        self.assertLess(logs.index('[PZTUTO] step 1'), start)  # prep step before the recording
        self.assertNotIn('[PZTUTO] cut', logs[:start])          # a prep teleport is not a cut
        self.assertEqual(logs[start + 1:start + 3], ['[PZTUTO] caption intro', '[PZTUTO] cut'])
        self.assertIn('[PZTUTO] uncaption', logs)
        self.assertEqual(logs[-1], '[PZTUTO] end')
        self.assertEqual((self.lua.globals().PLAYER.x, self.lua.globals().PLAYER.y), (31.5, 41.5))  # exact centre
        res = H.result(ctx)
        self.assertTrue(res.ok)
        self.assertIn('PASS no Lua error', list(res.lines.values())[-1])

    def test_failed_preflight_stops_before_the_recording(self):
        scene = SCENE.replace('T.step{ prep = true, run = function() T.teleport(30.5, 40.5) end }',
                              'T.step{ prep = true, run = function() T.require(false, "radio found") end }')
        H, ctx = self.hooks(scene)
        H.start(ctx)
        self.assertTrue(self.drive(H, ctx))
        self.assertNotIn('[PZTUTO] start', self.logs())
        self.assertFalse(H.result(ctx).ok)

    def test_live_waits_for_take_then_waits_again(self):
        H, ctx = self.hooks(live='1')
        H.start(ctx)
        self.assertFalse(self.drive(H, ctx, polls=10))
        self.assertIn('[PZTUTO] live: ready (prep done), waiting for commands', self.logs())
        self.assertNotIn('[PZTUTO] start', self.logs())
        self.assertEqual(self.lua.eval('T.take()'), 'take requested')
        self.assertFalse(self.drive(H, ctx, polls=20))  # the take plays, then the game waits again
        self.assertEqual(self.logs().count('[PZTUTO] start'), 1)
        self.assertEqual(self.logs().count('[PZTUTO] end'), 1)

    def test_world_helpers_delegate_to_world(self):
        self.lua.execute('''T = PZDevKit.Tuto.new(); T.player = PLAYER
            OBJECTS[1] = { name = "crate" }; OBJECTS[2] = { name = "wall" }
            assert(T.clearSquare(SQUARE, function(o) return o.name == "crate" end) == 1)
            assert(T.clearSquare(nil, function() return true end) == 0)
            T.speed(2); assert(SPEED == 2)''')
        self.assertFalse(self.lua.eval('(pcall(T.zoom, 0.5))'))  # World validates the steps

    def test_kept_entries_survive_the_debug_filter(self):
        self.lua.execute('''T = PZDevKit.Tuto.new(); T.player = PLAYER
            ISWorldObjectContextMenu = {}
            REMOVED = {}
            local own = function() end
            T.keepEntry(own)
            MENU = { options = { { name = "Inspect", onSelect = own }, { name = "Inspect", onSelect = function() end },
                { name = "Teleport" }, { name = "Light Switch" }, { name = "Walk to" } },
                removeOptionByName = function(self, n) REMOVED[#REMOVED + 1] = n end,
                closeAll = function() end }
            isoToScreenX = function() return 0 end; isoToScreenY = function() return 0 end
            ISWorldObjectContextMenu.createMenu = function() return MENU end
            T.showMenuPath({ getSquare = function() return SQUARE end }, { "Walk to" })''')
        removed = list(self.lua.globals().REMOVED.values())
        self.assertEqual(sorted(removed), ['Inspect', 'Teleport'])  # the foreign Inspect only

    POSE_FAKES = r'''T = PZDevKit.Tuto.new(); T.player = PLAYER
        PLAYER.vars = {}; PLAYER.events = {}; PLAYER.ground = false; PLAYER.furniture = false; PLAYER.sneak = false
        PLAYER.setVariable = function(s, k, v) s.vars[k] = v end
        PLAYER.getVariableBoolean = function(s, k) return s.vars[k] == true end
        PLAYER.playEmote = function(s, n) s.vars.emote = n; s.vars.EmotePlaying = true end
        PLAYER.reportEvent = function(s, e) s.events[#s.events + 1] = e end
        PLAYER.isSitting = function(s) return s.ground or s.furniture end
        PLAYER.setSneaking = function(s, v) s.sneak = v end
        PLAYER.StopAllActionQueue = function(s) s.stopped = true end
        PLAYER.setAutoWalk = function() end
        ISTimedActionQueue.add = function(a) QUEUE[#QUEUE + 1] = a end
        ISRestAction = { new = function(_, who, bed, anims) return { kind = "rest", bed = bed, anims = anims } end }
        ISPathFindAction = { pathToSitOnFurniture = function(_, who, bed, any)
            local a = { kind = "path", bed = bed, any = any }
            a.setOnComplete = function(self, f, ...) self.done = { f, ... } end
            a.setOnFail = function(self, f) self.fail = f end
            a.addAfter = function(self, x) self.after = x; return x end
            return a end }'''

    def test_emote_plays_a_vanilla_gesture_until_it_ends(self):
        self.lua.execute(self.POSE_FAKES)
        self.lua.execute('T.emote("thumbsup")')
        self.assertEqual(self.lua.eval('PLAYER.vars.emote'), 'thumbsup')
        self.assertFalse(self.lua.eval('T.emoteDone()'))
        self.lua.execute('PLAYER.vars.EmotePlaying = false')  # the game ends the animation
        self.assertTrue(self.lua.eval('T.emoteDone()'))

    def test_emote_hold_stops_a_looping_gesture(self):
        self.lua.execute(self.POSE_FAKES)
        self.lua.execute('T.emote("surrender", 2)')
        self.lua.globals().CLOCK += 1500
        self.assertFalse(self.lua.eval('T.emoteDone()'))
        self.lua.globals().CLOCK += 600
        self.assertTrue(self.lua.eval('T.emoteDone()'))

    def test_emote_rejects_unknown_ids_and_bad_hold(self):
        self.lua.execute(self.POSE_FAKES)
        self.assertFalse(self.lua.eval('(pcall(T.emote, "dance"))'))
        self.assertFalse(self.lua.eval('(pcall(T.emote, "clap", 0))'))
        self.assertFalse(self.lua.eval('(pcall(T.emote, "clap", 61))'))
        self.assertTrue(self.lua.eval('(pcall(T.emote, "wavehi02"))'))  # radial menu variants are valid

    def test_sit_on_ground_then_get_up_the_vanilla_way(self):
        self.lua.execute(self.POSE_FAKES)
        self.lua.execute('T.sit()')
        self.assertEqual(self.lua.eval('PLAYER.events[1]'), 'EventSitOnGround')
        self.lua.execute('PLAYER.ground = true')
        self.assertTrue(self.lua.eval('T.seated()'))
        self.lua.execute('T.getUp()')
        self.assertTrue(self.lua.eval('PLAYER.stopped'))
        self.assertTrue(self.lua.eval('PLAYER.vars.forceGetUp'))

    def test_sit_on_furniture_queues_the_rest_action_after_the_path(self):
        self.lua.execute(self.POSE_FAKES)
        self.lua.execute('CHAIR = { name = "chair" }; T.sitOn(CHAIR)')
        self.assertEqual(self.lua.eval('QUEUE[1].kind'), 'path')
        self.lua.execute('''local a = QUEUE[1]; a.goalFurnitureObject = CHAIR
            a.done[1](a.done[2], a.done[3])''')  # the game found the seat
        self.assertEqual(self.lua.eval('QUEUE[1].after.kind'), 'rest')
        self.assertTrue(self.lua.eval('QUEUE[1].after.anims'))
        self.assertTrue(self.lua.eval('QUEUE[1].after.bed == CHAIR'))

    def test_crouch_toggles_sneaking(self):
        self.lua.execute(self.POSE_FAKES)
        self.lua.execute('T.crouch(true)')
        self.assertTrue(self.lua.eval('PLAYER.sneak'))
        self.lua.execute('T.crouch(false)')
        self.assertFalse(self.lua.eval('PLAYER.sneak'))

    def test_emote_list_has_the_radial_menu_variants(self):
        self.assertTrue(self.lua.eval('PZDevKit.World.EMOTES.saluteformal'))


if __name__ == '__main__':
    unittest.main()
