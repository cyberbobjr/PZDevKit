local T={}
local function eq(actual,expected)
    assert(actual==expected,"Expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

function T.setup()
    NOW, DEBUG, SPEED, CLEARS, DEAD, ASLEEP, INPUT, DISCONNECTED = 0,true,1,0,false,false,false,false
    LOGS, WRITES = {},{}
    getTimestampMs=function() return NOW end
    isDebugEnabled=function() return DEBUG end
    getGameSpeed=function() return SPEED end
    print=function(msg) LOGS[#LOGS+1]=msg end
    getFileWriter=function(path)
        assert(path=="PZPuppet/last-report.txt" or path:match("^PZPuppet/reports/[%d-]+%.txt$"))
        return {write=function(_,s) WRITES[#WRITES+1]=s end,close=function() end}
    end
    Events=setmetatable({}, {__index=function(events,key)
        local e={handlers={}}
        e.Add=function(f) e.handlers[#e.handlers+1]=f end
        e.Remove=function(f) for i=#e.handlers,1,-1 do if e.handlers[i]==f then table.remove(e.handlers,i) end end end
        events[key]=e
        return e
    end})
    INV={}
    ACCESSIBLE={}
    INV.getOutermostContainer=function() return INV end
    ITEM={ getContainer=function() return ITEM.container end }
    INV.getFirstTypeRecurse=function(_,typeName) return typeName=="Base.TestItem" and ITEM or nil end
    ITEM.container=INV
    PLAYER={x=10.5,y=20.5,z=0,primary=nil,secondary=nil,
        getX=function(s) return s.x end,getY=function(s) return s.y end,getZ=function(s) return s.z end,
        isDead=function() return DEAD end,isAsleep=function() return ASLEEP end,
        pressedMovement=function() return INPUT end,pressedCancelAction=function() return false end,
        getVehicle=function() return nil end,getPlayerNum=function() return 0 end,
        getInventory=function() return INV end,canAccessContainer=function() return true end,
        getPrimaryHandItem=function(s) return s.primary end,getSecondaryHandItem=function(s) return s.secondary end}
    getSpecificPlayer=function(index) if index==0 and not DISCONNECTED then return PLAYER end end
    QUEUE={}
    ISTimedActionQueue={queues={[PLAYER]={queue=QUEUE}},
        add=function(a) QUEUE[#QUEUE+1]=a end,
        clear=function() CLEARS=CLEARS+1 for i=#QUEUE,1,-1 do table.remove(QUEUE,i) end end}
    LOADED=true
    getCell=function() return {getGridSquare=function() return LOADED and {} or nil end} end
    ISPathFindAction={
        pathToLocationF=function(_,player,x,y,z)
            local a={character=player,x=x,y=y,z=z,
                setOnFail=function(s,f) s.failed=f end,setOnComplete=function(s,f) s.completed=f end}
            PATH=a
            return a
        end,
        pathToVehicleArea=function(self,player) return self:pathToLocationF(player,0,0,0) end,
        pathToVehicleAdjacent=function(self,player) return self:pathToLocationF(player,0,0,0) end}
    ISInventoryPaneContextMenu={getContainers=function()
        return {contains=function(_,container) return ACCESSIBLE[container]==true end}
    end,equipWeapon=function(item,primary,two,index)
        eq(index,0)
        QUEUE[#QUEUE+1]={equip=item,primary=primary,two=two}
    end}
    ISInventoryTransferUtil={newInventoryTransferAction=function(player,item,src,dest)
        eq(player,PLAYER)
        return {character=player,item=item,src=src,dest=dest}
    end}
    ISOpenCloseDoor={new=function(_,player,door) return {character=player,door=door} end}
    instanceof=function(obj,class) return obj.kind==class end
    dofileMod("PZDevKit/Scenario")
    dofileMod("PZDevKit/Game")
end

local function tick(ms)
    NOW=NOW+(ms or 100)
    local handlers={}
    for i,f in ipairs(Events.OnTick.handlers) do handlers[i]=f end
    for _,f in ipairs(handlers) do f() end
end
local function drain()
    for i=#QUEUE,1,-1 do table.remove(QUEUE,i) end
end
local function report() return PZDevKit.Scenario.lastReport end

function T.no_test_starts_automatically()
    eq(#Events.OnTick.handlers,0)
    eq(#QUEUE,0)
    eq(PZDevKit.Scenario.status(),nil)
end

function T.sequential_calls_waits_and_checks()
    local value=0
    PZDevKit.Scenario.scenario("sequence"):call("first",function(c) c.vars.number=4; value=1 end)
        :wait(.2):check("state",function(c) return c.vars.number==4 and value==1 end):run()
    eq(value,0)
    tick(); eq(value,1)
    tick(); tick(); eq(report().status,"running")
    tick(); tick(); tick()
    eq(report().status,"passed")
    eq(#report().steps,3)
    eq(#Events.OnTick.handlers,0)
    assert(#WRITES>0)
end

function T.assertion_failure_stops_before_the_next_step()
    local after=false
    PZDevKit.Scenario.scenario("assertion"):check("bad",function() return false,"missing item" end)
        :call("must not run",function() after=true end):run()
    tick(); tick()
    eq(report().status,"failed")
    eq(after,false)
    eq(report().steps[2].status,"pending")
    assert(report().reason:find("missing item",1,true))
end

function T.unmet_check_records_failure_without_raising_a_lua_assert()
    local cleanups,after=0,false
    PZDevKit.Scenario.scenario("expected failure")
        :check("missing",function() return false,"missing fixture" end)
        :call("must not execute",function() after=true end)
        :finally(function() cleanups=cleanups+1 end):run()
    local previousAssert=assert
    local failedAsserts=0
    assert=function(condition,...)
        if not condition then failedAsserts=failedAsserts+1 end
        return previousAssert(condition,...)
    end
    local ok,err=pcall(tick)
    assert=previousAssert
    assert(ok,err)
    tick()
    eq(failedAsserts,0)
    eq(report().status,"failed")
    eq(report().reason,"missing fixture")
    eq(cleanups,1)
    eq(after,false)
    eq(report().steps[2].status,"pending")
end

function T.timeout_is_a_failure_and_a_truthy_string_is_not_success()
    PZDevKit.Scenario.scenario("timeout"):await("event",function() return "yes" end,.2):run()
    tick(); tick(); tick(); tick()
    eq(report().status,"failed")
    assert(report().reason:find("Timeout",1,true))
end

function T.gates_reject_debug_off_missing_player_and_busy_queue()
    local s=PZDevKit.Scenario.scenario("gates"):wait(1)
    DEBUG=false
    eq(pcall(function() s:run() end),false)
    DEBUG=true
    eq(pcall(function() s:run({playerIndex=1}) end),false)
    QUEUE[1]={foreign=true}
    eq(pcall(function() s:run() end),false)
    eq(#QUEUE,1)
    eq(CLEARS,0)
    eq(#Events.OnTick.handlers,0)
end

function T.single_runner_and_stop_from_inside_a_callback()
    PZDevKit.Scenario.scenario("first"):call("stop",function() PZDevKit.Scenario.stop("callback") end):run()
    eq(pcall(function() PZDevKit.Scenario.scenario("second"):wait(1):run() end),false)
    tick()
    eq(report().status,"cancelled")
    eq(report().reason,"callback")
    eq(#Events.OnTick.handlers,0)
end

function T.speed_zero_ticks_and_long_gaps_do_not_consume_the_timeout()
    PZDevKit.Scenario.scenario("pause"):wait(1):run()
    tick()
    SPEED=0; tick(300000)
    eq(PZDevKit.Scenario.status().duration,.1)
    SPEED=1; tick(300000)
    eq(PZDevKit.Scenario.status().duration,.35)
    eq(report().status,"running")
end

function T.callback_error_after_queueing_cleans_up()
    PZDevKit.Scenario.scenario("error"):interact("broken",function()
        QUEUE[1]={}
        error("test failure")
    end,function() return true end):run()
    tick()
    eq(report().status,"failed")
    eq(#QUEUE,0)
    eq(CLEARS,1)
end

function T.waiting_does_not_claim_or_clear_foreign_actions()
    PZDevKit.Scenario.scenario("observer"):await("wait",function() return false end):run()
    tick()
    QUEUE[1]={foreign=true}
    INPUT=true; tick()
    eq(report().status,"cancelled")
    eq(#QUEUE,1)
    eq(CLEARS,0)
end

function T.death_sleep_and_disconnect_cancel_the_scenario()
    PZDevKit.Scenario.scenario("death"):wait(1):run()
    DEAD=true; tick(); eq(report().reason,"Player died")
    DEAD=false
    PZDevKit.Scenario.scenario("sleep"):wait(1):run()
    ASLEEP=true; tick(); eq(report().reason,"Player fell asleep")
    ASLEEP=false
    PZDevKit.Scenario.scenario("disconnect"):wait(1):run()
    DISCONNECTED=true; tick(); eq(report().reason,"Local player changed/disconnected")
end

function T.walk_uses_pathfinding_and_checks_both_position_and_queue()
    PZDevKit.Scenario.scenario("walk"):walkTo(12.5,20.5,0):run()
    tick()
    eq(PATH.x,12.5)
    eq(PATH.character,PLAYER)
    PLAYER.x=12.5
    tick(); eq(report().status,"running")
    drain(); tick(); eq(report().status,"passed")
end

function T.walk_path_failure_is_reported_and_cancelled()
    PZDevKit.Scenario.scenario("blocked"):walkTo(12.5,20.5,0):run()
    tick(); PATH.failed(); tick()
    eq(report().status,"failed")
    eq(#QUEUE,0)
    assert(report().reason:find("Pathfinding failed",1,true))
end

function T.walk_refuses_unloaded_target_and_wrong_floor_never_passes()
    LOADED=false
    PZDevKit.Scenario.scenario("unloaded"):walkTo(12.5,20.5,0):run()
    tick(); eq(report().status,"failed"); eq(PATH,nil)
    LOADED=true
    PZDevKit.Scenario.scenario("floor"):walkTo(12.5,20.5,1,.2):run()
    tick(); PLAYER.x=12.5; drain(); tick(); tick(); tick()
    eq(report().status,"failed")
end

function T.empty_queue_alone_does_not_prove_an_interaction_succeeded()
    PZDevKit.Scenario.scenario("cancelled queue"):interact("operation",function() QUEUE[1]={} end,
        function() return false end,.2):run()
    tick(); drain(); tick(); tick(); tick()
    eq(report().status,"failed")
end

function T.generic_timed_action_cancellation_is_observed_without_patching_the_class()
    local stopped=0
    local original=function() stopped=stopped+1 end
    local class={stop=original}
    local action=setmetatable({character=PLAYER},{__index=class})
    PZDevKit.Scenario.scenario("generic"):act("custom",function() return action end,function() return true end):run()
    tick(); action:stop(); drain(); tick()
    eq(stopped,1)
    eq(class.stop,original)
    eq(report().status,"failed")
end

function T.manual_stop_cancels_a_claimed_path_action()
    PZDevKit.Scenario.scenario("manual"):walkTo(12.5,20.5,0):run()
    tick(); INPUT=true; tick()
    eq(report().status,"cancelled")
    eq(CLEARS,1)
    eq(#QUEUE,0)
end

function T.equip_uses_the_vanilla_menu_callback_and_checks_the_correct_hand()
    PLAYER.secondary=ITEM
    PZDevKit.Scenario.scenario("equip"):equip("Base.TestItem",true):run()
    tick()
    eq(QUEUE[1].equip,ITEM)
    drain(); tick(); eq(report().status,"running")
    PLAYER.primary=ITEM; tick(); eq(report().status,"passed")
end

function T.transfer_uses_the_vanilla_action_and_waits_for_container_change()
    local destination={getOutermostContainer=function(self) return self end}
    ACCESSIBLE[destination]=true
    PZDevKit.Scenario.scenario("transfer"):transfer("Base.TestItem",destination):run()
    tick()
    eq(QUEUE[1].src,INV)
    eq(QUEUE[1].dest,destination)
    drain(); tick(); eq(report().status,"running")
    ITEM.container=destination; tick(); eq(report().status,"passed")
end

function T.door_uses_the_timed_action_and_locked_door_times_out()
    local open=false
    local door={kind="IsoDoor",IsOpen=function() return open end,
        getSquare=function() return {getX=function() return 10 end,getY=function() return 20 end,
            getZ=function() return 0 end} end}
    PZDevKit.Scenario.scenario("door"):door(door,true,.2):run()
    tick(); eq(QUEUE[1].door,door)
    drain(); tick(); tick(); tick()
    eq(report().status,"failed")
    PZDevKit.Scenario.scenario("door success"):door(door,true):run()
    tick(); open=true; drain(); tick()
    eq(report().status,"passed")
end

function T.vehicle_navigation_uses_the_path_completion_callback()
    local vehicle={isRemovedFromWorld=function() return false end}
    PZDevKit.Scenario.scenario("vehicle"):walkToVehicle(vehicle):run()
    tick(); drain(); tick(); eq(report().status,"running")
    PATH.completed(); tick(); eq(report().status,"passed")
end

function T.poll_exception_fails_and_no_step_runs_afterwards()
    PZDevKit.Scenario.scenario("poll"):await("error",function() error("predicate error") end):wait(1):run()
    tick(); eq(report().status,"failed")
    eq(report().steps[2].status,"pending")
end

function T.no_report_option_keeps_the_result_in_memory()
    PZDevKit.Scenario.scenario("memory"):check("ok",function() return true end):run({writeReport=false})
    tick(); eq(report().status,"passed"); eq(#WRITES,0)
end

function T.core_reload_releases_the_old_tick_subscription()
    PZDevKit.Scenario.scenario("reload"):wait(1):run()
    dofileMod("PZDevKit/Scenario")
    eq(report().status,"cancelled")
    eq(#Events.OnTick.handlers,0)
end

function T.invalid_steps_and_reusing_a_scenario_are_rejected()
    local s=PZDevKit.Scenario.scenario("validation")
    eq(pcall(function() s:wait(-1) end),false)
    eq(pcall(function() s:await("bad",function() end,0/0) end),false)
    eq(pcall(function() s:walkTo(nil,2,0) end),false)
    s:wait(0):run(); tick()
    eq(pcall(function() s:run() end),false)
end

function T.synchronous_server_reply_is_saved_before_the_wait_step_and_consumed_once()
    PZDevKit.Scenario.scenario("network"):call("request",function()
        for _,f in ipairs(Events.OnServerCommand.handlers) do f("Mod","Ack",{id=7}) end
    end):awaitServerCommand("Mod","Ack",function(_,args) return args.id==7 end)
        :awaitServerCommand("Mod","Ack",nil,.2):run()
    tick(); tick()
    eq(report().steps[2].status,"passed")
    tick(); tick(); tick(); tick()
    eq(report().status,"failed")
    eq(#Events.OnServerCommand.handlers,0)
end

function T.server_history_is_bounded_and_wrong_replies_do_not_pass()
    PZDevKit.Scenario.scenario("filter"):call("noise",function()
        for i=1,100 do
            for _,f in ipairs(Events.OnServerCommand.handlers) do f("Other","Ack",{id=i}) end
        end
    end):awaitServerCommand("Mod","Ack",nil,.2):run()
    tick(); tick(); tick(); tick(); tick()
    eq(report().status,"failed")
end

function T.travel_streams_a_route_as_loaded_waypoints_without_changing_player_position()
    PZDevKit.Scenario.scenario("travel"):travelTo(60.5,20.5,0):run()
    tick()
    eq(PATH.x,34.5)
    eq(PLAYER.x,10.5)
    PLAYER.x=PATH.x; drain(); tick()
    eq(PATH.x,58.5)
    PLAYER.x=PATH.x; drain(); tick()
    eq(PATH.x,60.5)
    PLAYER.x=PATH.x; drain(); tick()
    eq(report().status,"passed")
end

function T.travel_does_not_advance_if_a_waypoint_was_not_reached()
    PZDevKit.Scenario.scenario("lost waypoint"):travelTo(60.5,20.5,0):run()
    tick(); drain(); tick()
    eq(report().status,"failed")
    eq(PLAYER.x,10.5)
end

function T.ui_click_respects_visibility_enablement_and_the_result_predicate()
    local clicked=false
    local button={forceClick=function() clicked=true end,isEnabled=function() return true end,
        getIsVisible=function() return true end}
    PZDevKit.Scenario.scenario("UI"):click(button,function() return clicked end):run()
    tick(); eq(report().status,"passed")
    clicked=false; button.isEnabled=function() return false end
    PZDevKit.Scenario.scenario("disabled UI"):click(button,function() return clicked end):run()
    tick(); eq(report().status,"failed"); eq(clicked,false)
end

function T.finally_runs_once_in_reverse_order_even_on_failure()
    local order={}
    PZDevKit.Scenario.scenario("cleanup"):finally(function() order[#order+1]="first" end)
        :finally(function() order[#order+1]="second" end)
        :check("fail",function() return false end):run()
    tick(); PZDevKit.Scenario.stop()
    eq(table.concat(order,","),"second,first")
end

function T.cleanup_failure_prevents_a_passed_report()
    PZDevKit.Scenario.scenario("cleanup error"):finally(function() error("restore failure") end)
        :check("ok",function() return true end):run()
    tick(); eq(report().status,"failed")
    assert(report().reason:find("restore failure",1,true))
end

function T.nearest_vehicle_ignores_removed_nonmatching_and_out_of_range_vehicles()
    local function vehicle(x,removed,matches)
        return {getX=function() return x end,getY=function() return PLAYER.y end,
            isRemovedFromWorld=function() return removed end,matches=matches}
    end
    local good=vehicle(12,false,true)
    local items={vehicle(11,true,true),vehicle(11,false,false),vehicle(80,false,true),good}
    getCell=function() return {getVehicles=function() return {size=function() return #items end,
        get=function(_,i) return items[i+1] end} end} end
    eq(PZDevKit.Scenario.Game.nearestVehicle({player=PLAYER},function(v) return v.matches end,10),good)
end

function T.remote_or_locked_container_is_rejected_before_transfer()
    local remote={getOutermostContainer=function(self) return self end}
    PZDevKit.Scenario.scenario("remote transfer"):transfer(ITEM,remote):run()
    tick(); eq(report().status,"failed"); eq(#QUEUE,0)
    ITEM.container=remote
    PZDevKit.Scenario.scenario("remote equip"):equip(ITEM):run()
    tick(); eq(report().status,"failed"); eq(#QUEUE,0)
end

local function approachWorld()
    local target={getZ=function() return 0 end}
    local adjacent={getX=function() return 12 end,getY=function() return 20 end,getZ=function() return 0 end}
    local source={getOutermostContainer=function(self) return self end,
        getVehiclePart=function() return nil end,getParent=function() return nil end,
        getSourceGrid=function() return target end}
    AdjacentFreeTileFinder={Find=function(square,player)
        eq(square,target); eq(player,PLAYER); return adjacent
    end}
    PLAYER.getCurrentSquare=function()
        return {canReachTo=function(_,square)
            eq(square,target); return PLAYER.x==12.5 and PLAYER.z==0
        end}
    end
    ITEM.container=source
    return source
end

function T.container_approach_waits_for_path_and_loot_panel_before_transfer()
    local source=approachWorld()
    PZDevKit.Scenario.scenario("approach then transfer"):approachContainer(source):transfer(ITEM):run()
    tick(); eq(#QUEUE,1); eq(PATH.x,12.5); eq(PATH.y,20.5)
    eq(ITEM.container,source)
    PLAYER.x=12.5
    drain(); tick(); eq(report().status,"running"); eq(report().steps[2].status,"pending")
    ACCESSIBLE[source]=true
    tick(); tick(); eq(QUEUE[1].src,source); eq(QUEUE[1].dest,INV)
    ITEM.container=INV; drain(); tick(); eq(report().status,"passed")
end

function T.stale_accessible_list_without_physical_reach_never_completes_approach()
    local source=approachWorld()
    ACCESSIBLE[source]=true
    PZDevKit.Scenario.scenario("stale loot panel"):approachContainer(source,.2):transfer(ITEM):run()
    tick(); drain(); tick(); tick(); tick()
    eq(report().status,"failed"); eq(ITEM.container,source)
    eq(report().steps[2].status,"pending")
    assert(report().reason:find("Timeout",1,true))
end

function T.locked_container_approach_stops_before_path_or_transfer()
    local source=approachWorld()
    PLAYER.canAccessContainer=function() return false end
    PZDevKit.Scenario.scenario("locked approach"):approachContainer(source):transfer(ITEM):run()
    tick(); eq(report().status,"failed"); eq(#QUEUE,0); eq(ITEM.container,source)
    assert(report().reason:find("Container is locked",1,true))
end

function T.failed_container_path_cleans_queue_and_never_transfers()
    local source=approachWorld()
    PZDevKit.Scenario.scenario("failed approach"):approachContainer(source):transfer(ITEM):run()
    tick(); PATH.failed()
    local previousAssert=assert
    local failedAsserts=0
    assert=function(condition,...)
        if not condition then failedAsserts=failedAsserts+1 end
        return previousAssert(condition,...)
    end
    tick(); assert=previousAssert
    eq(failedAsserts,0)
    eq(report().status,"failed"); eq(#QUEUE,0); eq(ITEM.container,source)
    eq(report().steps[2].status,"pending")
    assert(report().reason:find("Container approach pathfinding failed",1,true))
end

function T.already_reachable_loot_does_not_path_to_another_adjacent_square()
    local source=approachWorld()
    PLAYER.x=12.5; ACCESSIBLE[source]=true
    AdjacentFreeTileFinder.Find=function() error("Do not move away from accessible loot") end
    PZDevKit.Scenario.scenario("already alongside"):approachContainer(source):transfer(ITEM):run()
    tick(); eq(#QUEUE,0); eq(PATH,nil)
    tick(); eq(#QUEUE,1); eq(QUEUE[1].item,ITEM)
end

function T.container_approach_does_not_cross_floors_or_teleport()
    local source=approachWorld()
    PLAYER.z=1
    PZDevKit.Scenario.scenario("other floor"):approachContainer(source):run()
    tick(); eq(report().status,"failed"); eq(#QUEUE,0); eq(PLAYER.z,1); eq(PLAYER.x,10.5)
    assert(report().reason:find("another floor",1,true))
end

return T
