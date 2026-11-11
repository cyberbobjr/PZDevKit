--[[
Live - live Lua channel of PZDevKit (DEV-ONLY). Active only in a game started with -debug; does nothing without its
command file. Used by `pzdev lua|repl|attach` on a cached test game or on the real game (attached mode).

Command  Zomboid/Lua/pzdev/cmd.lua, written by the command line (temporary file, then renamed):
             --pzdev 1 id=<n> [shot] [timeoutMs=<n>]
             <Lua chunk; "return" optional>
Answer   Zomboid/Lua/pzdev/out.txt, written here:
             --pzdev 1 id=<n> status=ok|error|compile-error durationMs=<n>
             -> <each returned value, one line, 4 KiB max, tables 2 levels deep>
             info <each PZDevKit.info line of the command>
             error <message>               (status other than ok)
             shot pzdev_<n>.png            (when "shot" was asked; file in Zomboid/Screenshots)
             --end
The file is read every 400 ms on OnTickEvenPaused (also while paused). Each id runs once: the last answered id is
read back from out.txt after a Lua reload. The chunk runs in one frame inside pcall, with the Lua debugger popup
muted for that call only (the user's setting is restored); the game goes on after an error.
]]

require "PZDevKit/Driver"

PZDevKit = PZDevKit or {}
PZDevKit.Live = PZDevKit.Live or {}
local L = PZDevKit.Live
local Z = PZDevKit.Driver

L.DIR = "pzdev/"
L.COMMAND_FILE = L.DIR .. "cmd.lua"
L.ANSWER_FILE = L.DIR .. "out.txt"
L.POLL_MS = 400
L.MAX_LINES = 20000
L.MAX_VALUE = 4096
L.MAX_DEPTH = 2

local lastId = nil
local loaded = false
local lastPoll = 0
local capture = nil

-- Prints a line; during a live command the line is also sent back in the answer ("info ...").
function PZDevKit.info(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
    local line = Z.oneLine(table.concat(parts, " "), L.MAX_VALUE)
    print("[PZDevKit] info " .. line)
    if capture then capture[#capture + 1] = line end
end

local function keyOrder(a, b)
    local ta, tb = type(a), type(b)
    if ta ~= tb then return ta == "number" end
    if ta == "number" then return a < b end
    return tostring(a) < tostring(b)
end

local function serialize(v, depth, quote)
    local t = type(v)
    if t == "string" then
        if quote then return string.format("%q", v) end
        return v
    end
    if t ~= "table" then return tostring(v) end
    if depth > L.MAX_DEPTH then return "{...}" end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, keyOrder)
    local parts = {}
    for _, k in ipairs(keys) do
        parts[#parts + 1] = tostring(k) .. "=" .. serialize(v[k], depth + 1, true)
        if #parts > 200 then parts[#parts + 1] = "..."; break end
    end
    return "{" .. table.concat(parts, ", ") .. "}"
end

function L.format(v)
    local ok, s = pcall(serialize, v, 1, false)
    if not ok then s = "<" .. type(v) .. ": " .. tostring(s) .. ">" end
    return Z.oneLine(s, L.MAX_VALUE)
end

local function header(lines)
    local first = lines and lines[1]
    if not first then return nil end
    local id, rest = string.match(first, "^%-%-pzdev 1 id=(%d+)(.*)$")
    return id, rest
end

-- Count and table of every value (nil included): Kahlua has no table.maxn.
local function pack(...)
    return select("#", ...), { ... }
end

local function run(code)
    local out, status = {}, "ok"
    local f, err = loadstring(code, "=pzdev")
    if not f then
        return "compile-error", { "error " .. Z.oneLine(err, L.MAX_VALUE) }
    end
    local show = nil
    if UIManager ~= nil and UIManager.isShowLuaDebuggerOnError ~= nil then
        local okGet, v = pcall(UIManager.isShowLuaDebuggerOnError)
        if okGet then show = v end
    end
    Z.muteDebugger()
    local n, res = pack(pcall(f))
    if show ~= nil then pcall(UIManager.setShowLuaDebuggerOnError, show) end
    if not res[1] then
        status = "error"
        out[#out + 1] = "error " .. Z.oneLine(res[2], L.MAX_VALUE)
    else
        for i = 2, n do out[#out + 1] = "-> " .. L.format(res[i]) end
    end
    return status, out
end

function L.tick()
    local now = Z.nowMs()
    if now - lastPoll < L.POLL_MS then return end
    lastPoll = now
    if not loaded then
        loaded = true
        lastId = header(Z.readLines(L.ANSWER_FILE, 1))
    end
    local lines = Z.readLines(L.COMMAND_FILE, L.MAX_LINES)
    local id, rest = header(lines)
    if not id or id == lastId then return end
    lastId = id
    local shot = string.find(" " .. rest .. " ", " shot ", 1, true) ~= nil
    local code = table.concat(lines, "\n", 2)
    capture = {}
    local started = Z.nowMs()
    local status, out = run(code)
    local infos = capture
    capture = nil
    local answer = { "--pzdev 1 id=" .. id .. " status=" .. status .. " durationMs=" .. tostring(Z.nowMs() - started) }
    for _, line in ipairs(out) do answer[#answer + 1] = line end
    for _, line in ipairs(infos) do answer[#answer + 1] = "info " .. line end
    if shot then
        local name = "pzdev_" .. id .. ".png"
        pcall(takeScreenshot, name)
        answer[#answer + 1] = "shot " .. name
    end
    answer[#answer + 1] = "--end"
    local ok, err = Z.writeLines(L.ANSWER_FILE, answer, false)
    if not ok then print("[PZDevKit] live: cannot write the answer: " .. tostring(err)) end
end

if type(isDebugEnabled) == "function" and isDebugEnabled() then
    Events.OnTickEvenPaused.Add(L.tick)
end

return L
