--[[
Tuto - tutorial video helpers of PZDevKit (DEV-ONLY), formerly pz-tutorial tuto_lib.lua. `pzdev record` writes the
hooks of a video as:  T = PZDevKit.Tuto.new() ; T.name = "<slug>" ; <scene.lua> ; return T.hooks()
so a scene keeps using the global T (fresh for each run). World changes go through PZDevKit.World.
Console protocol read by `pzdev record` (prefix [PZTUTO]):
  start | end | cut | caption <id> | uncaption | step <n> | PASS/FAIL <text> | info <text>
The scene defines T.setup(ctx) (optional) and its steps with T.step{...}:
  caption = id in captions.json (shown from the start of the step), nocaption = true (hide)
  run = function() ... end, wait = minimum seconds, untilIdle = wait for the player's actions,
  until_ = function() return done end (max `limit` seconds, default 30)
  prep = true: runs before the recording starts (teleport, set dressing once the area is loaded)
Menu paths (T.showMenuPath): "*" follows the first submenu that is not a debug one.
Kahlua: ASCII only in this file and in scene.lua (player text lives in captions.json).
]]
require "PZDevKit/World"

PZDevKit = PZDevKit or {}
PZDevKit.Tuto = PZDevKit.Tuto or {}
local W = PZDevKit.World

function PZDevKit.Tuto.new()
    local T = { lines = {}, ok = true, steps = {}, kept = {} }

    function T.rec(ok, name, detail)
        if not ok then T.ok = false end
        T.lines[#T.lines + 1] = (ok and "PASS " or "FAIL ") .. name .. " - " .. tostring(detail or "")
        print("[PZTUTO] " .. T.lines[#T.lines])
    end
    -- Pre-flight check, in prep steps: a failed one stops the run BEFORE the recording starts (fast feedback,
    -- no wasted take). Check everything the scene relies on: objects found, menu entries, squares free...
    function T.require(ok, name, detail)
        T.rec(ok and true or false, "preflight: " .. name, detail)
        if not ok then T.abort = true end
        return ok
    end
    function T.info(text)
        T.lines[#T.lines + 1] = "INFO " .. tostring(text)
        if T.capture then T.capture[#T.capture + 1] = tostring(text) end
        print("[PZTUTO] info " .. tostring(text))
    end
    function T.caption(id) print("[PZTUTO] caption " .. id) end
    function T.step(t) T.steps[#T.steps + 1] = t end

    -- ------------------------------------------------------------------ world
    function T.sq(x, y, z) return getCell():getGridSquare(x, y, z or 0) end
    function T.idle() return ISTimedActionQueue.isPlayerDoingAction(T.player) == false end

    function T.objectWith(square, test)
        local objs = square and square:getObjects()
        for i = 0, objs and objs:size() - 1 or -1 do
            if test(objs:get(i)) then return objs:get(i) end
        end
    end

    -- Remove every object of `square` that matches test (set dressing: clutter in front of a wall).
    function T.clearSquare(square, test)
        if not square then return 0 end
        return W.clearSquare(square:getX(), square:getY(), square:getZ(), test)
    end
    function T.clearZombies(radius) return W.clearZombies(radius) end
    function T.clearBodies(radius) return W.clearBodies(radius) end

    -- Hide what a player never sees: debug watermark and console, character window.
    function T.quiet()
        local ui = UIManager.getUI()
        for i = 0, ui:size() - 1 do
            local t = ui:get(i):getTable()
            if t and t.Type == "WaterMarkUI" then t:setVisible(false) end
        end
        local console = UIManager.getDebugConsole and UIManager.getDebugConsole()
        if console then console:setVisible(false) end
        if ISCharacterInfoWindow and ISCharacterInfoWindow.instance then ISCharacterInfoWindow.instance:setVisible(false) end
        T.clearZombies()
    end

    function T.inventories(visible)
        if getPlayerInventory(0) then getPlayerInventory(0):setVisible(visible) end
        if getPlayerLoot(0) then getPlayerLoot(0):setVisible(visible) end
    end

    -- Moving the player without walking. During the recording it is a CUT: record notes its time and the
    -- assembler dips to black there, so the jump never looks like a glitch. Never move the player one or two
    -- squares this way on camera: walk (T.walkTo) for short moves, cut (teleport) to change place.
    function T.teleport(x, y, z)
        if T.started then print("[PZTUTO] cut") end
        W.setPosition(x, y, z or 0)
    end

    -- Is the straight walk from the player to square s free of fences, walls and windows? (Path finding climbs
    -- over fences: the player jumps them on camera.) Checks every square on the line and their shared edges.
    function T.clearWalk(s)
        local p = T.player
        local x0, y0, x1, y1 = math.floor(p:getX()), math.floor(p:getY()), s:getX(), s:getY()
        local n = math.max(math.abs(x1 - x0), math.abs(y1 - y0))
        local prev = p:getSquare()
        for i = 1, n do
            local q = T.sq(math.floor(x0 + (x1 - x0) * i / n + 0.5), math.floor(y0 + (y1 - y0) * i / n + 0.5), s:getZ())
            if not q or not prev or prev:isBlockedTo(q) or prev:isHoppableTo(q) or not prev:canReachTo(q) then return false end
            prev = q
        end
        return true
    end

    -- Walk to a square; if the straight way crosses a fence or wall, cut there instead (no fence vaulting).
    function T.walkTo(x, y, z)
        local target = T.sq(x, y, z)
        if not target then return end
        if T.clearWalk(target) then
            ISTimedActionQueue.add(ISWalkToTimedAction:new(T.player, target))
        else
            T.teleport(x + 0.5, y + 0.5, z or 0)
        end
    end

    function T.nearSquare(s)
        local fake = { getSquare = function() return s end }
        return T.near(fake)
    end

    -- Stand the player on a free square next to obj (actions started from a menu need it: when no adjacent
    -- square can be reached, the game queues nothing and nothing says so).
    function T.near(obj, prefer)
        local s = obj and obj:getSquare()
        if not s then return false end
        local order = prefer or { { 0, 1 }, { 1, 0 }, { -1, 0 }, { 0, -1 }, { 1, 1 }, { -1, 1 }, { 1, -1 }, { -1, -1 } }
        for _, d in ipairs(order) do
            local n = T.sq(s:getX() + d[1], s:getY() + d[2], s:getZ())
            if n and n:isFree(false) and (n:getRoom() ~= nil) == (s:getRoom() ~= nil) then
                T.teleport(n:getX() + 0.5, n:getY() + 0.5, s:getZ()); T.face(s:getX(), s:getY())
                return true
            end
        end
        return false
    end
    function T.face(x, y) T.player:faceLocation(x, y) end

    -- ------------------------------------------------------------------ gestures and poses (ADR-002)
    -- Vanilla emote of the radial menu (W.EMOTES). hold = seconds before stopping a looping one (optional).
    -- In a step: run = function() T.emote("thumbsup") end, until_ = T.emoteDone
    function T.emote(name, hold)
        assert(W.EMOTES[name], "unknown emote, use an exact vanilla id: " .. tostring(name))
        assert(hold == nil or (type(hold) == "number" and hold > 0 and hold <= 60), "emote hold: 0 to 60 s")
        T.gesture = { at = getTimestampMs(), hold = hold }
        T.player:playEmote(name)
    end
    function T.emoteDone()
        local g = T.gesture
        if g and g.hold and getTimestampMs() - g.at >= g.hold * 1000 then T.player:setVariable("EmotePlaying", false) end
        if T.player:getVariableBoolean("EmotePlaying") then return false end
        T.gesture = nil
        return true
    end
    -- Poses, the player's own vanilla gestures: the sit key, the Rest entry of a seat, crouching, getting up.
    function T.sit()
        T.player:setAutoWalk(false)
        T.player:reportEvent("EventSitOnGround")
    end
    function T.sitOn(seat)
        local path = ISPathFindAction:pathToSitOnFurniture(T.player, seat, true)
        path:setOnComplete(function(action)
            local rest = ISRestAction:new(T.player, action.goalFurnitureObject or seat, true)
            if action:addAfter(rest) == nil then ISTimedActionQueue.add(rest) end
        end, path)
        path:setOnFail(function() T.rec(false, "sit on furniture", "no free seat on this object") end)
        ISTimedActionQueue.add(path)
    end
    function T.crouch(on) T.player:setSneaking(on ~= false) end
    function T.getUp()
        T.player:StopAllActionQueue()
        T.player:setVariable("forceGetUp", true)
    end
    function T.seated() return T.player:isSitting() end
    -- Game speed, time, held weather, night darkness and zoom: PZDevKit.World (a speed-up asked while walking is
    -- applied when the walk ends; fast forward during a walk would cancel it).
    function T.speed(n) return W.speed(n) end
    function T.time(hour) return W.setTime(hour) end
    function T.weather(clouds, wind) return W.holdWeather(clouds, wind) end
    function T.night(strength) return W.night(strength) end
    function T.zoom(steps) return W.zoom(steps) end

    -- Building helpers (IsoMetaGrid / BuildingDef / RoomDef).
    function T.buildingAt(x, y) return getWorld():getMetaGrid():getBuildingAt(x, y, 0) end
    function T.roomOf(def, name, z)
        local rooms = def:getRooms()
        for i = 0, rooms:size() - 1 do
            local r = rooms:get(i)
            if r:getName() == name and r:getZ() == (z or 0) then return r end
        end
    end

    -- ------------------------------------------------------------------ player gestures
    -- Real furniture placement (the furniture cursor's action, with its animation). The sprite name
    -- carries the facing: check it so that the object faces the room.
    function T.placeItem(item, x, y, spriteName, z)
        local props = ISMoveableSpriteProps.new(getSprite(spriteName))
        local dir = props:getFaceDirectionFromSpriteName(spriteName)
        local target = T.sq(x, y, z)
        local can = target and props:canPlaceMoveable(T.player, target, item)
        T.info("place " .. spriteName .. " at " .. x .. "," .. y .. " dir=" .. tostring(dir) .. " canPlace=" .. tostring(can))
        -- next to the target first: walk when the way is clear and short, else cut (no fence vaulting)
        local dx, dy = math.abs(T.player:getX() - x - 0.5), math.abs(T.player:getY() - y - 0.5)
        if dx > 1.6 or dy > 1.6 then
            if not (math.max(dx, dy) <= 6 and T.clearWalk(target)) then T.nearSquare(target) end
        end
        luautils.walkAdj(T.player, target, true)
        -- the action looks the item up by ITS OWN world sprite (the cursor passes it, the facing goes in `dir`):
        -- passing a rotated sprite name (N, W, E facings) made the placement silently do nothing.
        local own = item and item.getWorldSprite and item:getWorldSprite() or spriteName
        ISTimedActionQueue.add(ISMoveablesAction:new(T.player, target, "place", own or spriteName, nil, dir, item, nil))
    end

    -- Vanilla crafting window opened on a recipe (the debug line under the title hidden).
    function T.openCraft(recipeName)
        local recipe = getScriptManager():getCraftRecipe(recipeName)
        if not recipe then T.rec(false, "recipe exists", recipeName); return end
        local debugEnabled = isDebugEnabled
        isDebugEnabled = function() return false end
        local ok, err = pcall(ISEntityUI.OpenHandcraftWindow, T.player, nil, nil, false, recipe)
        isDebugEnabled = debugEnabled
        if not ok then T.rec(false, "crafting window", tostring(err)) end
        -- high on the screen: the subtitles go at the bottom
        local w = T.craftWindow()
        if w then w:setY(20) end
    end
    function T.craftWindow()
        local p = ISEntityUI.players and ISEntityUI.players[T.player:getPlayerNum()]
        local w = p and p.windows and p.windows.HandcraftWindow
        return w and w.instance
    end
    -- Start the shown recipe as the Craft button does (needs the ingredients in the inventory).
    function T.startCraft()
        local w = T.craftWindow()
        if w then ISEntityUI.HandcraftStart(T.player, w.handCraftPanel.logic, true, true) end
    end
    function T.closeCraft()
        local w = T.craftWindow()
        if w then w:close() end
    end

    -- Right-click menu of the game on `obj`, then each level of `path` in turn as the mouse would
    -- (42.22 menus replace a level by its submenu): the entry is highlighted, then its submenu
    -- slides in `perLevel` seconds later. path: texts (or text prefixes) of the options to follow;
    -- "*" follows the first submenu that is not a debug one. T.menuDone() tells when the last entry
    -- is highlighted; T.clickMenu() then runs it as a click does.
    local DEBUG_ENTRIES = { "^Tile Report", "^Room Report", "^Coordinates Report", "^Seed", "^Debug", "^Inspect", "^Object",
        "^Teleport", "^Remove", "^Spawn", "^Zombie", "^Light", "^Fluid", "^Entity", "^Durability", "container distro" }
    -- A mod's own menu callback to keep although its name looks like a debug entry (e.g. its "Inspect").
    function T.keepEntry(callback) if callback then T.kept[callback] = true end end
    local function dropDebug(menu)
        local drop = {}
        for _, opt in ipairs(menu.options or {}) do
            local n = tostring(opt.name)
            -- keep a mod's own entry registered with T.keepEntry (an "Inspect" entry matches the debug pattern by name)
            local own = opt.onSelect ~= nil and T.kept[opt.onSelect] == true
            -- the object's own "Light Switch" submenu holds the mod's wiring entries (it matches "^Light")
            if n:find("^Light Switch") then own = true end
            if not own then
                for _, pat in ipairs(DEBUG_ENTRIES) do if n:find(pat) then drop[#drop + 1] = opt.name; break end end
            end
        end
        for _, n in ipairs(drop) do menu:removeOptionByName(n) end
    end
    local function highlight(cur, want)
        local found
        for i, opt in ipairs(cur.options or {}) do
            if not found and tostring(opt.name):sub(1, #want) == want then found = opt; cur.mouseOver = i end
        end
        if not found and want == "*" then
            for i, opt in ipairs(cur.options or {}) do
                if not found and opt.subOption and not tostring(opt.name):find("^Debug") then found = opt; cur.mouseOver = i end
            end
        end
        -- the game shows the submenu of the highlighted entry at once: no debug entry in it
        if found and found.subOption then
            local sub = cur:getSubMenu(found.subOption)
            if sub then dropDebug(sub) end
        end
        if not found then
            local names = {}
            for _, opt in ipairs(cur.options or {}) do names[#names + 1] = tostring(opt.name) end
            T.info("menu entry not found: " .. want .. " among: " .. table.concat(names, " | "))
        end
        return found
    end
    function T.showMenuPath(obj, path, perLevel)
        T.closeMenu()
        local num = T.player:getPlayerNum()
        local s = obj:getSquare()
        local x = isoToScreenX(num, s:getX() + 0.5, s:getY() + 0.5, s:getZ())
        local y = isoToScreenY(num, s:getX() + 0.5, s:getY() + 0.5, s:getZ())
        local menu = ISWorldObjectContextMenu.createMenu(num, { obj }, x, y)
        if not menu then return end
        dropDebug(menu)
        T.menu = menu
        T.menuAnim = { cur = menu, path = path or {}, n = 1, every = (perLevel or 0.9) * 1000, at = getTimestampMs() }
        T.menuAnim.found = highlight(menu, T.menuAnim.path[1] or "")
        T.menuFinal = (#T.menuAnim.path <= 1) and T.menuAnim.found or nil
    end
    -- Called by the runner at each poll.
    function T.menuTick()
        local a = T.menuAnim
        if not a or T.menuFinal or not a.found then return end
        local now = getTimestampMs()
        if now - a.at < a.every then return end
        if not a.found.subOption then T.menuFinal = a.found; return end
        local sub = a.cur:getSubMenu(a.found.subOption)
        if not sub then T.menuFinal = a.found; return end
        dropDebug(sub)
        a.cur:displaySubMenu(sub, a.found)
        a.cur, a.n, a.at = sub, a.n + 1, now
        a.found = highlight(sub, a.path[a.n] or "")
        if a.n >= #a.path then T.menuFinal = a.found end
    end
    function T.menuDone() return T.menuFinal ~= nil or (T.menuAnim and not T.menuAnim.found) end
    -- Run the highlighted last entry of the shown path (its own callback, as a click does).
    function T.clickMenu(opt)
        opt = opt or T.menuFinal
        T.closeMenu()
        if opt and opt.onSelect then
            opt.onSelect(opt.target, opt.param1, opt.param2, opt.param3, opt.param4, opt.param5, opt.param6, opt.param7,
                opt.param8, opt.param9, opt.param10)
        end
    end
    function T.closeMenu()
        if T.menu then T.menu:closeAll() end
        T.menu, T.menuAnim, T.menuFinal = nil, nil, nil
    end

    -- ------------------------------------------------------------------ live takes
    -- record --live: after the prep steps the game stays open and waits; Lua is sent with `pzdev lua` (PZDevKit
    -- live channel, T is a global of the hooks) and `pzdev take <video-dir>` sends T.take(): the recorded steps are
    -- played (and filmed by record), then the game waits again: undo what the take did, adjust, take again.
    function T.take()
        if T.abort then return "refused: a pre-flight check failed (fix it, then T.abort = false)" end
        T.takeNow = true
        return "take requested"
    end

    -- ------------------------------------------------------------------ runner
    function T.hooks()
        local H = {}
        function H.start(ctx)
            T.player, T.ctx = getPlayer(), ctx
            T.errors = getLuaDebuggerErrorCount()
            T.shots = ctx.params.shots == "1"
            T.live = ctx.params.live == "1"
            local p = T.player
            p:setGodMod(true)
            getSandboxOptions():getOptionByName("ElecShutModifier"):setValue(0)
            T.inventories(false)
            if T.setup then
                local ok, err = pcall(T.setup, ctx)
                if not ok then T.rec(false, "scene setup", tostring(err)); return true end
            end
            T.quiet()
            T.i, T.at = 0, getTimestampMs()
            T.started = false
            return true
        end
        function H.done(ctx)
            local now = getTimestampMs()
            T.clearZombies()
            T.menuTick()
            -- live: wait for T.take() before the recorded steps
            if T.holding then
                if not T.takeNow then return false end
                T.holding, T.takeNow, T.takeStarted = false, false, true
            end
            local cur = T.steps[T.i]
            if cur then
                local elapsed = (now - T.at) / 1000
                if elapsed < (cur.wait or 0) then return false end
                if cur.untilIdle and not T.idle() and elapsed < (cur.limit or 60) then return false end
                if cur.until_ and not cur.until_() and elapsed < (cur.limit or 30) then return false end
            end
            if T.shots and T.i > 0 then pcall(takeScreenshot, string.format("step_%02d.png", T.i)) end
            T.i = T.i + 1
            local nextStep = T.steps[T.i]
            if not nextStep then
                T.rec(getLuaDebuggerErrorCount() == T.errors, "no Lua error", getLuaDebuggerErrorCount() - T.errors)
                print("[PZTUTO] end")
                if T.live and T.firstRec then
                    -- back to the start of the recorded steps, waiting for the next T.take()
                    T.speed(1)
                    T.i, T.started, T.holding = T.firstRec - 1, false, true
                    return false
                end
                return true
            end
            T.quiet()
            -- a failed pre-flight check stops at once: no later prep step runs on a wrong set-up (red errors)
            if not T.started and T.abort and T.live then
                T.i, T.holding = T.i - 1, true
                return false
            end
            if not T.started and T.abort then
                print("[PZTUTO] end")
                T.rec(false, "preflight failed: nothing recorded")
                return true
            end
            if not nextStep.prep and not T.started and T.live and not T.takeStarted then
                -- first time at the recorded steps: wait for T.take()
                T.firstRec = T.firstRec or T.i
                T.i, T.holding = T.i - 1, true
                print("[PZTUTO] live: ready (prep done), waiting for commands")
                T.takeStarted = true
                return false
            end
            if not nextStep.prep and not T.started then
                T.started, T.takeStarted = true, false
                T.errors, T.ok, T.lines = getLuaDebuggerErrorCount(), true, {}
                if ctx.params.dry ~= "1" then print("[PZTUTO] start") end
            end
            if nextStep.caption then T.caption(nextStep.caption) elseif nextStep.nocaption then print("[PZTUTO] uncaption") end
            if nextStep.run then
                local ok, err = pcall(nextStep.run)
                if not ok then
                    T.rec(false, "step " .. T.i .. " ran", tostring(err))
                    if nextStep.prep then T.abort = true end
                end
            end
            print("[PZTUTO] step " .. T.i)
            T.at = now
            return false
        end
        function H.result() return { ok = T.ok, summary = "tutorial " .. tostring(T.name), lines = T.lines } end
        return H
    end
    return T
end

return PZDevKit.Tuto
