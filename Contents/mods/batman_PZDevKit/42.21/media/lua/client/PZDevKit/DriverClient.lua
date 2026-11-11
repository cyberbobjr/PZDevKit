--[[
DriverClient (ex-PZAT_Client) - client side of the generic automatic test driver (pz-autotest). Development mod only. Does nothing
without Zomboid/Lua/pz-autotest/command.txt (format in shared/PZDevKit/Driver.lua).

role=sp      main menu: "Break On Error" off; OnFETick waits for MainScreen.instance and 3 s, then
             MainScreen.continueLatestSave(gameMode, save) (what LoadGameScreen:clickPlay calls). The loading screen
             waits for a left click (GameLoadingState.update reads Mouse.isButtonDown(0)): the launcher posts it to the
             window while the last status is "load". A save error dialog (MainScreen.instance.checkSavefileModal)
             fails the launch. A Lua reset (save mods different from the menu list) fires OnMainMenuEnter again in a
             new Lua state: the status file says that the load was already asked.
role=mpclient main menu: ConnectToServer.instance:connect(...) as the "Join server" popup (ServerConnectPopup.lua).
             The connection resets Lua; in the new state the driver presses NEXT on CharacterCreationProfession then
             CharacterCreationMain (vanilla defaults; the server ini has a fixed SpawnPoint), status "load", and the
             launcher clicks the loading screen. OnConnectFailed or a return to the plain menu fails the launch.
In game      OnGameStart: status "ingame"; the run (Driver.lua) is stepped on OnTickEvenPaused (also while paused):
             world gate first (C.worldCheck, status "world"), then the start delay, "ready" / "go" (control=true),
             the hooks; at the end result.txt, then (control=true) wait for "quit" in control.txt, screenshot,
             quitToDesktop (GameWindow.exit saves the copy of the save first).
             An MP client is not in the world yet at OnGameStart: IngameState.enter fires it before
             sendPlayerConnect and waits for the server answer (onlineId) only afterwards.
]]

require "PZDevKit/Driver"

local Z = PZDevKit.Driver
Z.Client = Z.Client or {}
local C = Z.Client

C.MENU_DELAY_MS = 3000
C.CREATE_STEP_MS = 1500
C.JOIN_MENU_MS = 20000
C.JOIN_LOAD_MS = 120000

local function isClientRole(cmd)
    return cmd ~= nil and (cmd.role == "sp" or cmd.role == "mpclient")
end

-- ---------------------------------------------------------------- end of the launch

local quitState = nil

local function quitTick()
    local q = quitState
    if not q or Z.nowMs() < q.at then return end
    if q.step == "shot" then
        q.step = "quit"
        q.at = Z.nowMs() + 1500
        local ok, err = pcall(takeScreenshot, "pz-autotest-" .. Z._cmd.token .. ".png")
        if not ok then Z.log("screenshot failed: " .. Z.oneLine(err)) end
        return
    end
    quitState = nil
    Events.OnTickEvenPaused.Remove(quitTick)
    Z.status("quit", "quitToDesktop")
    getCore():quitToDesktop()
end

-- Screenshot (in game, when asked) then quit to desktop. In the menu: quit at once.
function C.finish(inGame)
    local cmd = Z._cmd
    if cmd and not cmd.quit then
        Z.status("open", "quit=false: the game stays open")
        return
    end
    if not inGame then
        Z.status("quit", "quitToDesktop from the menu")
        getCore():quitToDesktop()
        return
    end
    quitState = { step = (cmd and cmd.screenshot) and "shot" or "quit", at = Z.nowMs() + 1000 }
    Events.OnTickEvenPaused.Add(quitTick)
end

function C.fail(reason, inGame)
    Z.log("ERROR: " .. reason)
    Z.status("error", reason)
    Z.writeResult("client", nil, 0, reason)
    C.finish(inGame)
end

-- ---------------------------------------------------------------- main menu

local menu = nil
local menuTick

local function stopMenu()
    menu = nil
    Events.OnFETick.Remove(menuTick)
end

-- Presses a vanilla screen button by its "internal" name (what a mouse click on it calls).
local function press(panel, internal)
    return pcall(function() panel:onOptionMouseDown({ internal = internal }, 0, 0) end)
end

local function isVisible(panel)
    if panel == nil then return false end
    local ok, v = pcall(function() return panel:getIsVisible() end)
    return ok and v and true or false
end

local function gameMode()
    -- 42.22: a GameMode object whose toString is its id ("Multiplayer"); older builds returned the string.
    local ok, v = pcall(function() return getWorld():getGameMode() end)
    if ok and v ~= nil then return tostring(v) end
    return nil
end

local function join(screen)
    local cmd = Z._cmd
    Z.status("connect", cmd.host .. ":" .. cmd.port .. " as " .. cmd.user)
    local ok, err = pcall(function()
        ConnectToServer.instance:connect(screen.bottomPanel or screen, "", cmd.user, cmd.password, cmd.host, "",
            cmd.port, "", false, true, 1)
    end)
    if not ok then
        stopMenu()
        C.fail("ConnectToServer.connect failed: " .. Z.oneLine(err), false)
    end
end

-- MP, new Lua state after the connection reset: character creation of a new account, then the loading screen.
local function joinedTick(m, screen)
    local now = Z.nowMs()
    if m.phase == "create" then
        if now < m.at then return end
        stopMenu()
        local main = screen and screen.charCreationMain or nil
        local ok, err = press(main, "NEXT")
        if not ok then
            C.fail("character creation: NEXT of CharacterCreationMain failed: " .. Z.oneLine(err), false)
            return
        end
        Z.status("load", "character created; loading the server world")
        return
    end
    local profession = screen and screen.charCreationProfession or nil
    if isVisible(profession) then
        Z.status("create", "character creation shown by ConnectToServer:OnConnected")
        local ok, err = press(profession, "NEXT")
        if not ok then
            stopMenu()
            C.fail("character creation: NEXT of CharacterCreationProfession failed: " .. Z.oneLine(err), false)
            return
        end
        m.phase = "create"
        m.at = now + C.CREATE_STEP_MS
        return
    end
    if now - m.at >= C.JOIN_MENU_MS and gameMode() ~= "Multiplayer" then
        stopMenu()
        C.fail("connection lost: back on the main menu without a character creation", false)
        return
    end
    if now - m.at >= C.JOIN_LOAD_MS then
        stopMenu()
        Z.status("load", "no character creation (existing character?): loading")
    end
end

menuTick = function()
    local m = menu
    if not m then return end
    local screen = MainScreen and MainScreen.instance or nil
    if m.phase == "joined" or m.phase == "create" then
        joinedTick(m, screen)
        return
    end
    if m.phase == "joining" then return end -- OnConnectFailed or the Lua reset of the connection ends this state
    if m.phase == "wait" then
        if screen == nil then return end
        if m.at == nil then m.at = Z.nowMs() + C.MENU_DELAY_MS end
        if Z.nowMs() < m.at then return end
        if Z._cmd.role == "mpclient" then
            m.phase = "joining"
            join(screen)
            return
        end
        m.phase = "asked"
        Z.status("load", Z._cmd.gameMode .. "/" .. Z._cmd.save)
        local ok, err = pcall(MainScreen.continueLatestSave, Z._cmd.gameMode, Z._cmd.save)
        if not ok then
            stopMenu()
            C.fail("MainScreen.continueLatestSave failed: " .. Z.oneLine(err), false)
        end
        return
    end
    -- After the request: the menu only stays when vanilla refused the save with a dialog, except the world
    -- conversion warning (save of an older build, MainScreen.continueLatestSaveAux): YES once, on the cache copy.
    local modal = screen and screen.checkSavefileModal or nil
    if modal ~= nil and not m.converted and modal.yes ~= nil and modal.onClick ~= nil
            and modal.text == getText("UI_worldscreen_SavefileConversion") then
        m.converted = true
        Z.status("load", "save conversion accepted (older world version, cache copy only)")
        local ok, err = pcall(modal.onClick, modal, modal.yes)
        if not ok then
            stopMenu()
            C.fail("save conversion: YES failed: " .. Z.oneLine(err), false)
        end
        return
    end
    if screen ~= nil and screen.checkSavefileModal ~= nil then
        stopMenu()
        C.fail("the main menu refused the save (save error dialog: missing mod, map or version)", false)
    end
end

local function startJoined()
    if menu then return end
    Z.status("menu", "Lua reset of the connection; waiting for the character creation")
    menu = { phase = "joined", at = Z.nowMs() }
    Events.OnFETick.Add(menuTick)
end

local function onMainMenuEnter()
    local cmd = Z.command()
    if not isClientRole(cmd) then
        if Z.invalid and not Z._invalidReported then
            Z._invalidReported = true
            Z.writeResult("client", nil, 0, "command.txt refused: " .. Z.invalid)
        end
        return
    end
    Z.muteDebugger()
    if Z.hasStatus("ingame") then
        -- Back at the menu after the game (exitToMenu by a test, or a lost connection): never load again.
        Z.status("menu", "back at the main menu after the game")
        if not Z.hasStatus("done") then Z.writeResult("client", nil, 0, "back at the main menu before the end") end
        C.finish(false)
        return
    end
    if menu then return end
    if cmd.role == "mpclient" and Z.hasStatus("connect") then
        if Z.hasStatus("load") then return end
        startJoined()
        return
    end
    if cmd.role == "sp" and Z.hasStatus("load") then
        Z.status("menu", "Lua reset for the save mods; vanilla continues the load")
        menu = { phase = "asked" }
    else
        Z.status("menu", "main menu reached")
        menu = { phase = "wait" }
    end
    Events.OnFETick.Add(menuTick)
end

local function onConnectFailed(message, detail)
    local cmd = Z._cmd
    if not cmd or cmd.role ~= "mpclient" or Z.hasStatus("ingame") then return end
    if menu then stopMenu() end
    C.fail("connection refused: " .. Z.oneLine(message) .. (detail and (" (" .. Z.oneLine(detail) .. ")") or ""), false)
end

-- ---------------------------------------------------------------- in game

local game = nil
local gameTick

gameTick = function()
    local g = game
    if not g then return end
    if g.phase == "quitwait" then
        if not Z.control("quit") then return end
        g.phase = "over"
        Events.OnTickEvenPaused.Remove(gameTick)
        C.finish(true)
        return
    end
    if g.phase == "over" then return end
    if Z.step(g.run) then
        if Z._cmd.control then
            g.phase = "quitwait"
            return
        end
        g.phase = "over"
        Events.OnTickEvenPaused.Remove(gameTick)
        C.finish(true)
    end
end

-- World gate of a client: local player, online id (mpclient), current square and its chunk in memory (the test
-- of BuildingDef.isFullyStreamedIn: IsoCell.getChunk(wx, wy) non-nil). Returns ready, detail.
function C.worldCheck()
    local p = getPlayer()
    if p == nil then return false, "no local player" end
    local x, y, z = math.floor(p:getX()), math.floor(p:getY()), math.floor(p:getZ())
    local where = x .. "," .. y .. "," .. z
    if Z._cmd.role == "mpclient" then
        local id = p:getOnlineID()
        if id == nil or id < 0 then return false, "no online id yet (player-connect not answered), at " .. where end
    end
    local sq = p:getCurrentSquare()
    if sq == nil then return false, "player square nil at " .. where end
    local cell = getCell()
    local wx, wy = math.floor(x / 8), math.floor(y / 8)
    if sq:getChunk() == nil or cell == nil or cell:getChunk(wx, wy) == nil then
        return false, "chunk " .. wx .. "," .. wy .. " of the player square not loaded, at " .. where
    end
    local around = 0
    for dx = -1, 1 do
        for dy = -1, 1 do
            if cell:getChunk(wx + dx, wy + dy) ~= nil then around = around + 1 end
        end
    end
    return true, "square " .. where .. ", chunk " .. wx .. "," .. wy .. " loaded (" .. around .. "/9 around)"
end

local function onGameStart()
    local cmd = Z.command()
    if not isClientRole(cmd) or game then return end
    if cmd.role == "mpclient" and Z.hasStatus("connect") and not Z.hasStatus("load") then
        Z.status("load", "saved multiplayer character resumed without creation")
    end
    if not Z.hasStatus("load") or Z.hasStatus("ingame") then return end
    Z.muteDebugger()
    local world = "?"
    pcall(function() world = tostring(getWorld():getWorld()) end)
    Z.status("ingame", "world " .. world)
    game = { phase = "run", run = Z.newRun("client", nil, { first = true, state = "world", check = C.worldCheck,
        timeoutMs = cmd.readyTimeoutMs, minFrames = cmd.readyFrames }) }
    Events.OnTickEvenPaused.Add(gameTick)
end

-- ---------------------------------------------------------------- subscriptions (once per Lua state)

if not C._subscribed and type(Events) == "table" then
    if Events.OnMainMenuEnter then Events.OnMainMenuEnter.Add(onMainMenuEnter) end
    if Events.OnGameStart then Events.OnGameStart.Add(onGameStart) end
    if Events.OnConnectFailed then Events.OnConnectFailed.Add(onConnectFailed) end
    C._subscribed = true
    -- MP: when the connection reset does not fire OnMainMenuEnter, the new Lua state goes on from here.
    local cmd = Z.command()
    if cmd and cmd.role == "mpclient" and Z.hasStatus("connect") and not Z.hasStatus("load")
        and not Z.hasStatus("ingame") then
        startJoined()
    end
end

return C
