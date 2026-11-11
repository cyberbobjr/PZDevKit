-- Game - real player actions of the scenario engine (formerly PZPuppet_Game.lua).
require "PZDevKit/Scenario"
require "PZDevKit/World"
require "TimedActions/ISTimedActionQueue"
require "Vehicles/TimedActions/ISPathFindAction"
require "TimedActions/ISInventoryTransferUtil"
require "TimedActions/ISOpenCloseDoor"
require "ISUI/ISInventoryPaneContextMenu"
require "Util/AdjacentFreeTileFinder"

local P = PZDevKit.Scenario
local S = P.Scenario
local Game = {}
P.Game = Game

function Game.queueSize(player)
    local queue = ISTimedActionQueue.queues[player]
    return queue and #queue.queue or 0
end

function Game.cancel(context)
    if context.queueOwned then ISTimedActionQueue.clear(context.player) end
    context.queueOwned = false
end

function Game.interrupted(context, manualStop)
    local player = context.player
    if getSpecificPlayer(context.playerIndex) ~= player then return "Local player changed/disconnected" end
    if player:isDead() then return "Player died" end
    if player:isAsleep() then return "Player fell asleep" end
    if manualStop and (player:pressedMovement(false) or player:pressedCancelAction()) then
        return "Manual player input"
    end
end

local function coordinates(x, y, z)
    local values={x,y,z}
    for i=1,3 do
        local v=values[i]
        assert(type(v)=="number" and v==v and math.abs(v)<math.huge, "Invalid coordinates")
    end
end

function Game.near(player, x, y, z, radius)
    coordinates(x,y,z)
    local dx,dy = player:getX()-x,player:getY()-y
    return math.floor(player:getZ())==math.floor(z) and dx*dx+dy*dy <= radius*radius
end

-- selector: a full item type, an existing InventoryItem, or function(context).
function Game.item(context, selector)
    local item
    if type(selector)=="function" then item=selector(context)
    elseif type(selector)=="string" then item=context.player:getInventory():getFirstTypeRecurse(selector)
    else item=selector end
    assert(item, "Item not found: " .. tostring(selector))
    return item
end

local function accessibleContainer(context,container)
    if container:getOutermostContainer()==context.player:getInventory() then return true end
    -- Same nearby/locked-container filtering as the vanilla inventory menu.
    local nearby=ISInventoryPaneContextMenu.getContainers(context.player)
    return nearby and nearby:contains(container)
end

local function actionStep(self, label, callback, predicate, timeout)
    assert(type(callback)=="function" and type(predicate)=="function", "Interaction needs a callback and result predicate")
    return self:step(label, {
        start=function(context,data)
            assert(Game.queueSize(context.player)==0, "Player action queue is busy")
            -- Claimed before callback: cleanup also runs if it queues then throws.
            context.queueOwned=true
            callback(context,data)
        end,
        poll=function(context,data)
            if data.failure then return false,data.failure end
            local matches = predicate(context,data)
            if Game.queueSize(context.player)==0 and matches==true then
                context.queueOwned=false
                return true
            end
            return false
        end,
        timeout=timeout,
    })
end

-- Uses the SAME callbacks as context menus; never assume an empty queue is success.
function S:interact(label, callback, predicate, timeout)
    return actionStep(self,label,callback,predicate,timeout)
end

-- Generic adapter for any vanilla/mod timed action with a visible postcondition.
function S:act(label, factory, predicate, timeout)
    assert(type(factory)=="function", "act needs an action factory")
    return actionStep(self,label,function(context,data)
        local action=factory(context)
        assert(action and action.character==context.player, "Action must belong to the selected player")
        assert(not action.ignoreAction, "Action is marked ignoreAction")
        -- Observe only this instance. Vanilla/mod class methods remain untouched.
        local previousStop=action.stop
        action.stop=function(instance,...)
            data.failure="Timed action stopped: " .. label
            return previousStop(instance,...)
        end
        ISTimedActionQueue.add(action)
    end,predicate,timeout)
end

function S:walkTo(x,y,z,timeout)
    z=z or 0
    coordinates(x,y,z)
    return actionStep(self,string.format("Walk %.2f %.2f %.0f",x,y,z),function(context,data)
        assert(not context.player:getVehicle(), "Exit the vehicle before walking")
        assert(not getGameSpeed or getGameSpeed()<=2, "Use normal game speed for pathfinding")
        assert(getCell():getGridSquare(math.floor(x),math.floor(y),math.floor(z)), "Target square is not loaded")
        local action=ISPathFindAction:pathToLocationF(context.player,x,y,z)
        action:setOnFail(function() data.failure="Pathfinding failed" end)
        ISTimedActionQueue.add(action)
    end,function(context)
        return Game.near(context.player,x,y,z,0.8)
    end,timeout or 60)
end

function S:walkToVehicle(selector,area,timeout)
    return actionStep(self,"Walk to vehicle",function(context,data)
        data.vehicle=type(selector)=="function" and selector(context) or selector
        assert(data.vehicle and not data.vehicle:isRemovedFromWorld(), "Vehicle not found")
        assert(not context.player:getVehicle(), "Exit the vehicle before walking")
        if area then
            assert(data.vehicle:getScript():getAreaById(area), "Vehicle area not found: " .. area)
        end
        local action=area and ISPathFindAction:pathToVehicleArea(context.player,data.vehicle,area)
            or ISPathFindAction:pathToVehicleAdjacent(context.player,data.vehicle)
        action:setOnFail(function() data.failure="Vehicle pathfinding failed" end)
        action:setOnComplete(function() data.reached=true end)
        ISTimedActionQueue.add(action)
    end,function(_,data) return data.reached==true end,timeout or 60)
end

-- Stream a distant route in short, loaded waypoints; no teleportation.
function S:travelTo(x,y,z,timeout)
    local selector=type(x)=="function" and x or nil
    z=z or 0
    if not selector then coordinates(x,y,z) end
    local label=selector and "Travel to selected target" or string.format("Travel %.2f %.2f %.0f",x,y,z)
    return actionStep(self,label,function(context)
        if selector then x,y,z=selector(context); z=z or 0; coordinates(x,y,z) end
        assert(not context.player:getVehicle(), "Exit the vehicle before walking")
        assert(math.floor(context.player:getZ())==math.floor(z), "travelTo stays on the same floor; use walkTo for stairs")
    end,function(context,data)
        local player=context.player
        if Game.queueSize(player)>0 then return false end
        if Game.near(player,x,y,z,0.8) then return true end
        if data.goal then
            assert(Game.near(player,data.goal.x,data.goal.y,z,0.8), "Waypoint action ended without reaching its target")
        end
        assert(not getGameSpeed or getGameSpeed()<=2, "Use normal game speed for pathfinding")
        local dx,dy=x-player:getX(),y-player:getY()
        local distance=math.sqrt(dx*dx+dy*dy)
        local length=math.min(distance,24)
        local gx,gy=player:getX()+dx/distance*length,player:getY()+dy/distance*length
        assert(getCell():getGridSquare(math.floor(gx),math.floor(gy),math.floor(z)), "Next waypoint is not loaded")
        data.goal={x=gx,y=gy}
        local action=ISPathFindAction:pathToLocationF(player,gx,gy,z)
        action:setOnFail(function() data.failure="Waypoint pathfinding failed" end)
        ISTimedActionQueue.add(action)
        return false
    end,timeout or 240)
end

function S:click(selector,predicate,timeout)
    return actionStep(self,"Click UI button",function(context)
        local button=type(selector)=="function" and selector(context) or selector
        assert(button and button.forceClick and button.isEnabled, "Expected an ISButton")
        assert(button:getIsVisible() and (not button.isReallyVisible or button:isReallyVisible()), "Button is not visible")
        assert(button:isEnabled(), "Button is disabled")
        button:forceClick()
    end,predicate,timeout)
end

function Game.nearestVehicle(context,predicate,radius)
    radius=radius or 40
    local vehicles=getCell():getVehicles()
    local best,distance
    for i=0,vehicles:size()-1 do
        local vehicle=vehicles:get(i)
        local dx,dy=vehicle:getX()-context.player:getX(),vehicle:getY()-context.player:getY()
        local d=dx*dx+dy*dy
        if d<=radius*radius and not vehicle:isRemovedFromWorld() and predicate(vehicle)
            and (not distance or d<distance) then best,distance=vehicle,d end
    end
    return best
end

function S:equip(selector,primary,twoHands,timeout)
    primary=primary~=false
    return actionStep(self,"Equip item",function(context,data)
        data.item=Game.item(context,selector)
        assert(data.item:getContainer() and accessibleContainer(context,data.item:getContainer()),
            "Item container is not accessible; walk next to it first")
        ISInventoryPaneContextMenu.equipWeapon(data.item,primary,twoHands==true,context.playerIndex)
    end,function(context,data)
        local player=context.player
        if twoHands then return player:getPrimaryHandItem()==data.item and player:getSecondaryHandItem()==data.item end
        if primary then return player:getPrimaryHandItem()==data.item end
        return player:getSecondaryHandItem()==data.item
    end,timeout)
end

-- Resolve a real adjacent square, walk there, then wait for the vanilla loot
-- panel to expose the container. No teleportation or relaxed transfer checks.
function S:approachContainer(selector,timeout)
    return actionStep(self,"Approach container",function(context,data)
        data.container=type(selector)=="function" and selector(context) or selector
        local container=data.container
        assert(container and container.getOutermostContainer,"Expected an ItemContainer")
        assert(context.player:canAccessContainer(container),"Container is locked")
        if container:getOutermostContainer()==context.player:getInventory() then return end
        assert(not context.player:getVehicle(),"Exit the vehicle before approaching a container")
        assert(not getGameSpeed or getGameSpeed()<=2,"Use normal game speed for pathfinding")
        assert(not container:getVehiclePart(),"Use walkToVehicle for vehicle containers")
        local parent=container:getParent()
        local target=parent and parent:getSquare() or container:getSourceGrid()
        assert(target,"Container has no loaded world square")
        data.target=target
        assert(math.floor(context.player:getZ())==target:getZ(),"Container is on another floor; use stairs first")
        local current=context.player:getCurrentSquare()
        if current and current:canReachTo(target) and accessibleContainer(context,container)==true then
            return -- Already reachable through the same vanilla loot filtering.
        end
        local adjacent=assert(AdjacentFreeTileFinder.Find(target,context.player),"No reachable adjacent container square")
        local action=ISPathFindAction:pathToLocationF(context.player,adjacent:getX()+0.5,adjacent:getY()+0.5,adjacent:getZ())
        action:setOnFail(function() data.failure="Container approach pathfinding failed" end)
        ISTimedActionQueue.add(action)
    end,function(context,data)
        if data.container:getOutermostContainer()==context.player:getInventory() then return true end
        local current=context.player:getCurrentSquare()
        return current~=nil and current:canReachTo(data.target)
            and context.player:canAccessContainer(data.container) and accessibleContainer(context,data.container)==true
    end,timeout or 45)
end

function S:transfer(selector,destination,timeout)
    return actionStep(self,"Transfer item",function(context,data)
        data.item=Game.item(context,selector)
        data.destination=type(destination)=="function" and destination(context) or destination
        data.destination=data.destination or context.player:getInventory()
        local source=data.item:getContainer()
        assert(source,"Item has no source container")
        assert(accessibleContainer(context,source) and accessibleContainer(context,data.destination),
            "Container is not accessible; walk next to it first")
        if source~=data.destination then
            ISTimedActionQueue.add(ISInventoryTransferUtil.newInventoryTransferAction(
                context.player,data.item,source,data.destination))
        end
    end,function(_,data) return data.item:getContainer()==data.destination end,timeout)
end

function S:door(selector,open,timeout)
    assert(type(open)=="boolean", "door needs true=open or false=closed")
    return actionStep(self,open and "Open door" or "Close door",function(context,data)
        data.door=type(selector)=="function" and selector(context) or selector
        assert(data.door and instanceof(data.door,"IsoDoor"), "Expected an IsoDoor")
        local square=data.door:getSquare()
        assert(square and Game.near(context.player,square:getX()+0.5,square:getY()+0.5,square:getZ(),2),
            "Walk next to the door first")
        if data.door:IsOpen()~=open then ISTimedActionQueue.add(ISOpenCloseDoor:new(context.player,data.door)) end
    end,function(_,data) return data.door:IsOpen()==open end,timeout)
end

-- Teleport step (formerly in PZPuppet_Debug.lua): PZDevKit.World.teleport, then wait for the loaded square.
function S:teleport(x,y,z,timeout)
    coordinates(x,y,z or 0)
    z=z or 0
    assert(z==math.floor(z),"z must be an integer")
    x,y=math.floor(x),math.floor(y)
    return self:step("SETUP: teleport",{timeout=timeout or 60,
        start=function(c) PZDevKit.World.teleport(x,y,z,c.playerIndex) end,
        poll=function(c)
            return Game.near(c.player,x,y,z,0.8) and getCell():getGridSquare(x,y,z)~=nil
        end})
end

-- Stop before a world switch. Old scenario/player references must not survive.
local function disconnect() P.stop("Game exited/disconnected") end
if P._disconnect then Events.OnDisconnect.Remove(P._disconnect) end
P._disconnect=disconnect
Events.OnDisconnect.Add(disconnect)
return Game
