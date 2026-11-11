-- Save as Zomboid/Lua/PZPuppet/scenarios/MonMod/equipement.lua.
-- Console: PZDevKit.Scenario.runFile("MonMod/equipement.lua",{playerIndex=0},{itemType="Base.Screwdriver"})
return function(params)
    local fullType=params.itemType or "Base.Screwdriver"
    assert(type(fullType)=="string","itemType must be a full item type")
    local D=PZDevKit.World
    return PZDevKit.Scenario.scenario("Generic equipment with fixture")
        :call("SETUP: create item",function(c)
            c.vars.items=D.spawnItem(fullType,1,c.playerIndex)
            c.vars.primary=c.player:getPrimaryHandItem()
            c.vars.secondary=c.player:getSecondaryHandItem()
        end)
        :equip(function(c) return c.vars.items[1] end)
        :check("Exact created item equipped",function(c)
            return c.player:getPrimaryHandItem()==c.vars.items[1]
        end)
        :finally(function(c)
            if c.vars.items then
                c.player:setPrimaryHandItem(c.vars.primary)
                c.player:setSecondaryHandItem(c.vars.secondary)
                for _,item in ipairs(c.vars.items) do D.removeSpawned(item) end
            end
        end)
end
