--[[
Driver (ex-PZAT_Core) - shared part of the generic automatic test driver (pzdev sp|server|mp, PZDevKit). Development
mod only, never published: the launcher copies it into a temporary cache folder. Without the command file below it
does nothing.

Files (all under Zomboid/Lua of the machine, i.e. <cachedir>/Lua, written by the launcher without BOM):
    pz-autotest/command.txt   command, one "key=value" per line ("#" comments and empty lines ignored), read only
        token=<letters/digits>    required, identifies the launch in the status file
        role=sp|server|mpclient   required
        save=<folder>             sp: Zomboid/Saves/<gameMode>/<folder>
        gameMode=Sandbox          sp: save mode (default Sandbox)
        connect=<host>:<port>     mpclient: server to join; user=<account>, password=<text>
        control=true|false        wait for "go" in control.txt before the run, and for "quit" after it (default false)
        run=true|false            false = nothing to run (second MP client, server without server hooks; default true)
        startDelaySec=<n>         real seconds between the game start and the run (default 5)
        readyTimeoutSec=<n>       client: real seconds to wait for the world (see "World gate" below; default 60)
        readyFrames=<n>           client: ticks after OnGameStart before the client can be ready (default 10)
        players=<n>               server: online players with a loaded square awaited after "go" (default 0 = none)
        playerWaitSec=<n>         server: real seconds to wait for them (default 90)
        timeoutSec=<n>            real seconds for done() once the run started (default 0 = no Lua limit)
        quit=true|false           client: quit to desktop at the end (default true)
        screenshot=true|false     client: takeScreenshot("pz-autotest-<token>.png") before quitting (default true)
        param.<name>=<text>       parameters given to the hooks (ctx.params[name]); an empty text is kept
    pz-autotest/hooks.lua     Lua chunk returning the hooks table (written by the launcher), read only
    pz-autotest/control.txt   words "go", "quit", one per line (written by the launcher), read only
    pz-autotest/status.txt    appended here: "<token> <state> <detail>"
    pz-autotest/result.txt    written here at the end:
        PZAT-RESULT ok=<bool> side=<client|server> durationMs=<n> [error=<text>] summary=<text>
        <lines returned by the result hook>
        PZAT-END

Hooks table (hooks.lua returns it; either plain functions, or "client" / "server" sub-tables of functions):
    start(ctx)  required: starts the run; returns true (or nothing), or false and a reason (an error refuses too)
    done(ctx)   optional: polled every POLL_MS until it returns true (absent = finished at once)
    result(ctx) optional: returns { ok = bool, summary = text, lines = { ... } } or ok, summary, lines
                (absent = ok true)
ctx = { side = "client" | "server", role, token, params = { name = text }, log = function(text),
        players = function() list of online IsoPlayer (server) or { getPlayer() } (client) end, Z = PZDevKit.Driver,
        ready = { ok = bool, detail = text } (result of the gate below, nil without gate) }

World gate (status "world" on a client, "players" on a server), then the run:
    client  from OnGameStart, every tick: local player, its online id (mpclient: OnGameStart comes before the
            player-connect answer), its square, the chunk of that square, and at least readyFrames ticks; then
            startDelaySec, then (control=true) status "ready" and the wait for "go". Past readyTimeoutSec the run
            goes on with a WARNING line and a status detail starting with "timeout".
    server  after "go": players= online players, each with a non-nil square on the server (ServerMap cell
            loaded), within playerWaitSec (same WARNING / "timeout" otherwise).
Server inbox: from OnServerStarted until the start hook ran, client commands (OnClientCommand) are kept; the
    OnClientCommand subscribers added by the start hook receive them right after it, in their order of arrival
    (a client whose hooks started before the server's loses nothing). Subscribers added later receive none.
]]

PZDevKit = PZDevKit or {}
PZDevKit.Driver = PZDevKit.Driver or {}
local Z = PZDevKit.Driver

Z.DIR = "pz-autotest/"
Z.COMMAND_FILE = Z.DIR .. "command.txt"
Z.HOOKS_FILE = Z.DIR .. "hooks.lua"
Z.CONTROL_FILE = Z.DIR .. "control.txt"
Z.STATUS_FILE = Z.DIR .. "status.txt"
Z.RESULT_FILE = Z.DIR .. "result.txt"
Z.MAX_COMMAND_LINES = 200
Z.MAX_HOOK_LINES = 20000
Z.MAX_RESULT_LINES = 2000
Z.POLL_MS = 250
Z.CONTROL_POLL_MS = 1000
Z.MAX_INBOX = 1000

function Z.log(msg)
    print("[PZAT] " .. tostring(msg))
end

function Z.nowMs()
    if type(getTimestampMs) == "function" then
        local ok, v = pcall(getTimestampMs)
        if ok and type(v) == "number" then return v end
    end
    return 0
end

function Z.oneLine(s, maxLen)
    s = string.gsub(tostring(s), "[\r\n]+", " / ")
    maxLen = maxLen or 400
    if #s > maxLen then s = string.sub(s, 1, maxLen - 3) .. "..." end
    return s
end

function Z.trim(s)
    s = string.gsub(tostring(s), "^[ \t]+", "")
    s = string.gsub(s, "[ \t\r]+$", "")
    return s
end

-- Comma-separated list, items trimmed, empty items dropped. nil gives nil.
function Z.split(text)
    if text == nil then return nil end
    local list = {}
    for item in string.gmatch(tostring(text), "[^,]+") do
        item = Z.trim(item)
        if item ~= "" then list[#list + 1] = item end
    end
    return list
end

-- Lines of a file of Zomboid/Lua (read only), or nil when absent or unreadable.
function Z.readLines(path, maxLines)
    if type(getFileReader) ~= "function" then return nil end
    local okOpen, reader = pcall(getFileReader, path, false)
    if not okOpen or reader == nil then return nil end
    local lines, limit = {}, maxLines or Z.MAX_COMMAND_LINES
    local okRead = pcall(function()
        while #lines < limit do
            local line = reader:readLine()
            if line == nil then break end
            lines[#lines + 1] = tostring(line)
        end
    end)
    pcall(function() reader:close() end)
    if not okRead then return nil end
    return lines
end

-- True when the file exists and, if marker is given, its last non-empty line equals marker.
function Z.fileEndsWith(path, marker)
    local lines = Z.readLines(path, Z.MAX_RESULT_LINES * 10)
    if not lines then return false end
    if marker == nil then return true end
    for i = #lines, 1, -1 do
        local line = Z.trim(lines[i])
        if line ~= "" then return line == marker end
    end
    return false
end

function Z.writeLines(path, lines, append)
    if type(getFileWriter) ~= "function" then return false, "getFileWriter missing" end
    local okOpen, writer = pcall(getFileWriter, path, true, append and true or false)
    if not okOpen or writer == nil then return false, "cannot open " .. path end
    local okWrite, err = pcall(function()
        for _, line in ipairs(lines) do writer:writeln(line) end
    end)
    pcall(function() writer:close() end)
    if not okWrite then return false, Z.oneLine(err) end
    return true
end

-- ---------------------------------------------------------------- command

local function isTrue(v, default)
    if v == nil then return default end
    return v == "true"
end

-- Parses the command lines. Returns the command table, or nil and a reason.
function Z.parse(lines)
    local raw, params = {}, {}
    for i, text in ipairs(lines) do
        local line = Z.trim(text)
        if line ~= "" and string.sub(line, 1, 1) ~= "#" then
            local key, value = string.match(line, "^([%w_%.]+)=(.*)$")
            if not key then return nil, "line " .. i .. ": expected key=value" end
            local name = string.match(key, "^param%.([%w_]+)$")
            if name then
                params[name] = Z.trim(value)
            elseif string.find(key, "%.") then
                return nil, "line " .. i .. ": unknown key " .. key
            else
                raw[key] = Z.trim(value)
            end
        end
    end
    if not raw.token or not string.match(raw.token, "^[%w]+$") then return nil, "token missing or not alphanumeric" end
    local role = raw.role
    if role ~= "sp" and role ~= "server" and role ~= "mpclient" then return nil, "role must be sp, server or mpclient" end
    local cmd = { token = raw.token, role = role, params = params, save = raw.save, gameMode = raw.gameMode or "Sandbox",
        control = isTrue(raw.control, false), run = isTrue(raw.run, true),
        startDelayMs = (tonumber(raw.startDelaySec or "5") or 5) * 1000,
        timeoutMs = (tonumber(raw.timeoutSec or "0") or 0) * 1000,
        quit = isTrue(raw.quit, true), screenshot = isTrue(raw.screenshot, true),
        readyTimeoutMs = (tonumber(raw.readyTimeoutSec or "60") or 60) * 1000,
        readyFrames = tonumber(raw.readyFrames or "10") or 10,
        players = tonumber(raw.players or "0") or 0,
        playerWaitMs = (tonumber(raw.playerWaitSec or "90") or 90) * 1000,
        user = raw.user, password = raw.password or "" }
    if role == "sp" and (cmd.save == nil or cmd.save == "") then return nil, "save= is needed with role=sp" end
    if role == "mpclient" then
        if not raw.connect or not string.match(raw.connect, "^[^:%s]+:%d+$") then
            return nil, "connect=<host>:<port> is needed with role=mpclient"
        end
        if not cmd.user or cmd.user == "" then return nil, "user= is needed with role=mpclient" end
        cmd.host, cmd.port = string.match(raw.connect, "^([^:]+):(%d+)$")
    end
    return cmd
end

-- The command of this Lua state (read once). nil when absent or invalid (Z.invalid then holds the reason).
function Z.command()
    if Z._cmdRead then return Z._cmd end
    Z._cmdRead = true
    local lines = Z.readLines(Z.COMMAND_FILE)
    if not lines then return nil end
    local cmd, why = Z.parse(lines)
    if not cmd then
        Z.log("ERROR: " .. Z.COMMAND_FILE .. " refused: " .. why)
        Z.invalid = why
        return nil
    end
    Z._cmd = cmd
    return cmd
end

function Z.status(state, detail)
    local cmd = Z._cmd
    local line = (cmd and cmd.token or "-") .. " " .. state .. " " .. Z.oneLine(detail or "", 300)
    Z.log("status " .. line)
    Z.writeLines(Z.STATUS_FILE, { line }, true)
end

-- True when the status file already holds this state for the token (survives a Lua reset).
function Z.hasStatus(state)
    local cmd = Z._cmd
    if not cmd then return false end
    local prefix = cmd.token .. " " .. state .. " "
    for _, line in ipairs(Z.readLines(Z.STATUS_FILE, 5000) or {}) do
        if string.sub(line .. " ", 1, #prefix) == prefix then return true end
    end
    return false
end

-- True when control.txt holds the word on a line of its own (file read at most once per CONTROL_POLL_MS).
function Z.control(word)
    local now = Z.nowMs()
    if Z._controlAt == nil or now >= Z._controlAt then
        Z._controlAt = now + Z.CONTROL_POLL_MS
        local words = {}
        for _, line in ipairs(Z.readLines(Z.CONTROL_FILE) or {}) do words[Z.trim(line)] = true end
        Z._controlWords = words
    end
    return (Z._controlWords or {})[word] == true
end

function Z.muteDebugger()
    if UIManager ~= nil and UIManager.setShowLuaDebuggerOnError ~= nil then
        pcall(UIManager.setShowLuaDebuggerOnError, false)
    end
end

-- ---------------------------------------------------------------- hooks

-- Loads hooks.lua and returns the functions of the side, or nil and a reason.
function Z.loadHooks(side)
    local lines = Z.readLines(Z.HOOKS_FILE, Z.MAX_HOOK_LINES)
    if not lines then return nil, Z.HOOKS_FILE .. " missing or unreadable" end
    if type(loadstring) ~= "function" then return nil, "loadstring missing" end
    local chunk, err = loadstring(table.concat(lines, "\n"), "=" .. Z.HOOKS_FILE)
    if not chunk then return nil, "hooks do not compile: " .. Z.oneLine(err) end
    local ok, hooks = pcall(chunk)
    if not ok then return nil, "hooks failed to load: " .. Z.oneLine(hooks) end
    if type(hooks) ~= "table" then return nil, "hooks.lua must return a table" end
    local own = hooks[side]
    if type(own) == "table" then hooks = own end
    if type(hooks.start) ~= "function" then return nil, "no start hook for side " .. side end
    return hooks
end

local function players(side)
    local out = {}
    if side == "server" then
        if type(getOnlinePlayers) == "function" then
            pcall(function()
                local list = getOnlinePlayers()
                for i = 0, list:size() - 1 do out[#out + 1] = list:get(i) end
            end)
        end
    elseif type(getPlayer) == "function" then
        local ok, p = pcall(getPlayer)
        if ok and p ~= nil then out[1] = p end
    end
    return out
end

-- Normalises what the result hook returned.
function Z.normalise(a, b, c)
    if type(a) == "table" then
        return { ok = a.ok and true or false, summary = a.summary, lines = a.lines }
    end
    return { ok = a and true or false, summary = b, lines = c }
end

function Z.resultLine(side, res, durationMs, err)
    local ok = res and res.ok and err == nil
    local line = "PZAT-RESULT ok=" .. tostring(ok and true or false) .. " side=" .. side
        .. " durationMs=" .. math.floor((durationMs or 0) + 0.5)
    if err then line = line .. " error=" .. Z.oneLine(err, 300) end
    line = line .. " summary=" .. Z.oneLine(res and res.summary or "", 300)
    return line
end

function Z.writeResult(side, res, durationMs, err)
    local out = { Z.resultLine(side, res, durationMs, err) }
    if res and type(res.lines) == "table" then
        for _, line in ipairs(res.lines) do
            if #out > Z.MAX_RESULT_LINES then
                out[#out + 1] = "(result truncated)"
                break
            end
            out[#out + 1] = Z.oneLine(line, 1000)
        end
    end
    out[#out + 1] = "PZAT-END"
    local ok, why = Z.writeLines(Z.RESULT_FILE, out)
    if not ok then Z.log("ERROR: result not written: " .. tostring(why)) end
    Z.status("done", out[1])
    return out[1]
end

-- ---------------------------------------------------------------- run engine (client and server)

-- ---------------------------------------------------------------- server inbox

-- Keeps the client commands received before the start hook (server only; Z.stopInbox ends it).
function Z.startInbox()
    if Z.inbox or type(Events) ~= "table" or not Events.OnClientCommand then return end
    Z.inbox = {}
    Z.inboxListener = function(module, command, player, args)
        local inbox = Z.inbox
        if inbox and #inbox < Z.MAX_INBOX then inbox[#inbox + 1] = { module, command, player, args } end
    end
    Events.OnClientCommand.Add(Z.inboxListener)
end

-- Ends the inbox and gives its commands to the subscribers in handlers (nil = drop them).
function Z.stopInbox(handlers)
    local inbox = Z.inbox
    if not inbox then return end
    Z.inbox = nil
    if Z.inboxListener then pcall(Events.OnClientCommand.Remove, Z.inboxListener) end
    Z.inboxListener = nil
    if #inbox == 0 then return end
    if not handlers or #handlers == 0 then
        Z.log(#inbox .. " client command(s) received before the start hook, no OnClientCommand subscriber added"
            .. " by it: not replayed")
        return
    end
    for _, e in ipairs(inbox) do
        for _, f in ipairs(handlers) do
            local ok, err = pcall(f, e[1], e[2], e[3], e[4])
            if not ok then
                Z.log("ERROR: replayed client command " .. tostring(e[1]) .. "/" .. tostring(e[2]) .. ": "
                    .. Z.oneLine(err))
            end
        end
    end
    Z.log("replayed " .. #inbox .. " client command(s) received before the start hook to " .. #handlers
        .. " OnClientCommand subscriber(s) of the hooks")
end

-- Calls the start hook; while the inbox is open, records the OnClientCommand subscribers it adds.
local function callStart(hooks, ctx)
    local ev = Z.inbox and type(Events) == "table" and Events.OnClientCommand or nil
    if not ev then return pcall(hooks.start, ctx) end
    local added, add = {}, ev.Add
    ev.Add = function(f, ...)
        added[#added + 1] = f
        return add(f, ...)
    end
    local ok, a, b = pcall(hooks.start, ctx)
    ev.Add = add
    Z.stopInbox((ok and a ~= false) and added or nil)
    return ok, a, b
end

-- Creates a run; Z.step(run) is then called on every tick until it returns true (finished).
-- onEnd(run) is called once, after the result file is written.
-- gate (optional): { first = bool (true: before the start delay; false: after "go"), state = status name,
--     check = function() returns ready, detail end, timeoutMs, minFrames }
function Z.newRun(side, onEnd, gate)
    local cmd = Z._cmd
    local run = { side = side, phase = "wait", at = Z.nowMs() + cmd.startDelayMs, onEnd = onEnd, gate = gate,
        ctx = { side = side, role = cmd.role, token = cmd.token, params = cmd.params, log = Z.log,
            players = function() return players(side) end, Z = Z } }
    if gate then
        gate.frames, gate.timeoutMs, gate.minFrames = 0, gate.timeoutMs or 60000, gate.minFrames or 1
        if gate.first then run.phase = "gate" end
    end
    return run
end

-- One tick of the gate. Returns true once it is passed (ready, or timed out with a warning).
local function gateStep(run, now)
    local g = run.gate
    g.frames = g.frames + 1
    if g.since == nil then g.since = now end
    local ok, ready, detail = pcall(g.check)
    if not ok then ready, detail = false, "check error: " .. Z.oneLine(ready) end
    detail = Z.oneLine(detail or "", 240)
    local waited = now - g.since
    if ready and g.frames >= g.minFrames then
        g.done = true
        run.ctx.ready = { ok = true, detail = detail }
        Z.status(g.state, "ok after " .. math.floor(waited) .. " ms, " .. g.frames .. " ticks: " .. detail)
        return true
    end
    if waited >= g.timeoutMs then
        g.done = true
        if ready then detail = "ready but only " .. g.frames .. " ticks" end
        run.ctx.ready = { ok = false, detail = detail }
        Z.log("WARNING: " .. g.state .. " not ready after " .. math.floor(g.timeoutMs / 1000)
            .. " s, the run goes on: " .. detail)
        Z.status(g.state, "timeout after " .. math.floor(g.timeoutMs / 1000) .. " s, " .. g.frames .. " ticks: "
            .. detail)
        return true
    end
    return false
end

local function finishRun(run, res, err)
    run.phase = "end"
    Z.writeResult(run.side, res, run.startedAt and (Z.nowMs() - run.startedAt) or 0, err)
    if run.onEnd then run.onEnd(run) end
end

local function begin(run)
    local cmd = Z._cmd
    if not cmd.run then
        Z.stopInbox(nil)
        Z.status("idle", "nothing to run")
        run.phase = "idle"
        if run.onEnd then run.onEnd(run) end
        return
    end
    local hooks, why = Z.loadHooks(run.side)
    if not hooks then
        Z.stopInbox(nil)
        run.startedAt = Z.nowMs()
        finishRun(run, nil, why)
        return
    end
    run.hooks = hooks
    run.startedAt = Z.nowMs()
    local ok, started, reason = callStart(hooks, run.ctx)
    if not ok then
        finishRun(run, nil, "start hook error: " .. Z.oneLine(started))
        return
    end
    if started == false then
        finishRun(run, nil, "run not started: " .. Z.oneLine(reason or "start returned false"))
        return
    end
    Z.status("run", "started")
    run.phase = "run"
    run.nextPoll = Z.nowMs()
end

-- After the start delay (and "go"): the gate placed after "go", then the start hook.
local function beginAfterGate(run)
    if run.gate and not run.gate.done then
        run.phase = "gate"
        return
    end
    begin(run)
end

-- One step of the run. Returns true when it is over (result written, or idle).
function Z.step(run)
    local now = Z.nowMs()
    if run.phase == "gate" then
        if not gateStep(run, now) then return false end
        if run.gate.first then
            run.phase = "wait"
            return false
        end
        begin(run)
    elseif run.phase == "wait" then
        if now < run.at then return false end
        if Z._cmd.control then
            run.phase = "go"
            Z.status("ready", "waiting for go")
            return false
        end
        beginAfterGate(run)
    elseif run.phase == "go" then
        if not Z.control("go") then return false end
        Z.status("go", "control file")
        beginAfterGate(run)
    elseif run.phase == "run" then
        if now < run.nextPoll then return false end
        run.nextPoll = now + Z.POLL_MS
        local hooks = run.hooks
        if hooks.done then
            local ok, finished = pcall(hooks.done, run.ctx)
            if not ok then
                finishRun(run, nil, "done hook error: " .. Z.oneLine(finished))
                return true
            end
            if not finished then
                local limit = Z._cmd.timeoutMs
                if limit > 0 and now - run.startedAt >= limit then
                    finishRun(run, nil, "no end after " .. math.floor(limit / 1000) .. " s (timeoutSec)")
                    return true
                end
                return false
            end
        end
        local res = { ok = true, summary = "", lines = {} }
        if hooks.result then
            local ok, a, b, c = pcall(hooks.result, run.ctx)
            if not ok then
                finishRun(run, nil, "result hook error: " .. Z.oneLine(a))
                return true
            end
            res = Z.normalise(a, b, c)
        end
        finishRun(run, res, nil)
    end
    return run.phase == "end" or run.phase == "idle"
end

return Z
