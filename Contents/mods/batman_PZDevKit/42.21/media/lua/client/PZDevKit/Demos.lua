require "PZDevKit/Production"
local D = PZDevKit.Production

local function terrain(c)
    local p=c.player
    assert(math.floor(p:getZ())==0,"Demonstration au niveau du sol")
    -- Keep the framing and scripted route clear; no teleportation or demolition.
    for dx=-6,6 do
        for dy=-6,2 do D.square(p:getX()+dx,p:getY()+dy,0) end
    end
end

function D.demo(params)
    params=params or {}
    return D.scene("L'approche",{duration=20,countdown=params.countdown,
        hideUI=params.hideUI,preflight=terrain})
        :cue(0,"Un cri au loin",function(c) D.sound(c,"MetaScream",-6,-6) end)
        :cue(2,"Apparition",function(c)
            c.vars.zombie=D.zombie(c,-5,-5,{invulnerable=true})
            PZDevKit.World.freezeZombie(c.vars.zombie,true)
        end)
        :wait(3)
        :crouch(true)
        :sneakBy(3,0)
        :stand()
        :check("Personnage au premier repere",function(c)
            local p=c.vars.director.origin
            return PZDevKit.Scenario.Game.near(c.player,p.x+3,p.y,p.z,0.8)
        end)
        :cue(7,"Le zombie approche",function(c)
            assert(c.vars.zombie,"Zombie non cree")
            PZDevKit.World.freezeZombie(c.vars.zombie,false)
            c.vars.zombie:pathToCharacter(c.player)
        end)
        :cue(10,"Tonnerre",function(c) D.thunder(c,-5,-5) end)
        :emote("stop")
        :wait(2)
        :runBy(0,0)
        :check("Personnage revenu au point de depart",function(c)
            local p=c.vars.director.origin
            return PZDevKit.Scenario.Game.near(c.player,p.x,p.y,p.z,0.8)
        end)
end

function D.observation(params)
    params=params or {}
    return D.scene("Traversees",{duration=20,countdown=params.countdown,
        hideUI=params.hideUI,observe=true,preflight=terrain})
        :cue(0,"Plan d'ambiance",function(c) D.sound(c,"MetaDogBark",6,-6) end)
        :cue(2,"Premier passage",function(c)
            c.vars.first=D.zombie(c,6,-4,{invulnerable=true})
            local p=c.vars.director.origin
            c.vars.first:pathToLocationF(p.x-6,p.y-4,p.z)
        end)
        :cue(6,"Second passage",function(c)
            c.vars.second=D.zombie(c,6,-2,{invulnerable=true})
            local p=c.vars.director.origin
            c.vars.second:pathToLocationF(p.x-6,p.y-2,p.z)
        end)
        :cue(10,"Tonnerre",function(c) D.thunder(c,4,-4) end)
        :wait(19)
        :check("Deux figurants crees",function(c)
            return c.vars.first~=nil and c.vars.second~=nil
        end)
        :check("Point de vue reste immobile",function(c)
            local p=c.vars.director.origin
            return PZDevKit.Scenario.Game.near(c.player,p.x,p.y,p.z,0.1)
        end)
end

PZDevKit.Scenario.register("PZDevKit.Production.demo",D.demo,true)
PZDevKit.Scenario.register("PZDevKit.Production.observation",D.observation,true)
return D
