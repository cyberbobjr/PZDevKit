-- Place in a separate test mod: 42.21/media/lua/client/MonMod/PZTests/Equipment.lua.
-- Its mod.info requires batman_PZDevKit and the tested mod.
-- Console: PZDevKit.Scenario.run("MonMod.equipment",{playerIndex=0},{itemType="Base.Screwdriver"})
require "PZDevKit/Game"
PZDevKit.Scenario.register("MonMod.equipment",function(params)
    local fullType=params.itemType or "Base.Screwdriver"
    return PZDevKit.Scenario.scenario("MonMod equipment")
        :equip(fullType)
        :check("Expected item equipped",function(c)
            local item=c.player:getPrimaryHandItem()
            return item~=nil and item:getFullType()==fullType
        end)
end,true)
