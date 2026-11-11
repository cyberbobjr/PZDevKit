--[[
Scenario - scenario engine of PZDevKit (DEV-ONLY), formerly PZPuppeteer (PZPuppet_Core.lua). Console
scenarios and campaigns: one local player, real actions, explicit launches, reports.
Kept contracts (read by the collectors of other projects): log prefix "[PZPuppet]", report header
"PZPuppet 0.1.0", files under Zomboid/Lua/PZPuppet/ (scenarios/, reports/, last-report.txt, batch-ack.txt).
The old global PZPuppet no longer exists (plan 001 step 10): call PZDevKit.Scenario.
]]
PZDevKit = PZDevKit or {}
local P = PZDevKit.Scenario or {}
PZDevKit.Scenario = P
P.VERSION = "0.1.0"
P.DEFAULT_TIMEOUT = 30
P.MAX_TICK_SECONDS = 0.25
P.factories = P.factories or {}

-- Lua reload: release the previous runner before installing another callback.
if P.stopBatch then P.stopBatch("Lua reload") end
if P.stop then P.stop("Lua reload") end
local Scenario = {}
Scenario.__index = Scenario
local active
local onTick
local batch
local onBatchTick
local batchLaunching = false
local batchLoading = false
P.runSequence = P.runSequence or 0

local function token()
    P.runSequence = P.runSequence + 1
    return string.format("%.0f-%d",getTimestampMs(),P.runSequence)
end
local function onServerCommand(module,command,args)
    if not active then return end
    local context=active.context
    context.eventSequence=context.eventSequence+1
    context.serverCommands[#context.serverCommands+1]={module=module,command=command,args=args,
        sequence=context.eventSequence}
    if #context.serverCommands>64 then table.remove(context.serverCommands,1) end
end

local function positive(value, name, allowZero)
    assert(type(value) == "number" and value == value and value < math.huge
        and (value > 0 or (allowZero and value == 0)), name .. " must be finite and positive")
    return value
end

local function log(message)
    print("[PZPuppet] " .. tostring(message))
end

local function snapshot(run)
    local player = run.context.player
    return { x=player:getX(), y=player:getY(), z=player:getZ(),
        queued=P.Game and P.Game.queueSize(player) or 0 }
end

local function writeReportFile(report,path)
    local writer = getFileWriter(path, true, false)
    assert(writer,"Cannot write " .. path)
    local ok,err=pcall(function()
        writer:write("PZPuppet " .. P.VERSION .. "\n" .. report.name .. " : " .. report.status .. "\n")
        writer:write(string.format("Active time: %.3fs\n", report.duration))
        writer:write("Run token: " .. report.runToken .. "\n")
        writer:write("Persistent report: " .. report.persistentReport .. "\n")
        writer:write("Player index: " .. report.playerIndex .. "\n")
        writer:write("Manual stop: " .. tostring(report.manualStop) .. "\n")
        if report.batchToken then
            writer:write("Batch token: " .. report.batchToken .. "\n")
            writer:write("Batch index: " .. report.batchIndex .. "\n")
            writer:write("Scenario path: " .. report.scenarioPath .. "\n")
        end
        for i, step in ipairs(report.steps) do
            writer:write(string.format("%d. %s | %s | %.3fs | %s\n", i, step.label, step.status,
                step.duration or 0, step.reason or ""))
        end
        if report.reason then writer:write("Reason: " .. report.reason .. "\n") end
        local s = report.position
        writer:write(string.format("Position: %.3f %.3f %.3f | queued: %d\n", s.x,s.y,s.z,s.queued))
    end)
    local closed,closeError=pcall(function() writer:close() end)
    if not ok then error(err) end
    if not closed then error(closeError) end
end

local function writeReport(report)
    assert(getFileWriter,"getFileWriter is unavailable")
    writeReportFile(report,report.persistentReport)
    writeReportFile(report,"PZPuppet/last-report.txt")
    report.persisted = true
end

local function finish(status, reason)
    local run = active
    if not run then return end
    active = nil
    Events.OnTick.Remove(onTick)
    Events.OnServerCommand.Remove(onServerCommand)
    local row = run.report.steps[run.index]
    if row and row.status == "running" then
        row.status, row.reason, row.duration = status, reason, run.elapsed-run.stepStarted
    end
    -- The game adapter only cancels a queue explicitly claimed by a scenario action.
    if run.context.queueOwned and P.Game then
        local ok, err = pcall(P.Game.cancel, run.context)
        if not ok then
            log("Cleanup error: " .. tostring(err))
            if status=="passed" then status,reason="failed","Cleanup: " .. tostring(err) end
        end
    end
    for i=#run.cleanups,1,-1 do
        local ok,err=pcall(run.cleanups[i],run.context)
        if not ok then
            log("Scenario cleanup error: " .. tostring(err))
            if status=="passed" then status,reason="failed","Cleanup: " .. tostring(err) end
        end
    end
    run.report.status, run.report.reason, run.report.duration = status, reason, run.elapsed
    run.report.position = snapshot(run)
    P.lastReport = run.report
    if run.writeReport then
        local ok, err = pcall(writeReport, run.report)
        if not ok then
            run.report.persisted = false
            log("Report write error: " .. tostring(err))
            if status=="passed" then
                status,reason="failed","Report write: " .. tostring(err)
                run.report.status,run.report.reason=status,reason
            end
        end
    end
    log(run.report.name .. " : " .. status .. (reason and (" | " .. reason) or ""))
end

onTick = function()
    local run = active
    if not run then return end
    local now = getTimestampMs()
    local dt = math.max(0, math.min((now-run.lastTick)/1000, P.MAX_TICK_SECONDS))
    run.lastTick = now
    -- OnTick does not run during a normal solo pause. Also exclude speed-zero ticks.
    if getGameSpeed and getGameSpeed() == 0 then return end
    run.elapsed = run.elapsed + dt
    local ok, err = pcall(function()
        local context = run.context
        if P.Game then
            local reason = P.Game.interrupted(context, run.manualStop)
            if reason then finish("cancelled", reason) return end
        end
        local step = run.steps[run.index]
        if not step then finish("passed") return end
        if not run.stepStarted then
            run.stepStarted = run.elapsed
            run.report.steps[run.index].status = "running"
            context.stepData = {}
            log(string.format("%s [%d/%d] %s", run.report.name,run.index,#run.steps,step.label))
            if step.start then step.start(context, context.stepData) end
            -- A user callback may stop the scenario itself.
            if active ~= run then return end
        end
        local passed, failure = step.poll(context, context.stepData)
        if active ~= run then return end
        -- Expected action failures are outcomes, not debugger-breaking Lua errors.
        if failure ~= nil then finish("failed", tostring(failure)); return end
        if passed == true then
            local row = run.report.steps[run.index]
            row.status, row.duration = "passed", run.elapsed-run.stepStarted
            run.index, run.stepStarted = run.index+1, nil
            if run.index > #run.steps then finish("passed") end
        elseif run.elapsed-run.stepStarted >= step.timeout then
            finish("failed", "Timeout: " .. step.label)
        end
    end)
    if not ok and active == run then finish("failed", tostring(err)) end
end

function P.scenario(name)
    assert(type(name) == "string" and name ~= "", "Scenario needs a name")
    return setmetatable({name=name, steps={},cleanups={}}, Scenario)
end

function P.register(name,factory,replace)
    assert(type(name)=="string" and name~="" and type(factory)=="function", "register needs a name and factory(params)")
    assert(not P.factories[name] or replace==true, "Scenario already registered: " .. name)
    P.factories[name]=factory
end

function P.listScenarios()
    local names={}
    for name in pairs(P.factories) do names[#names+1]=name end
    table.sort(names)
    return names
end

local function built(factory,params)
    local scenario=factory(params or {})
    assert(type(scenario)=="table" and getmetatable(scenario)==Scenario, "Factory must return PZDevKit.Scenario.scenario(...)")
    return scenario
end

function P.run(name,options,params)
    assert(isDebugEnabled() and not active and not batch, "Use debug mode with no scenario or batch already running")
    assert(P.factories[name], "Unknown registered scenario: " .. tostring(name))
    return built(P.factories[name],params):run(options)
end

-- Explicit hot-load from the game's user Lua directory, independently of require's cache.
local function loadFactory(path)
    assert(isDebugEnabled() and not active, "Use debug mode with no scenario already running")
    assert(type(path)=="string" and path:match("^[%w_/-]+%.lua$") and not path:find("..",1,true)
        and path:sub(1,1)~="/", "Use a relative .lua path below PZPuppet/scenarios")
    local relative="PZPuppet/scenarios/" .. path
    local reader=getFileReader(relative,false)
    assert(reader,"Scenario file not found: " .. relative)
    local lines,size={},0
    while true do
        local line=reader:readLine()
        if not line then break end
        size=size+#line+1
        if size>262144 then reader:close(); error("Scenario file exceeds 256 KiB") end
        lines[#lines+1]=line
    end
    reader:close()
    local source=table.concat(lines,"\n")
    if source:sub(1,3)=="\239\187\191" then source=source:sub(4) end
    local chunk,err=loadstring(source,"@" .. relative)
    assert(chunk,"Scenario syntax: " .. tostring(err))
    local factory=chunk()
    assert(type(factory)=="function", "Scenario file must return function(params) ... end")
    return factory
end

local function loadScenario(path,params)
    return built(loadFactory(path),params)
end

function P.loadScenario(path,params)
    assert(not batch or batchLoading,"A batch is running; PZDevKit.Scenario.stopBatch() to cancel it")
    return loadScenario(path,params)
end

function P.runFile(path,options,params)
    return P.loadScenario(path,params):run(options)
end

function Scenario:step(label, definition)
    assert(not self.used, "Create a new scenario to run again")
    assert(type(label) == "string" and label ~= "", "Step needs a label")
    assert(type(definition) == "table" and type(definition.poll) == "function", "Step needs poll(context, data)")
    assert(definition.start == nil or type(definition.start) == "function", "start must be a function")
    self.steps[#self.steps+1] = {label=label, start=definition.start, poll=definition.poll,
        timeout=positive(definition.timeout or P.DEFAULT_TIMEOUT,"timeout")}
    return self
end

function Scenario:call(label, callback)
    assert(type(callback) == "function", "call needs a function")
    return self:step(label, {start=callback, poll=function() return true end})
end

function Scenario:check(label, predicate)
    assert(type(predicate) == "function", "check needs a predicate")
    return self:step(label, {poll=function(context)
        local result, reason = predicate(context)
        if result ~= true then
            -- An unmet expectation is a test result, not a Lua runtime exception.
            -- Kahlua's debugger stops before pcall can catch an assert failure.
            finish("failed", reason or ("Assertion failed: " .. label))
            return false
        end
        return true
    end})
end

function Scenario:wait(seconds)
    positive(seconds, "wait", true)
    return self:step("Wait " .. seconds .. "s", {
        start=function(_, data) data.deadline=active.elapsed+seconds end,
        poll=function(_, data) return active.elapsed >= data.deadline end,
        timeout=seconds+P.DEFAULT_TIMEOUT})
end

function Scenario:await(label, predicate, timeout)
    assert(type(predicate) == "function", "await needs a predicate")
    return self:step(label, {poll=predicate, timeout=timeout})
end

-- Listener is installed at run start, so a synchronous solo reply is not lost.
function Scenario:awaitServerCommand(module,command,predicate,timeout)
    assert(type(module)=="string" and type(command)=="string", "Expected module and command names")
    assert(predicate==nil or type(predicate)=="function", "Expected an optional command predicate")
    return self:await(module .. ":" .. command,function(context)
        for _,entry in ipairs(context.serverCommands) do
            if entry.sequence>context.serverCursor and entry.module==module and entry.command==command
                and (not predicate or predicate(context,entry.args)==true) then
                context.serverCursor=entry.sequence
                context.vars.lastCommand=entry.args
                return true
            end
        end
        return false
    end,timeout)
end

function Scenario:finally(callback)
    assert(not self.used and type(callback)=="function", "finally needs a callback before run")
    self.cleanups[#self.cleanups+1]=callback
    return self
end

-- Explicit bridge for mods which dispatch directly in solo instead of a network event.
function P.captureServerCommand(module,command,args)
    onServerCommand(module,command,args)
end

function Scenario:run(options)
    options = options or {}
    assert(not self.used, "Create a new scenario to run again")
    assert(not active, "A scenario is already running; PZDevKit.Scenario.stop() to cancel it")
    assert(not batch or batchLaunching,"A batch is running; PZDevKit.Scenario.stopBatch() to cancel it")
    assert(isDebugEnabled(), "Run scenarios in -debug mode")
    assert(#self.steps > 0, "Scenario has no steps")
    local index = options.playerIndex or 0
    assert(type(index) == "number" and index >= 0 and index <= 3 and index == math.floor(index),
        "playerIndex must be 0..3")
    local player = getSpecificPlayer(index)
    assert(player and not player:isDead(), "No living local player at this index")
    assert(not P.Game or P.Game.queueSize(player) == 0, "Player action queue is busy")
    self.used = true
    local runToken=token()
    local report = {name=self.name, status="running", steps={},runToken=runToken,
        persistentReport="PZPuppet/reports/" .. runToken .. ".txt",
        playerIndex=index,manualStop=options.manualStop~=false}
    if batch then
        report.batchToken,report.batchIndex= batch.token,batch.index
        report.scenarioPath=batch.entries[batch.index].path
    end
    for i, step in ipairs(self.steps) do report.steps[i]={label=step.label,status="pending"} end
    local context = {player=player, playerIndex=index, vars={}, queueOwned=false,
        serverCommands={}, serverCursor=0, eventSequence=0}
    active = {context=context, report=report, steps=self.steps, index=1, elapsed=0,
        lastTick=getTimestampMs(), manualStop=options.manualStop ~= false, writeReport=options.writeReport ~= false,
        cleanups=self.cleanups}
    P.lastReport = report
    Events.OnTick.Add(onTick)
    Events.OnServerCommand.Add(onServerCommand)
    log("Starting " .. self.name .. " (close the console and unpause)")
    log("Run token: " .. runToken .. (batch and (" | batch: " .. batch.token
        .. " | index: " .. batch.index .. " | path: " .. report.scenarioPath) or ""))
    return report
end

function P.stop(reason)
    if batch then P.stopBatch(reason) return end
    finish("cancelled", reason or "Stopped from console")
end

local function finishBatch(status,reason)
    if not batch then return end
    batch.status,batch.reason=status,reason
    batch.finishedAt=getTimestampMs()
    P.lastBatch=batch
    log("Batch " .. batch.token .. " : " .. status .. (reason and (" | " .. reason) or ""))
    batch=nil
    Events.OnTick.Remove(onBatchTick)
end

function P.stopBatch(reason)
    if not batch then return end
    finish("cancelled",reason or "Batch stopped from console")
    finishBatch("cancelled",reason or "Batch stopped from console")
end

local function copy(source)
    local result={}
    for key,value in pairs(source or {}) do result[key]=value end
    return result
end

function P.batchStatus()
    local current=batch or P.lastBatch
    if not current then return nil end
    return {token=current.token,status=current.status,index=current.index,total=#current.entries,
        path=current.entries[current.index] and current.entries[current.index].path,
        runToken=current.child and current.child.runToken,reason=current.reason,
        completed=current.completed,skipped=current.skipped,startedAt=current.startedAt,finishedAt=current.finishedAt}
end

function P.runStatus()
    return {busy=active~=nil or batch~=nil,scenario=P.status(),batch=P.batchStatus()}
end

local function launchBatchChild()
    local entry=batch.entries[batch.index]
    while entry and entry.when do
        local condition=entry.when(entry.params)
        assert(type(condition)=="boolean","Batch entry.when must return true or false")
        if condition then break end
        log("Batch skipped: " .. batch.token .. " | index: " .. batch.index
            .. " | path: " .. entry.path .. " | reason: " .. entry.skipReason)
        batch.skipped=batch.skipped+1
        batch.index=batch.index+1
        entry=batch.entries[batch.index]
    end
    if not entry then finishBatch("passed") return end
    -- Child wrappers may build their scenario by loading another factory (e.g. suite.lua).
    -- This scoped permission allows construction only; Scenario.run stays blocked in factories.
    batchLoading=true
    local loaded,scenario=pcall(loadScenario,entry.path,entry.params)
    batchLoading=false
    if not loaded then error(scenario) end
    batchLaunching=true
    local ok,report=pcall(Scenario.run,scenario,entry.options)
    batchLaunching=false
    if not ok then error(report) end
    batch.child=report
    batch.status="running"
end

local function readAck()
    local reader=getFileReader("PZPuppet/batch-ack.txt",false)
    if not reader then return nil end
    local ok,line=pcall(function() return reader:readLine() end)
    reader:close()
    if not ok then error(line) end
    if not line then return nil end
    local ackToken,status,reason=line:match("^PZPuppet ACK ([%d-]+) (%a+)%s*(.*)$")
    if ackToken==batch.child.runToken then return status,reason end
    return nil
end

onBatchTick=function()
    if not batch then return end
    local ok,err=pcall(function()
        local child=batch.child
        if child.status=="running" then return end
        if child.status~="passed" then
            finishBatch(child.status,child.reason or "Child scenario did not pass")
            return
        end
        if not child.persisted then finishBatch("failed","Child report was not persisted") return end
        local now=getTimestampMs()
        if batch.status~="awaiting_archive" then
            batch.status="awaiting_archive"
            batch.ackDeadline=now+batch.ackTimeout*1000
            batch.nextAckPoll=now
            log("Batch archive requested: " .. child.runToken .. " | report: " .. child.persistentReport)
        end
        if now<batch.nextAckPoll then return end
        batch.nextAckPoll=now+500
        local status,reason=readAck()
        if status=="passed" then
            batch.completed=batch.completed+1
            if batch.index==#batch.entries then finishBatch("passed") return end
            batch.index=batch.index+1
            launchBatchChild()
        elseif status then
            finishBatch("failed","Archive rejected: " .. (reason~="" and reason or status))
        elseif now>=batch.ackDeadline then
            finishBatch("failed","Timeout waiting for archive ACK: " .. child.runToken)
        end
    end)
    if not ok and batch then
        finish("failed","Batch: " .. tostring(err))
        finishBatch("failed",tostring(err))
    end
end

function P.runFiles(entries,options)
    assert(isDebugEnabled() and not active and not batch,"Use debug mode with no scenario or batch already running")
    assert(type(entries)=="table" and #entries>0,"runFiles needs a nonempty sequence of entries")
    options=options or {}
    assert(type(options)=="table","Batch options must be a table")
    assert(options.writeReport~=false,"Batches require persistent reports and archive ACK")
    assert(getFileReader and getFileWriter,"Batches require the game file APIs")
    local timeout=positive(options.ackTimeout or 30,"ackTimeout")
    assert(timeout<=300,"ackTimeout must not exceed 300 seconds")
    local normalized={}
    for index,entry in ipairs(entries) do
        assert(type(entry)=="table" and type(entry.path)=="string","Each batch entry needs path")
        assert(entry.params==nil or type(entry.params)=="table","Entry params must be a table")
        assert(entry.options==nil or type(entry.options)=="table","Entry options must be a table")
        assert(entry.when==nil or type(entry.when)=="function","Entry when must be a function")
        assert(not entry.when or (type(entry.skipReason)=="string" and entry.skipReason~=""),
            "Conditional entries need a skipReason")
        local childOptions=copy(options)
        childOptions.ackTimeout=nil
        for key,value in pairs(entry.options or {}) do childOptions[key]=value end
        assert(childOptions.writeReport~=false,"Batch children require persistent reports")
        normalized[index]={path=entry.path,params=copy(entry.params),options=childOptions,
            when=entry.when,skipReason=entry.skipReason}
    end
    batch={token=token(),entries=normalized,index=1,completed=0,skipped=0,status="starting",
        ackTimeout=timeout,startedAt=getTimestampMs()}
    log("Batch " .. batch.token .. " starting | count: " .. #normalized .. " | ackTimeout: " .. timeout)
    for index,entry in ipairs(normalized) do
        log("Batch entry " .. index .. " | path: " .. entry.path .. " | playerIndex: "
            .. tostring(entry.options.playerIndex or 0) .. " | manualStop: " .. tostring(entry.options.manualStop~=false))
    end
    local ok,err=pcall(launchBatchChild)
    if not ok then finishBatch("failed",tostring(err)) return P.batchStatus() end
    if batch then Events.OnTick.Add(onBatchTick) end
    return P.batchStatus()
end

-- A plan is trusted reloadable Lua, but does not start any scenarios on game load.
function P.runBatchFile(path,options,params)
    assert(not batch,"A batch is running; PZDevKit.Scenario.stopBatch() to cancel it")
    local entries=loadFactory(path)(params or {})
    return P.runFiles(entries,options)
end

function P.status()
    if not active then return P.lastReport end
    return {name=active.report.name, status="running", index=active.index,
        label=active.steps[active.index].label, duration=active.elapsed, position=snapshot(active)}
end

function P.printStatus()
    local s = P.status()
    if not s then log("No scenario has run") return end
    log(s.name .. " : " .. s.status .. (s.label and (" | " .. s.label) or ""))
    if s.reason then log(s.reason) end
end

P.Scenario = Scenario
-- No action or event subscription until :run().
return P
