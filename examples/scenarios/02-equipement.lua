-- Equip an EXISTING inventory item. Replace the type to match your test fixture (params.itemType).
-- Run: python PZDevKit/pzdev.py scenario run PZDevKit/examples/scenarios/02-equipement.lua -P itemType=Base.Hammer
return function(params)
    local fullType=params.itemType or "Base.WalkieTalkie5"
    return PZDevKit.Scenario.scenario("Equiper un objet")
        :equip(fullType,true,false)
        :check("Objet dans la main principale",function(c)
            local item=c.player:getPrimaryHandItem()
            return item~=nil and item:getFullType()==fullType
        end)
end
