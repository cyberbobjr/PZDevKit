"""Bench of PZDevKit.World (client/PZDevKit/World.lua) in lupa (Lua 5.1) with game doubles. Cases taken over from
PZPuppeteer tests/test_debug.lua and new cases for the helpers merged from pz-tutorial tuto_lib.lua."""

from __future__ import annotations

import unittest
from pathlib import Path

try:
    import lupa.lua51 as lupa
except ImportError:  # pragma: no cover
    lupa = None

WORLD = (Path(__file__).resolve().parents[1] / 'Contents' / 'mods' / 'batman_PZDevKit' / '42.21' / 'media' / 'lua'
         / 'client' / 'PZDevKit' / 'World.lua')

FAKES = r"""
local function list(values)
    return { size = function() return #values end, get = function(_, i) return values[i + 1] end }
end
LIST = list
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
Events = { OnTick = fakeEvent() }
DEBUG, CLIENT, SERVER, LOADED, FREE, WATER, OCCUPIED = true, false, false, true, true, false, false
SPAWNS, REMOVED, ADDED, PERK_LEVEL, TIME = 0, 0, 0, 0, 12
isDebugEnabled = function() return DEBUG end
isClient = function() return CLIENT end
isServer = function() return SERVER end
instanceof = function(o, kind) return type(o) == "table" and o.kind == kind end
IsoDirections = { N = 1, S = 2, E = 3, W = 4 }
IsoFlagType = { water = "water" }
ItemTag = { GENERATOR = "Generator" }
QUEUE = {}
ISTimedActionQueue = { queues = {} }
INV = { AddItem = function(_, item) ADDED = ADDED + 1; item.container = INV; return item end,
    Remove = function(_, item) REMOVED = REMOVED + 1; item.container = nil end }
PLAYER = { x = 10.5, y = 20.5, z = 0, isDead = function() return false end, getVehicle = function() return nil end,
    getX = function(s) return s.x end, getY = function(s) return s.y end, getZ = function(s) return s.z end,
    getInventory = function() return INV end,
    teleportTo = function(s, x, y, z) s.x, s.y, s.z = x, y, z end }
ISTimedActionQueue.queues[PLAYER] = { queue = QUEUE }
getSpecificPlayer = function(i) if i == 0 then return PLAYER end end
local function item(name)
    return { kind = "InventoryItem", getFullType = function() return name end,
        getContainer = function(s) return s.container end, getWorldItem = function(s) return s.world end,
        isHumanCorpse = function() return name == "Base.Corpse" end, isAnimalCorpse = function() return false end,
        hasTag = function() return false end, getWorldObjectSprite = function() return nil end }
end
instanceItem = function(name) return item(name) end
local function script(name)
    return { getFullName = function() return name end, getObsolete = function() return false end,
        getSkinCount = function() return 2 end }
end
ScriptManager = { instance = {
    getItem = function(_, name) if name == "Base.TestItem" or name == "Base.Corpse" then return script(name) end end,
    getVehicle = function(_, name) if name == "Base.TestCar" then return script(name) end end,
    getAllItems = function() return list({ script("Other.Tool"), script("Base.TestItem") }) end,
    getAllVehicleScripts = function() return list({ script("Base.TestCar") }) end } }
OBJECTS = {}
SQUARE = { isFree = function() return FREE end,
    getProperties = function() return { has = function() return WATER end } end,
    AddWorldInventoryItem = function(s, it) ADDED = ADDED + 1; it.world = { getSquare = function() return s end }
        return it end,
    transmitRemoveItemFromSquare = function(_, o)
        REMOVED = REMOVED + 1
        for i, x in ipairs(OBJECTS) do if x == o then table.remove(OBJECTS, i) end end
    end,
    getObjects = function() return list(OBJECTS) end,
    getDeadBodys = function() return list(BODIES or {}) end }
ZOMBIES = {}
getCell = function() return { getGridSquare = function() return LOADED and SQUARE or nil end,
    getZombieList = function() return list(ZOMBIES) end } end
addVehicleDebug = function(name, dir, skin, sq)
    assert(name == "Base.TestCar" and dir == 1 and skin == 1 and sq == SQUARE)
    SPAWNS = SPAWNS + 1
    return { kind = "BaseVehicle", getSquare = function() return sq end, getSqlId = function() return 1 end,
        getMaxPassengers = function() return 1 end, getCharacter = function() return OCCUPIED and PLAYER or nil end,
        createVehicleKey = function() return item("Base.CarKey") end,
        permanentlyRemove = function() REMOVED = REMOVED + 1 end }
end
function ZOMBIE(x, y)
    return { kind = "IsoZombie", useless = false, getX = function() return x end, getY = function() return y end,
        isUseless = function(s) return s.useless end, setUseless = function(s, b) s.useless = b end,
        removeFromWorld = function() REMOVED = REMOVED + 1 end, removeFromSquare = function() end }
end
getAllOutfits = function() return list({ "Police" }) end
addZombiesInOutfit = function(...)
    ZOMBIE_ARGS = select("#", ...)
    local x, y, z, count, outfit, chance, crawler, fall, fake, knocked, invulnerable, sitting, health = ...
    assert(x == 15 and y == 20 and z == 0 and outfit == "Police" and chance == 100 and health == 2)
    assert(crawler == true and fall == false and fake == false and knocked == false and invulnerable == false
        and sitting == false)
    SPAWNS = SPAWNS + count
    local zombies = {}
    for i = 1, count do zombies[i] = ZOMBIE(x, y) end
    return list(zombies)
end
for name, methods in pairs({ god = { "isGodMod", "setGodMod" }, ghost = { "isGhostMode", "setGhostMode" } }) do
    local key = name
    PLAYER[key] = false
    PLAYER[methods[1]] = function(s) return s[key] end
    PLAYER[methods[2]] = function(s, b) s[key] = b end
end
local hunger = { getMinimumValue = function() return 0 end, getMaximumValue = function() return 1 end }
CharacterStat = { getById = function(name) return name == "Hunger" and hunger or nil end }
PLAYER.hunger = .5
PLAYER.getStats = function() return { get = function() return PLAYER.hunger end,
    set = function(_, _, value) PLAYER.hunger = value end } end
PLAYER.getBodyDamage = function() return { RestoreToFullHealth = function() PLAYER.healed = true end } end
Perks = { MAX = {}, None = {}, FromString = function(name) return name == "Aiming" and "Aiming" or nil end }
PLAYER.getPerkLevel = function() return PERK_LEVEL end
PLAYER.setPerkLevelDebug = function(_, perk, level) assert(perk == "Aiming"); PERK_LEVEL = level end
PLAYER.getXp = function() return { setXPToLevel = function(_, perk, level) XP_LEVEL = level end } end
getGameTime = function() return { getTimeOfDay = function() return TIME end,
    setTimeOfDay = function(_, n) TIME = n end } end
CLIMATE = {}
getClimateManager = function() return {
    stopWeatherAndThunder = function() WEATHER = "clear" end,
    triggerCustomWeatherStage = function(_, stage, hours) WEATHER, HOURS = stage, hours; return true end,
    getClimateFloat = function(_, id)
        return { setEnableAdmin = function(_, b) CLIMATE[id] = CLIMATE[id] or {}; CLIMATE[id].admin = b end,
            setAdminValue = function(_, v) CLIMATE[id] = CLIMATE[id] or {}; CLIMATE[id].value = v end }
    end } end
ZOOMS = {}
getCore = function() return { doZoomScroll = function(_, _, d) ZOOMS[#ZOOMS + 1] = d end } end
SPEED = 1
UIManager = { getSpeedControls = function() return { SetCurrentGameSpeed = function(_, n) SPEED = n end } end }
"""


@unittest.skipIf(lupa is None, 'lupa missing')
class WorldTest(unittest.TestCase):
    def setUp(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(FAKES)
        self.lua.execute(WORLD.read_text(encoding='utf-8'))
        self.W = self.lua.globals().PZDevKit.World
        self.g = self.lua.globals()

    def fails(self, code):
        ok = self.lua.eval(f'(pcall(function() {code} end))')
        self.assertFalse(ok, code)

    def run_lua(self, code):
        return self.lua.execute(code)

    def test_changes_require_debug_and_solo_before_any_spawn(self):
        self.run_lua('DEBUG = false')
        self.fails('PZDevKit.World.spawnItem("Base.TestItem")')
        self.run_lua('DEBUG = true; CLIENT = true')
        self.fails('PZDevKit.World.spawnItem("Base.TestItem")')
        self.fails('PZDevKit.World.teleport(1, 2, 0)')
        self.run_lua('CLIENT = false; SERVER = true')
        self.fails('PZDevKit.World.spawnZombie(15, 20, 0)')
        self.fails('PZDevKit.World.clearZombies()')
        self.assertEqual((self.g.ADDED, self.g.SPAWNS, self.g.PLAYER.x), (0, 0, 10.5))

    def test_items_use_exact_types_and_cleanup_is_limited_to_creations(self):
        self.fails('PZDevKit.World.spawnItem("TestItem", 2)')
        self.fails('PZDevKit.World.spawnItem("Base.TestItem", 101)')
        self.run_lua('''local W = PZDevKit.World
            ITEMS = W.spawnItem("Base.TestItem", 2)
            assert(#ITEMS == 2 and ADDED == 2 and ITEMS[1] ~= ITEMS[2])
            assert(not pcall(W.removeSpawned, { kind = "InventoryItem" }))
            W.removeSpawned(ITEMS[1]); assert(REMOVED == 1 and ITEMS[1]:getContainer() == nil)
            assert(not pcall(W.removeSpawned, ITEMS[1]))
            local ground = W.spawnWorldItem("Base.TestItem", 15.5, 20.5, 0)
            assert(ground[1]:getWorldItem())
            W.removeSpawned(ground[1]); assert(REMOVED == 2)
            assert(not pcall(W.spawnWorldItem, "Base.Corpse", 15, 20, 0))
            LOADED = false
            assert(not pcall(W.spawnWorldItem, "Base.TestItem", 15, 20, 0))
            assert(ADDED == 3)''')

    def test_failed_item_instantiation_does_not_add_partial_batch(self):
        self.run_lua('''local original, calls = instanceItem, 0
            instanceItem = function(name) calls = calls + 1; if calls == 2 then return nil end
                return original(name) end
            assert(not pcall(PZDevKit.World.spawnItem, "Base.TestItem", 2))
            assert(ADDED == 0 and REMOVED == 0)''')

    def test_vehicle_area_skin_and_occupants_are_checked(self):
        self.run_lua('''local W = PZDevKit.World
            FREE = false; assert(not pcall(W.spawnVehicle, "Base.TestCar", 20, 20, 0, { skin = 1 }))
            FREE = true; WATER = true; assert(not pcall(W.spawnVehicle, "Base.TestCar", 20, 20, 0, { skin = 1 }))
            WATER = false
            assert(not pcall(W.spawnVehicle, "Base.TestCar", 20, 20, 0, { skin = 2 }))
            assert(not pcall(W.spawnVehicle, "Missing.Car", 20, 20, 0))
            assert(SPAWNS == 0)
            local car = W.spawnVehicle("Base.TestCar", 20, 20, 0, { skin = 1 })
            local key = W.vehicleKey(car)
            assert(key:getFullType() == "Base.CarKey" and SPAWNS == 1)
            OCCUPIED = true; assert(not pcall(W.removeSpawned, car))
            OCCUPIED = false; W.removeSpawned(car); W.removeSpawned(key)
            assert(REMOVED == 2)''')

    def test_zombie_options_validate_before_spawn_and_use_the_13_argument_overload(self):
        self.run_lua('''local W = PZDevKit.World
            assert(not pcall(W.spawnZombies, 15, 20, 0, 0))
            assert(not pcall(W.spawnZombies, 15, 20, 0, 1, { outfit = "Unknown" }))
            assert(not pcall(W.spawnZombies, 15, 20, 0, 1, { health = 0 }))
            assert(SPAWNS == 0)
            local zombies = W.spawnZombies(15.8, 20.1, 0, 2, { outfit = "Police", femaleChance = 100, crawler = true,
                health = 2 })
            assert(#zombies == 2 and SPAWNS == 2 and ZOMBIE_ARGS == 13)
            assert(W.freezeZombie(zombies[1], true) == false and zombies[1]:isUseless())
            W.removeSpawned(zombies[1]); assert(REMOVED == 1)''')

    def test_flags_and_stats_are_validated_as_a_batch_and_restorable(self):
        self.run_lua('''local W = PZDevKit.World
            assert(not pcall(W.setFlags, { god = true, invalid = true }))
            assert(PLAYER.god == false)
            local old = W.setFlags({ god = true, ghost = true })
            assert(PLAYER.god and PLAYER.ghost)
            W.setFlags(old); assert(not PLAYER.god and not PLAYER.ghost)
            assert(not pcall(W.setStats, { Hunger = 2 }))
            assert(not pcall(W.setStats, { Hunger = 0, Missing = 0 }))
            assert(PLAYER.hunger == .5)
            old = W.setStats({ Hunger = 0 }); assert(PLAYER.hunger == 0)
            W.setStats(old); assert(PLAYER.hunger == .5)''')

    def test_skills_time_weather_and_discovery_validate_parameters(self):
        self.run_lua('''local W = PZDevKit.World
            assert(not pcall(W.setSkill, "Missing", 10))
            assert(not pcall(W.setSkill, "Aiming", 11))
            assert(W.setSkill("Aiming", 4) == 0 and PERK_LEVEL == 4 and XP_LEVEL == 4)
            assert(not pcall(W.setTime, 24))
            assert(W.setTime(6) == 12 and TIME == 6)
            assert(not pcall(W.weather, "rain"))
            assert(W.weather("storm", 12) == true and WEATHER == 3 and HOURS == 12)
            W.weather("clear"); assert(WEATHER == "clear")
            W.heal(); assert(PLAYER.healed)
            local names = W.itemTypes("test"); assert(#names == 1 and names[1] == "Base.TestItem")
            assert(W.vehicleTypes()[1] == "Base.TestCar")''')

    def test_teleport_refuses_busy_player_bad_values_and_moves(self):
        self.run_lua('''local W = PZDevKit.World
            QUEUE[1] = {}
            assert(not pcall(W.teleport, 30, 40, 0))
            QUEUE[1] = nil
            assert(not pcall(W.teleport, 0/0, 40, 0))
            assert(not pcall(W.teleport, 30, 40, .5))
            W.teleport(30.9, 40.9)
            assert(PLAYER.x == 30 and PLAYER.y == 40 and PLAYER.z == 0)''')

    def test_set_position_places_exactly_without_walking(self):
        self.run_lua('''PLAYER.setX = function(s, v) s.x = v end; PLAYER.setY = function(s, v) s.y = v end
            PLAYER.setZ = function(s, v) s.z = v end
            PLAYER.setLastX = function(s, v) s.lx = v end; PLAYER.setLastY = function(s, v) s.ly = v end
            PLAYER.setLastZ = function(s, v) s.lz = v end
            PZDevKit.World.setPosition(30.5, 40.5)
            assert(PLAYER.x == 30.5 and PLAYER.y == 40.5 and PLAYER.z == 0)
            assert(PLAYER.lx == 30.5 and PLAYER.ly == 40.5 and PLAYER.lz == 0)
            assert(not pcall(PZDevKit.World.setPosition, 0/0, 1))''')
        self.run_lua('CLIENT = true')
        self.fails('PZDevKit.World.setPosition(1, 2)')

    def test_clear_zombies_within_radius_only(self):
        self.run_lua('''ZOMBIES[1] = ZOMBIE(12, 22); ZOMBIES[2] = ZOMBIE(500, 22)
            assert(PZDevKit.World.clearZombies(90) == 1 and REMOVED == 1)''')

    def test_clear_bodies_and_square_clutter(self):
        self.run_lua('''BODIES = { { removeFromWorld = function() REMOVED = REMOVED + 1 end,
            removeFromSquare = function() end } }''')
        self.fails('PZDevKit.World.clearBodies(0)')  # radius 1..100
        self.run_lua('''local n = PZDevKit.World.clearBodies(1)
            assert(n == 18 and REMOVED == 18)  -- the same fake square for 3x3 squares x 2 floors''')
        self.run_lua('''REMOVED = 0
            OBJECTS[1] = { name = "crate" }; OBJECTS[2] = { name = "wall" }
            assert(PZDevKit.World.clearSquare(15, 20, 0, function(o) return o.name == "crate" end) == 1)
            assert(#OBJECTS == 1 and OBJECTS[1].name == "wall")''')
        self.fails('PZDevKit.World.clearSquare(15, 20, 0, "crate")')

    def test_held_weather_and_night_use_climate_admin_values(self):
        self.run_lua('''local W = PZDevKit.World
            W.holdWeather(0.2, 0.1)
            assert(WEATHER == "clear" and CLIMATE[3].value == 0 and CLIMATE[5].value == 0)
            assert(CLIMATE[8].value == 0.2 and CLIMATE[6].value == 0.1 and CLIMATE[8].admin == true)
            assert(not pcall(W.holdWeather, 2))
            W.night(1); assert(CLIMATE[2].admin == true and CLIMATE[2].value == 1)
            W.night(nil); assert(CLIMATE[2].admin == false)''')

    def test_zoom_steps(self):
        self.run_lua('PZDevKit.World.zoom(-2)')
        self.assertEqual(list(self.g.ZOOMS.values()), [-1, -1])
        self.fails('PZDevKit.World.zoom(1.5)')

    def test_speed_is_deferred_while_walking_then_applied(self):
        self.run_lua('''local W = PZDevKit.World
            QUEUE[1] = { Type = "ISWalkToTimedAction" }
            assert(W.speed(3) == "deferred" and SPEED == 1 and #Events.OnTick.handlers == 1)
            Events.OnTick.fire(); assert(SPEED == 1)
            QUEUE[1] = nil
            Events.OnTick.fire(); assert(SPEED == 3 and #Events.OnTick.handlers == 0)
            assert(W.speed(1) == "applied" and SPEED == 1)
            assert(not pcall(W.speed, 5))''')


if __name__ == '__main__':
    unittest.main()
