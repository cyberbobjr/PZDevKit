local T={}
function T.setup()
    assert(loadstring(readTests("test_engine.lua")))().setup()
    FILES,CLOSED={},0
    getFileReader=function(path)
        local text=FILES[path]
        if not text then return nil end
        local lines={}
        for line in (text .. "\n"):gmatch("(.-)\n") do lines[#lines+1]=line end
        local index=0
        return {readLine=function() index=index+1; return lines[index] end,
            close=function() CLOSED=CLOSED+1 end}
    end
end
local function tick()
    NOW=NOW+100
    Events.OnTick.handlers[1]()
end
local function file(text) FILES["PZPuppet/scenarios/Test/basic.lua"]=text end

function T.registry_is_sorted_and_never_runs_on_registration()
    local calls=0
    PZDevKit.Scenario.register("Z.test",function() calls=calls+1; return PZDevKit.Scenario.scenario("z"):wait(0) end)
    PZDevKit.Scenario.register("A.test",function() return PZDevKit.Scenario.scenario("a"):wait(0) end)
    assert(calls==0 and #Events.OnTick.handlers==0)
    local names=PZDevKit.Scenario.listScenarios()
    assert(names[1]=="A.test" and names[2]=="Z.test")
    assert(not pcall(PZDevKit.Scenario.register,"Z.test",function() end))
    PZDevKit.Scenario.register("Z.test",function(params)
        return PZDevKit.Scenario.scenario(params.title):wait(0)
    end,true)
    PZDevKit.Scenario.run("Z.test",nil,{title="fresh"}); tick()
    assert(PZDevKit.Scenario.lastReport.name=="fresh" and PZDevKit.Scenario.lastReport.status=="passed")
    PZDevKit.Scenario.run("Z.test",nil,{title="again"}); tick()
    assert(PZDevKit.Scenario.lastReport.name=="again")
end
function T.unknown_invalid_and_non_debug_factories_do_not_start()
    assert(not pcall(PZDevKit.Scenario.run,"absent"))
    PZDevKit.Scenario.register("bad",function() return {} end)
    assert(not pcall(PZDevKit.Scenario.run,"bad"))
    DEBUG=false
    PZDevKit.Scenario.register("forbidden",function() error("must not execute") end)
    local ok,err=pcall(PZDevKit.Scenario.run,"forbidden")
    assert(not ok and err:find("debug mode",1,true))
    assert(#Events.OnTick.handlers==0)
end
function T.file_is_reread_and_reader_closed_before_execution()
    file('return function(params) assert(CLOSED==1); return PZDevKit.Scenario.scenario(params.title):wait(0) end')
    local scenario=PZDevKit.Scenario.loadScenario("Test/basic.lua",{title="one"})
    assert(CLOSED==1 and #Events.OnTick.handlers==0)
    scenario:run(); tick(); assert(PZDevKit.Scenario.lastReport.name=="one")
    file('return function() assert(CLOSED==2); return PZDevKit.Scenario.scenario("changed"):wait(0) end')
    PZDevKit.Scenario.runFile("Test/basic.lua"); tick()
    assert(PZDevKit.Scenario.lastReport.name=="changed")
end
function T.paths_are_relative_and_files_are_required()
    for _,path in ipairs({"../bad.lua","/bad.lua","C:/bad.lua","Test\\basic.lua","Test/basic.txt","Test/../basic.lua"}) do
        assert(not pcall(PZDevKit.Scenario.loadScenario,path))
    end
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/missing.lua"))
    assert(CLOSED==0)
end
function T.syntax_return_type_and_size_errors_close_the_file()
    file('this is not valid Lua')
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/basic.lua")); assert(CLOSED==1)
    file('return {}')
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/basic.lua")); assert(CLOSED==2)
    file('return function() return {} end')
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/basic.lua")); assert(CLOSED==3)
    file(string.rep(" ",262145))
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/basic.lua")); assert(CLOSED==4)
    assert(#Events.OnTick.handlers==0)
end
function T.utf8_bom_is_supported_and_active_runner_blocks_loading()
    file('\239\187\191return function() return PZDevKit.Scenario.scenario("UTF8"):wait(0) end')
    PZDevKit.Scenario.runFile("Test/basic.lua")
    assert(not pcall(PZDevKit.Scenario.loadScenario,"Test/basic.lua"))
    assert(CLOSED==1)
    tick(); assert(PZDevKit.Scenario.lastReport.status=="passed")
end
return T
