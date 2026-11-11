--[[
World - world and character helpers of PZDevKit (DEV-ONLY): one implementation of each helper, merged from
PZPuppeteer (PZPuppet.Debug: checked spawns, flags, stats, skills, cleanup of what was created) and pz-tutorial
(tuto_lib: clearing zombies, bodies and clutter, held weather, night, zoom, deferred game speed).

Every function needs a game started with -debug; the ones that change the world also need a solo game (no client,
no server): they raise an error otherwise. Arguments are checked before anything changes; a batch (items, flags,
stats) is all or nothing. Functions that change a value return the previous one so that a test can restore it.
Called from the live channel (`pzdev lua`, `pzdev world ...`), from test hooks and from scenarios.
]]

PZDevKit = PZDevKit or {}
PZDevKit.World = PZDevKit.World or {}
local W = PZDevKit.World
local spawned = W.spawned or {}
W.spawned = spawned
-- Vanilla emote ids of the radial menu, variants included (ISEmoteRadialMenu.defaultMenu and .variants).
W.EMOTES = { wavehi = true, wavehi02 = true, wavebye = true, clap = true, clap02 = true, thumbsup = true,
    thankyou = true, insult = true, stop = true, stop02 = true, surrender = true, thumbsdown = true, followme = true,
    comehere = true, comehere02 = true, yes = true, no = true, shrug = true, undecided = true, ceasefire = true,
    signalok = true, moveout = true, freeze = true, followbehind = true, signalfire = true, comefront = true,
    saluteformal = true, salutecasual = true }

local function debugMode()
    assert(isDebugEnabled(), "World helpers require -debug")
end
local function authority()
    debugMode()
    assert(not isClient() and not isServer(), "World changes require a solo game")
end
local function finite(n, label)
    assert(type(n) == "number" and n == n and math.abs(n) < math.huge, label .. " must be finite")
    return n
end
local function integer(n, minimum, maximum, label)
    finite(n, label)
    assert(n == math.floor(n) and n >= minimum and n <= maximum, label .. " outside allowed integer range")
    return n
end
local function player(index)
    index = integer(index or 0, 0, 3, "playerIndex")
    local p = getSpecificPlayer(index)
    assert(p and not p:isDead(), "No living local player")
    return p
end
local function square(x, y, z)
    finite(x, "x"); finite(y, "y"); finite(z, "z")
    local sq = getCell():getGridSquare(math.floor(x), math.floor(y), math.floor(z))
    assert(sq, "Target square is not loaded")
    return sq
end
local function itemScript(fullType)
    assert(type(fullType) == "string", "Use a full item type")
    local script = ScriptManager.instance:getItem(fullType)
    assert(script and script:getFullName() == fullType and not script:getObsolete(),
        "Unknown or obsolete item: " .. fullType)
end
local function track(object, kind)
    assert(object, "Native spawn returned nil")
    spawned[object] = kind
    return object
end
local function queueSize(p)
    local queue = ISTimedActionQueue.queues[p]
    return queue and #queue.queue or 0
end

-- ------------------------------------------------------------------ player

function W.position(index)
    debugMode()
    local p = player(index)
    return { x = p:getX(), y = p:getY(), z = p:getZ() }
end

-- Instant move (no walk). The destination may still be loading on return: wait for its square before using it.
function W.teleport(x, y, z, index)
    authority()
    finite(x, "x"); finite(y, "y"); integer(z or 0, -32, 31, "z")
    local p = player(index)
    assert(not p:getVehicle() and queueSize(p) == 0, "Teleport requires an idle player outside a vehicle")
    p:teleportTo(math.floor(x), math.floor(y), z or 0)
    return p
end

-- Exact placement (sub-square position, e.g. x + 0.5 for the centre), no queue check: a cut in a filmed scene.
-- teleportTo floors its coordinates (42.22 IsoGameCharacter.java:15309); this writes the position as given.
function W.setPosition(x, y, z, index)
    authority()
    finite(x, "x"); finite(y, "y"); integer(z or 0, -32, 31, "z")
    local p = player(index)
    p:setX(x); p:setY(y); p:setZ(z or 0)
    p:setLastX(x); p:setLastY(y); p:setLastZ(z or 0)
    return p
end

local flagMethods = {
    god = { "isGodMod", "setGodMod" }, ghost = { "isGhostMode", "setGhostMode" },
    invisible = { "isInvisible", "setInvisible" },
    instantActions = { "isTimedActionInstantCheat", "setTimedActionInstantCheat" },
    unlimitedCarry = { "isUnlimitedCarry", "setUnlimitedCarry" } }
function W.setFlags(values, index)
    authority()
    assert(type(values) == "table", "Expected flag table")
    local p = player(index)
    local old = {}
    for name, value in pairs(values) do
        assert(flagMethods[name] and type(value) == "boolean", "Unknown flag or non-boolean value: " .. tostring(name))
        old[name] = p[flagMethods[name][1]](p)
    end
    for name, value in pairs(values) do p[flagMethods[name][2]](p, value) end
    return old
end

function W.setStats(values, index)
    authority()
    assert(type(values) == "table", "Expected stat table")
    local stats = player(index):getStats()
    local definitions, old = {}, {}
    for name, value in pairs(values) do
        assert(type(name) == "string", "Use a CharacterStat identifier")
        local stat = CharacterStat.getById(name)
        assert(stat, "Unknown stat: " .. name)
        finite(value, name)
        assert(value >= stat:getMinimumValue() and value <= stat:getMaximumValue(), "Stat outside bounds: " .. name)
        definitions[name], old[name] = stat, stats:get(stat)
    end
    for name, value in pairs(values) do stats:set(definitions[name], value) end
    return old
end

function W.heal(index)
    authority()
    player(index):getBodyDamage():RestoreToFullHealth()
end

function W.setSkill(name, level, index)
    authority()
    assert(type(name) == "string", "Use a perk identifier")
    local perk = Perks.FromString(name)
    assert(perk and perk ~= Perks.MAX and perk ~= Perks.None, "Unknown perk: " .. name)
    integer(level, 0, 10, "level")
    local p = player(index)
    local previous = p:getPerkLevel(perk)
    p:setPerkLevelDebug(perk, level)
    p:getXp():setXPToLevel(perk, level)
    return previous
end

-- ------------------------------------------------------------------ spawns (tracked, removable)

function W.spawnItem(fullType, count, index)
    authority()
    itemScript(fullType)
    count = integer(count or 1, 1, 100, "count")
    local inv = player(index):getInventory()
    local items = {}
    -- Instantiate the entire batch before changing the inventory.
    for i = 1, count do items[i] = assert(instanceItem(fullType), "Cannot create item") end
    for _, item in ipairs(items) do assert(inv:AddItem(item), "Cannot add item"); track(item, "item") end
    return items
end

function W.spawnWorldItem(fullType, x, y, z, count)
    authority()
    itemScript(fullType)
    local sq = square(x, y, z)
    count = integer(count or 1, 1, 100, "count")
    local items = {}
    for i = 1, count do
        local item = assert(instanceItem(fullType), "Cannot create item")
        assert(not item:isHumanCorpse() and not item:isAnimalCorpse() and not instanceof(item, "AnimalInventoryItem")
            and not item:getFullType():find(".Generator", 1, true)
            and not (item:hasTag(ItemTag.GENERATOR) and item:getWorldObjectSprite()),
            "spawnWorldItem supports ordinary ground items, not corpses, animals or generators")
        items[i] = item
    end
    for _, item in ipairs(items) do
        assert(sq:AddWorldInventoryItem(item, x - math.floor(x), y - math.floor(y), 0, true), "Cannot place item")
        track(item, "item")
    end
    return items
end

function W.spawnVehicle(fullType, x, y, z, options)
    authority()
    options = options or {}
    assert(type(fullType) == "string", "Use a full vehicle script name")
    local script = ScriptManager.instance:getVehicle(fullType)
    assert(script and script:getFullName() == fullType, "Unknown vehicle script: " .. fullType)
    local sq = square(x, y, z)
    assert(math.floor(z) == 0, "Spawn vehicles on the ground floor")
    local direction = options.direction or "N"
    assert(direction == "N" or direction == "S" or direction == "E" or direction == "W", "direction must be N/S/E/W")
    local skin = options.skin
    if skin ~= nil then integer(skin, 0, script:getSkinCount() - 1, "skin") end
    local radius = integer(options.clearRadius or 4, 1, 20, "clearRadius")
    for dx = -radius, radius do
        for dy = -radius, radius do
            local other = square(math.floor(x) + dx, math.floor(y) + dy, z)
            assert(other:isFree(true) and not other:getProperties():has(IsoFlagType.water), "Vehicle area is obstructed")
        end
    end
    local vehicle = assert(addVehicleDebug(fullType, IsoDirections[direction], skin, sq), "Cannot create vehicle")
    -- addVehicleDebug may return an object even when its placement failed.
    assert(vehicle:getSquare() and vehicle:getSqlId() ~= -1, "Native vehicle placement failed")
    return track(vehicle, "vehicle")
end

function W.vehicleKey(vehicle, index)
    authority()
    assert(vehicle and instanceof(vehicle, "BaseVehicle"), "Expected a vehicle")
    local inv = player(index):getInventory()
    local key = assert(vehicle:createVehicleKey(), "Cannot create vehicle key")
    assert(inv:AddItem(key), "Cannot add key")
    return track(key, "item")
end

-- 42.22 keeps the 13-argument overload of addZombiesInOutfit (LuaManager.java:8334) next to the longer ones.
function W.spawnZombies(x, y, z, count, options)
    authority()
    options = options or {}
    square(x, y, z)
    count = integer(count or 1, 1, 100, "count")
    local chance = integer(options.femaleChance or 50, 0, 100, "femaleChance")
    if options.outfit then
        local found = false
        for _, female in ipairs({ false, true }) do
            local list = getAllOutfits(female)
            for i = 0, list:size() - 1 do if list:get(i) == options.outfit then found = true end end
        end
        assert(found, "Unknown zombie outfit")
    end
    local health = finite(options.health or 1, "health")
    assert(health > 0, "Use positive zombie health")
    local flags = {}
    for _, name in ipairs({ "crawler", "fallOnFront", "fakeDead", "knockedDown", "invulnerable", "sitting" }) do
        assert(options[name] == nil or type(options[name]) == "boolean", name .. " must be boolean")
        flags[name] = options[name] == true
    end
    local list = assert(addZombiesInOutfit(math.floor(x), math.floor(y), math.floor(z), count, options.outfit, chance,
        flags.crawler, flags.fallOnFront, flags.fakeDead, flags.knockedDown, flags.invulnerable, flags.sitting, health),
        "Zombie spawn failed")
    local result = {}
    for i = 0, list:size() - 1 do result[#result + 1] = track(list:get(i), "zombie") end
    assert(#result == count, "Native zombie spawn returned fewer zombies than requested")
    return result
end

function W.spawnZombie(x, y, z, options)
    return W.spawnZombies(x, y, z, 1, options)[1]
end

function W.freezeZombie(zombie, freeze)
    authority()
    assert(zombie and instanceof(zombie, "IsoZombie") and type(freeze) == "boolean", "Expected zombie and boolean")
    local previous = zombie:isUseless()
    zombie:setUseless(freeze)
    return previous
end

function W.removeSpawned(object)
    authority()
    local kind = spawned[object]
    assert(kind, "Only objects created by PZDevKit.World can be removed")
    if kind == "item" then
        local world = object:getWorldItem()
        if world and world:getSquare() then world:getSquare():transmitRemoveItemFromSquare(world)
        elseif object:getContainer() then object:getContainer():Remove(object) end
    elseif kind == "vehicle" then
        for seat = 0, object:getMaxPassengers() - 1 do assert(not object:getCharacter(seat), "Vehicle is occupied") end
        object:permanentlyRemove()
    elseif kind == "zombie" then
        object:removeFromWorld()
        object:removeFromSquare()
    end
    spawned[object] = nil
end

-- ------------------------------------------------------------------ cleanup (not limited to our spawns)

-- Every zombie within radius squares (default 90) of the player. Returns the count.
function W.clearZombies(radius, index)
    authority()
    radius = finite(radius or 90, "radius")
    local p = player(index)
    local zs = getCell():getZombieList()
    local n = 0
    for i = zs:size() - 1, 0, -1 do
        local z = zs:get(i)
        if z and math.abs(z:getX() - p:getX()) < radius and math.abs(z:getY() - p:getY()) < radius then
            spawned[z] = nil
            z:removeFromWorld(); z:removeFromSquare()
            n = n + 1
        end
    end
    return n
end

-- Every dead body within radius squares of the player, floors 0 and 1. Returns the count.
function W.clearBodies(radius, index)
    authority()
    radius = integer(radius or 20, 1, 100, "radius")
    local p = player(index)
    local px, py = math.floor(p:getX()), math.floor(p:getY())
    local n = 0
    for y = py - radius, py + radius do
        for x = px - radius, px + radius do
            for z = 0, 1 do
                local s = getCell():getGridSquare(x, y, z)
                local bodies = s and s:getDeadBodys()
                for i = (bodies and bodies:size() or 0) - 1, 0, -1 do
                    local b = bodies:get(i)
                    b:removeFromWorld(); b:removeFromSquare()
                    n = n + 1
                end
            end
        end
    end
    return n
end

-- Removes every object of the square for which test(object) is true (set dressing). Returns the count.
function W.clearSquare(x, y, z, test)
    authority()
    assert(type(test) == "function", "Expected a test function")
    local sq = square(x, y, z)
    local objs = sq:getObjects()
    local n = 0
    for i = objs:size() - 1, 0, -1 do
        local o = objs:get(i)
        if test(o) then sq:transmitRemoveItemFromSquare(o); n = n + 1 end
    end
    return n
end

-- ------------------------------------------------------------------ time, weather, camera

function W.setTime(hours)
    authority()
    finite(hours, "hours"); assert(hours >= 0 and hours < 24, "hours must be in [0,24)")
    local time = getGameTime()
    local previous = time:getTimeOfDay()
    time:setTimeOfDay(hours)
    return previous
end

-- A weather event: clear (stops rain and thunder), storm, tropical or blizzard for hours (default 24).
function W.weather(kind, hours)
    authority()
    local stages = { storm = 3, tropical = 8, blizzard = 7 }
    assert(kind == "clear" or stages[kind], "weather must be clear/storm/tropical/blizzard")
    local climate = getClimateManager()
    if kind == "clear" then climate:stopWeatherAndThunder(); return end
    hours = finite(hours or 24, "hours"); assert(hours > 0, "hours must be positive")
    return climate:triggerCustomWeatherStage(stages[kind], hours)
end

-- Climate admin values (the debug climate panel's way, ids of ISAdmPanelClimate.lua). value nil gives the
-- control back to the game.
local function hold(id, value)
    local f = getClimateManager():getClimateFloat(id)
    if value == nil then f:setEnableAdmin(false); return end
    finite(value, "climate value"); assert(value >= 0 and value <= 1, "climate values are in [0,1]")
    f:setEnableAdmin(true); f:setAdminValue(value)
end

-- Dry weather held for a shot: rain and fog off, clouds and wind 0..1 (nil keeps the game's own).
function W.holdWeather(clouds, wind)
    authority()
    getClimateManager():stopWeatherAndThunder()
    hold(3, 0) -- FLOAT_PRECIPITATION_INTENSITY
    hold(5, 0) -- FLOAT_FOG_INTENSITY
    if clouds ~= nil then hold(8, clouds) end -- FLOAT_CLOUD_INTENSITY
    if wind ~= nil then hold(6, wind) end -- FLOAT_WIND_INTENSITY
end

-- Night darkness held: 1 = darkest, nil = back to the game's own (ClimateManager FLOAT_NIGHT_STRENGTH).
function W.night(strength)
    authority()
    hold(2, strength)
end

-- Camera zoom: steps of the mouse wheel (negative = closer).
function W.zoom(steps)
    debugMode()
    integer(steps, -20, 20, "steps")
    for _ = 1, math.abs(steps) do getCore():doZoomScroll(0, steps < 0 and -1 or 1) end
end

-- Game speed 1..4. Fast forward during a walk cancels the walk and the action after it (seen in 42.22: the queue
-- empties): a speed-up asked while walking is applied when the walk ends (OnTick, only while waiting).
local pendingSpeed = nil
local function walking(p)
    local queue = ISTimedActionQueue.queues[p]
    local first = queue and queue.queue[1]
    return first ~= nil and first.Type == "ISWalkToTimedAction"
end
local function speedTick()
    if pendingSpeed == nil then Events.OnTick.Remove(speedTick); return end
    if walking(getSpecificPlayer(0)) then return end
    UIManager.getSpeedControls():SetCurrentGameSpeed(pendingSpeed)
    pendingSpeed = nil
    Events.OnTick.Remove(speedTick)
end
function W.speed(n)
    authority()
    integer(n, 1, 4, "speed")
    if n > 1 and walking(player(0)) then
        if pendingSpeed == nil then Events.OnTick.Add(speedTick) end
        pendingSpeed = n
        return "deferred"
    end
    pendingSpeed = nil
    Events.OnTick.Remove(speedTick)
    UIManager.getSpeedControls():SetCurrentGameSpeed(n)
    return "applied"
end

-- ------------------------------------------------------------------ discovery

local function types(list, query)
    assert(query == nil or type(query) == "string", "Expected an optional text filter")
    local result = {}
    query = (query or ""):lower()
    for i = 0, list:size() - 1 do
        local name = list:get(i):getFullName()
        if name:lower():find(query, 1, true) then result[#result + 1] = name end
    end
    table.sort(result)
    return result
end
function W.itemTypes(query)
    debugMode()
    return types(ScriptManager.instance:getAllItems(), query)
end
function W.vehicleTypes(query)
    debugMode()
    return types(ScriptManager.instance:getAllVehicleScripts(), query)
end

return W
