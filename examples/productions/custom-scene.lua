-- Copy to Zomboid/Lua/PZPuppet/scenarios/PZDirector/custom-scene.lua.
-- python PZDevKit/pzdev.py film PZDevKit/examples/productions/custom-scene.lua
require "PZDevKit/Production"
return function()
    return PZDevKit.Production.scene("Mon plan",{duration=15,countdown=5})
        :cue(0,"Ambiance",function(c) PZDevKit.Production.sound(c,"MetaDogBark",5,-5) end)
        :wait(2)
        :moveBy(2,0)
        :cue(8,"Eclair",function(c) PZDevKit.Production.thunder(c,3,-3) end)
        :wait(2)
        :moveBy(0,0)
end
