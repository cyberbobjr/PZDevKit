-- Lua 5.1 orchestration contracts; no Project Zomboid execution implied.
local T={}
function T.setup()
    assert(loadstring(readTests("test_loader.lua")))().setup()
    getFileWriter=function(path)
        local parts={}
        return {write=function(_,text) parts[#parts+1]=text end,
            close=function() FILES[path]=table.concat(parts) end}
    end
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function(params)
            return PZDevKit.Scenario.scenario(params.title or "first")
                :call("actual callback",function() EXECUTED=(EXECUTED or 0)+1 end)
                :finally(function() CLEANED=(CLEANED or 0)+1 end)
        end
    ]]
    FILES["PZPuppet/scenarios/Test/second.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("second"):wait(0) end
    ]]
    EXECUTED,CLEANED=0,0
end

local function tick(ms)
    NOW=NOW+(ms or 500)
    local handlers={}
    for i,handler in ipairs(Events.OnTick.handlers) do handlers[i]=handler end
    for _,handler in ipairs(handlers) do handler() end
end
local function plan()
    return {{path="Test/first.lua"},{path="Test/second.lua"}}
end
local function ack(status,reason)
    FILES["PZPuppet/batch-ack.txt"]="PZPuppet ACK " .. PZDevKit.Scenario.lastReport.runToken
        .. " " .. (status or "passed") .. " " .. (reason or "")
end

function T.success_needs_matching_archive_ack_after_cleanup_for_each_child()
    local s=PZDevKit.Scenario.runFiles(plan(),{manualStop=false})
    assert(s.status=="running" and PZDevKit.Scenario.runStatus().busy)
    tick()
    local first=PZDevKit.Scenario.lastReport
    assert(first.status=="passed" and CLEANED==1 and first.persisted)
    assert(PZDevKit.Scenario.batchStatus().status=="awaiting_archive")
    local persisted=FILES[first.persistentReport]
    assert(persisted:find("Player index: 0",1,true) and persisted:find("Manual stop: false",1,true))
    assert(persisted:find("Batch index: 1",1,true) and persisted:find("Run token: " .. first.runToken,1,true))
    tick(); assert(PZDevKit.Scenario.lastReport==first)
    ack(); tick()
    local second=PZDevKit.Scenario.lastReport
    assert(second.status=="running" and second.runToken~=first.runToken)
    assert(FILES[first.persistentReport]==persisted)
    tick(); ack(); tick()
    s=PZDevKit.Scenario.batchStatus()
    assert(s.status=="passed" and s.completed==2 and s.skipped==0)
    assert(not PZDevKit.Scenario.runStatus().busy and #Events.OnTick.handlers==0)
    assert(FILES[second.persistentReport] and FILES["PZPuppet/last-report.txt"]==FILES[second.persistentReport])
end

function T.stale_or_partial_ack_cannot_start_next_child()
    PZDevKit.Scenario.runFiles(plan())
    tick()
    for _,line in ipairs({"PZPuppet ACK 999-999 passed","PZPuppet ACK ","unrelated text"}) do
        FILES["PZPuppet/batch-ack.txt"]=line
        tick()
        assert(PZDevKit.Scenario.batchStatus().index==1 and PZDevKit.Scenario.batchStatus().status=="awaiting_archive")
    end
    ack(); tick(); assert(PZDevKit.Scenario.batchStatus().index==2)
end

function T.collector_rejection_stops_without_next_actions()
    PZDevKit.Scenario.runFiles(plan()); tick(); ack("rejected","New external Lua error")
    tick()
    local s=PZDevKit.Scenario.batchStatus()
    assert(s.status=="failed" and s.completed==0 and s.index==1)
    assert(s.reason:find("New external Lua error",1,true) and not PZDevKit.Scenario.runStatus().busy)
    assert(PZDevKit.Scenario.lastReport.name=="first" and CLEANED==1)
end

function T.archive_timeout_is_bounded_wall_time_and_does_not_resume_later()
    PZDevKit.Scenario.runFiles(plan(),{ackTimeout=1})
    tick(); SPEED=0; tick(1100)
    assert(PZDevKit.Scenario.batchStatus().status=="failed")
    assert(PZDevKit.Scenario.batchStatus().reason:find("Timeout waiting for archive ACK",1,true))
    ack(); SPEED=1; tick()
    assert(PZDevKit.Scenario.lastReport.name=="first" and #Events.OnTick.handlers==0)
end

function T.failed_and_cancelled_child_runs_cleanup_and_stops_without_ack()
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("failure")
            :check("missing",function() return false,"No fixture" end)
            :finally(function() CLEANED=CLEANED+1 end) end
    ]]
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and CLEANED==1)
    assert(PZDevKit.Scenario.lastReport.persisted and PZDevKit.Scenario.lastReport.reason=="No fixture")
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("cancel")
            :wait(10):finally(function() CLEANED=CLEANED+1 end) end
    ]]
    PZDevKit.Scenario.runFiles(plan()); INPUT=true; tick()
    assert(PZDevKit.Scenario.batchStatus().status=="cancelled" and CLEANED==2)
end

function T.cleanup_and_report_write_failure_stop_batch()
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("cleanup")
            :wait(0):finally(function() error("Cleanup failed") end) end
    ]]
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed")
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("write failure"):wait(0) end
    ]]
    getFileWriter=function() return nil end
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and PZDevKit.Scenario.lastReport.persisted==false)
    assert(PZDevKit.Scenario.lastReport.reason:find("Report write:",1,true))
    assert(#Events.OnTick.handlers==0)
end

function T.queue_cleanup_error_cannot_be_reported_as_passed()
    PZDevKit.Scenario.Game.cancel=function() error("Cannot cancel owned queue") end
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() return PZDevKit.Scenario.scenario("queue cleanup")
            :call("own queue",function(c) c.queueOwned=true end) end
    ]]
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed")
    assert(PZDevKit.Scenario.lastReport.reason:find("Cannot cancel owned queue",1,true))
end

function T.writer_and_ack_reader_are_closed_when_an_operation_throws()
    local closed=0
    getFileWriter=function()
        return {write=function() error("Disk write failed") end,close=function() closed=closed+1 end}
    end
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and closed==1)
    getFileWriter=function(path)
        local parts={}
        return {write=function(_,text) parts[#parts+1]=text end,
            close=function() FILES[path]=table.concat(parts) end}
    end
    local originalReader=getFileReader
    getFileReader=function(path)
        if path=="PZPuppet/batch-ack.txt" then
            return {readLine=function() error("ACK read failed") end,close=function() closed=closed+1 end}
        end
        return originalReader(path)
    end
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and closed==2)
end

function T.batch_blocks_other_entry_points_even_while_awaiting_archive()
    PZDevKit.Scenario.register("foreign",function() return PZDevKit.Scenario.scenario("foreign"):wait(0) end)
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(not pcall(PZDevKit.Scenario.runFile,"Test/second.lua"))
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/second.lua"))
    assert(not pcall(PZDevKit.Scenario.run,"foreign"))
    assert(not pcall(PZDevKit.Scenario.runFiles,plan()))
    assert(not pcall(function() PZDevKit.Scenario.scenario("foreign"):wait(0):run() end))
    assert(PZDevKit.Scenario.batchStatus().index==1)
end

function T.stop_and_reload_release_both_runners_with_cleanup_exactly_once()
    PZDevKit.Scenario.runFiles(plan())
    PZDevKit.Scenario.stopBatch("operator stop")
    assert(CLEANED==1 and PZDevKit.Scenario.batchStatus().status=="cancelled")
    assert(#Events.OnTick.handlers==0 and #Events.OnServerCommand.handlers==0)
    PZDevKit.Scenario.runFiles(plan()); tick()
    dofileMod("PZDevKit/Scenario")
    assert(CLEANED==2 and PZDevKit.Scenario.batchStatus().status=="cancelled")
    assert(PZDevKit.Scenario.batchStatus().reason=="Lua reload" and #Events.OnTick.handlers==0)
    PZDevKit.Scenario.runFiles(plan()); dofileMod("PZDevKit/Scenario")
    assert(CLEANED==3 and #Events.OnTick.handlers==0)
end

function T.loading_syntax_and_factory_errors_stop_before_next_child()
    local scenarios={"Test/missing.lua","Test/../bad.lua","Test/second.lua"}
    FILES["PZPuppet/scenarios/Test/second.lua"]="return function() error('factory exploded') end"
    for _,path in ipairs(scenarios) do
        PZDevKit.Scenario.runFiles({{path=path},{path="Test/first.lua"}})
        assert(PZDevKit.Scenario.batchStatus().status=="failed" and EXECUTED==0)
        assert(#Events.OnTick.handlers==0)
    end
    FILES["PZPuppet/scenarios/Test/second.lua"]="invalid Lua syntax"
    PZDevKit.Scenario.runFiles({{path="Test/second.lua"}})
    assert(PZDevKit.Scenario.batchStatus().status=="failed")
end

function T.factories_cannot_start_a_nested_scenario()
    FILES["PZPuppet/scenarios/Test/first.lua"]=[[
        return function() PZDevKit.Scenario.scenario("nested"):wait(0):run()
            return PZDevKit.Scenario.scenario("outer"):wait(0) end
    ]]
    PZDevKit.Scenario.runFiles(plan())
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and #Events.OnTick.handlers==0)
end

function T.child_wrapper_can_hot_load_nested_factories_without_launching_them()
    FILES["PZPuppet/scenarios/Test/wrapper.lua"]=[[
        return function(params) return PZDevKit.Scenario.loadScenario("Test/middle.lua",params) end
    ]]
    FILES["PZPuppet/scenarios/Test/middle.lua"]=[[
        return function(params) return PZDevKit.Scenario.loadScenario("Test/first.lua",params) end
    ]]
    PZDevKit.Scenario.runFiles({{path="Test/wrapper.lua",params={title="nested factory"}},{path="Test/second.lua"}})
    assert(PZDevKit.Scenario.batchStatus().status=="running" and EXECUTED==0 and CLOSED==3)
    assert(PZDevKit.Scenario.lastReport.name=="nested factory")
    tick(); assert(EXECUTED==1 and CLEANED==1 and PZDevKit.Scenario.lastReport.persisted)
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/first.lua"))
    ack(); tick(); tick(); ack(); tick()
    assert(PZDevKit.Scenario.batchStatus().status=="passed" and PZDevKit.Scenario.batchStatus().completed==2)
end

function T.nested_loading_failure_releases_construction_permission()
    FILES["PZPuppet/scenarios/Test/wrapper.lua"]=[[
        return function() return PZDevKit.Scenario.loadScenario("Test/missing.lua") end
    ]]
    PZDevKit.Scenario.runFiles({{path="Test/wrapper.lua"}})
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and not PZDevKit.Scenario.runStatus().busy)
    PZDevKit.Scenario.runFiles(plan()); tick()
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/first.lua"))
    PZDevKit.Scenario.stopBatch()
    assert(#Events.OnTick.handlers==0)
end

function T.nested_factories_cannot_use_runfile_or_run_permission()
    FILES["PZPuppet/scenarios/Test/wrapper.lua"]=[[
        return function() return PZDevKit.Scenario.loadScenario("Test/nested.lua") end
    ]]
    FILES["PZPuppet/scenarios/Test/nested.lua"]=[[
        return function() PZDevKit.Scenario.runFile("Test/second.lua")
            return PZDevKit.Scenario.scenario("should not start"):wait(0) end
    ]]
    PZDevKit.Scenario.runFiles({{path="Test/wrapper.lua"}})
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and PZDevKit.Scenario.lastReport==nil)
    assert(#Events.OnTick.handlers==0 and EXECUTED==0)
end

function T.conditional_skip_is_recorded_without_a_fake_child_result()
    local entries=plan()
    entries[1].when=function() return false end
    entries[1].skipReason="Optional dependency absent"
    local status=PZDevKit.Scenario.runFiles(entries)
    assert(status.skipped==1 and status.index==2 and status.completed==0)
    assert(EXECUTED==0 and PZDevKit.Scenario.lastReport.name=="second")
    local found=false
    for _,line in ipairs(LOGS) do
        if line:find("Batch skipped:",1,true) and line:find("Optional dependency absent",1,true) then found=true end
    end
    assert(found)
    tick(); ack(); tick(); assert(PZDevKit.Scenario.batchStatus().completed==1)
end

function T.all_skipped_plan_starts_no_scenario_or_event()
    local entries=plan()
    for _,entry in ipairs(entries) do entry.when=function() return false end; entry.skipReason="Not applicable" end
    local s=PZDevKit.Scenario.runFiles(entries)
    assert(s.status=="passed" and s.skipped==2 and s.completed==0)
    assert(PZDevKit.Scenario.lastReport==nil and #Events.OnTick.handlers==0)
end

function T.invalid_skip_condition_stops_instead_of_accepting_truthy_value()
    local entries=plan()
    entries[1].when=function() return "yes" end; entries[1].skipReason="Optional"
    PZDevKit.Scenario.runFiles(entries)
    assert(PZDevKit.Scenario.batchStatus().status=="failed" and EXECUTED==0)
end

function T.plan_files_are_hot_loaded_without_automatic_launch_on_loading()
    FILES["PZPuppet/scenarios/Test/plan.lua"]=[[
        return function(params) return {{path="Test/first.lua",params={title=params.title}}} end
    ]]
    PZDevKit.Scenario.runBatchFile("Test/plan.lua",nil,{title="plan one"})
    tick(); ack(); tick(); assert(PZDevKit.Scenario.lastReport.name=="plan one")
    FILES["PZPuppet/scenarios/Test/plan.lua"]=[[
        return function() return {{path="Test/second.lua"}} end
    ]]
    PZDevKit.Scenario.runBatchFile("Test/plan.lua")
    tick(); ack(); tick(); assert(PZDevKit.Scenario.lastReport.name=="second")
    assert(not pcall(PZDevKit.Scenario.runBatchFile,"../bad.lua"))
end

function T.entry_options_override_defaults_without_mutating_callers()
    local entries=plan()
    entries[1].params={title="original"}
    entries[1].options={manualStop=false}
    local options={playerIndex=0,manualStop=true,ackTimeout=2}
    PZDevKit.Scenario.runFiles(entries,options)
    entries[2].path="Test/missing.lua"
    entries[1].params.title="changed"
    assert(PZDevKit.Scenario.lastReport.manualStop==false and options.ackTimeout==2)
    tick(); ack(); tick()
    assert(PZDevKit.Scenario.lastReport.name=="second" and PZDevKit.Scenario.lastReport.manualStop==true)
end

function T.invalid_options_reject_before_any_callbacks_or_subscriptions()
    assert(not pcall(PZDevKit.Scenario.runFiles,{},{}))
    for _,options in ipairs({{ackTimeout=0},{ackTimeout=301},{writeReport=false}}) do
        assert(not pcall(PZDevKit.Scenario.runFiles,plan(),options))
    end
    assert(not pcall(PZDevKit.Scenario.runFiles,{{path="Test/first.lua",options={writeReport=false}}}))
    assert(not pcall(PZDevKit.Scenario.runFiles,{{path="Test/first.lua",when=function() return false end}}))
    assert(EXECUTED==0 and #Events.OnTick.handlers==0)
end

return T
