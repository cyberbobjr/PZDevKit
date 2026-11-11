-- Walk two squares east and back with the real pathfinding, then check the position.
-- Run: python PZDevKit/pzdev.py scenario run PZDevKit/examples/scenarios/01-aller-retour.lua
-- (copied to Zomboid/Lua/PZPuppet/scenarios/pzdev/ of the target game, then PZDevKit.Scenario.runFile).
return function(params)
    local player=getSpecificPlayer(0)
    local x,y,z=player:getX(),player:getY(),player:getZ()
    local distance=params.distance or 2
    return PZDevKit.Scenario.scenario("Aller-retour")
        :walkTo(x+distance,y,z)
        :wait(1)
        :walkTo(x,y,z)
        :check("Position de retour",function(c)
            return PZDevKit.Scenario.Game.near(c.player,x,y,z,0.8)
        end)
end
