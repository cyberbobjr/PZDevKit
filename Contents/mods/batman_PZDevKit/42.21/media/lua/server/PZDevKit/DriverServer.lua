--[[
DriverServer (ex-PZAT_Server) - dedicated server side of the generic automatic test driver (pz-autotest). Development mod only.
Does nothing without Zomboid/Lua/pz-autotest/command.txt with role=server in the server cache folder (format in
shared/PZDevKit/Driver.lua). A multiplayer client also loads media/lua/server: everything here checks isServer().

At OnServerStarted (end of GameServer.startServer, port open) the run (Driver.lua) is created and stepped on
OnTickEvenPaused (the only tick of an empty server paused by PauseEmpty), and the inbox of client commands opens
(Driver.lua: replayed to the subscribers of the start hook). With control=true it waits for "go" in control.txt (the
launcher writes it once every client is ready in the world and its hooks started), then, with players=N, for N
online players whose square is loaded on the server (status "players"). At the end result.txt is written; the
launcher then sends "quit" on the server console (stdin).
]]

require "PZDevKit/Driver"

local Z = PZDevKit.Driver
Z.Server = Z.Server or {}
local S = Z.Server

local function isServerSide()
    return type(isServer) == "function" and isServer() and true or false
end

local function tick()
    local r = S.run
    if not r then return end
    if Z.step(r) then
        S.run = nil
        Events.OnTickEvenPaused.Remove(tick)
    end
end

-- Gate after "go": players= online players, each with a square on the server (nil until its ServerMap cell is
-- loaded). Returns ready, detail.
function S.playersCheck()
    local want = Z._cmd.players
    local list = {}
    if type(getOnlinePlayers) == "function" then
        local list0 = getOnlinePlayers()
        for i = 0, list0:size() - 1 do list[#list + 1] = list0:get(i) end
    end
    if #list < want then return false, #list .. "/" .. want .. " player(s) online" end
    for _, p in ipairs(list) do
        if p:getCurrentSquare() == nil then
            return false, tostring(p:getUsername()) .. ": square not loaded on the server at "
                .. math.floor(p:getX()) .. "," .. math.floor(p:getY()) .. "," .. math.floor(p:getZ())
        end
    end
    return true, #list .. " player(s) online, squares loaded on the server"
end

function S.onServerStarted()
    if not isServerSide() or S.started then return end
    local cmd = Z.command()
    if not cmd then
        if Z.invalid then Z.writeResult("server", nil, 0, "command.txt refused: " .. Z.invalid) end
        return
    end
    if cmd.role ~= "server" then return end
    S.started = true
    Z.status("started", "server started")
    local gate = nil
    if cmd.players > 0 then
        gate = { first = false, state = "players", check = S.playersCheck, timeoutMs = cmd.playerWaitMs }
    end
    if cmd.run then Z.startInbox() end
    S.run = Z.newRun("server", nil, gate)
    Events.OnTickEvenPaused.Add(tick)
end

if not S._subscribed and type(Events) == "table" and Events.OnServerStarted then
    Events.OnServerStarted.Add(function() PZDevKit.Driver.Server.onServerStarted() end)
    S._subscribed = true
end

return S
