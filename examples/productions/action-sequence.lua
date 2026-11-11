-- Reloadable showcase: loaded pistol, spare 9mm ammo, apple, open water bottle.
-- Copy to Zomboid/Lua/PZPuppet/scenarios/PZDirector/action-sequence.lua.
-- python PZDevKit/pzdev.py film PZDevKit/examples/productions/action-sequence.lua
require "PZDevKit/Production"
return function(params)
    params=params or {}
    local gun=params.weapon or "Base.Pistol"
    local food=params.food or "Base.Apple"
    local drink=params.drink or "Base.WaterBottle"
    local scene=PZDevKit.Production.scene("Gestes et actions",{duration=35,countdown=5,preflight=function(c)
            PZDevKit.Scenario.Game.item(c,gun)
            PZDevKit.Scenario.Game.item(c,food)
            PZDevKit.Scenario.Game.item(c,drink)
        end})
        :emote("wavehi")
        :runBy(3,0)
        :crouch(true)
        :sneakBy(0,0)
        :stand()
        :emote("stop")
        :equip(gun,true,false)
        :shootAt(function(c)
            local p=c.vars.director.origin
            return p.x+6,p.y,p.z
        end,{shots=1})
        :reload(gun)
        :eat(food,.5)
        :drink(drink,.25)
    -- Optional actual nearby IsoDoor or selector function(c).
    if params.door then scene:openDoor(params.door):wait(2):closeDoor(params.door) end
    return scene
end
