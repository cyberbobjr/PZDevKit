-- Screenshots on the spot: the same place in two framings, interface hidden.
-- Run in a game left open by `pzdev sp <Project> --no-quit`:
--   python PZDevKit/pzdev.py film PZDevKit/examples/productions/stills.lua            (PNG in PZDevKit/runs/film/...)
--   python PZDevKit/pzdev.py film PZDevKit/examples/productions/stills.lua --video    (with the video)
require "PZDevKit/Staging"
return function(params)
    params=params or {}
    local close,wide=params.close or 1.5,params.wide or 0.5
    return PZDevKit.Production.production("Captures sur place",{duration=1,countdown=3,immortal=true})
        :frame(close)
        :wait(1.5)
        :mark("serre")
        :screenshot("serre")
        :frame(wide)
        :wait(1.5)
        :mark("large")
        :screenshot("large")
end
