-- Copy to Zomboid/Lua/PZPuppet/scenarios/PZDirector/observation.lua.
-- python PZDevKit/pzdev.py film PZDevKit/examples/productions/observation.lua
require "PZDevKit/Demos"
return function(params)
    return PZDevKit.Production.observation(params)
end
