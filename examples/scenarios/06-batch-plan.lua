-- Save as Zomboid/Lua/PZPuppet/scenarios/MonMod/campaign.lua.
-- Also copy 04-equipped-fixture.lua as MonMod/equipement.lua.
-- Requires solo -debug and an external report collector implementing the ACK contract.
-- Console: PZDevKit.Scenario.runBatchFile("MonMod/campaign.lua",{playerIndex=0})
-- Each equipment case uses an actual equip action and its own finally cleanup.
-- This plan does not launch a scenario or change the player when loaded.
return function(params)
    return {
        {path="MonMod/equipement.lua",params={itemType=params.firstItem or "Base.Screwdriver"}},
        {path="MonMod/equipement.lua",params={itemType=params.secondItem or "Base.Hammer"}},
    }
end
