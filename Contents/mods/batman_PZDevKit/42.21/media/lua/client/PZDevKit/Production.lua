require "PZDevKit/Game"
require "ISUI/ISUIHandler"

PZDevKit = PZDevKit or {}
local D = PZDevKit.Production or {}
PZDevKit.Production = D
D.VERSION = "0.4.0"
if D.stop then D.stop("Director Lua reload") end

local P = PZDevKit.Scenario
local current
local function number(value, minimum, maximum, label)
    assert(type(value)=="number" and value==value and value>=minimum and value<=maximum,
        label .. " outside allowed range")
    return value
end

local function solo()
    assert(isDebugEnabled(), "PZDirector: lancer le jeu avec -debug")
    assert(not isClient() and not isServer(), "PZDirector: solo uniquement")
end

function D.status()
    return current and P.status() or D.lastReport
end

function D.stop(reason)
    -- Never cancel an unrelated Puppeteer scenario.
    if current then P.stop(reason or "Prise arretee") end
end

local flagMethods = {
    god="isGodMod", ghost="isGhostMode", invisible="isInvisible",
}

local function cleanup(c)
    local t = c.vars.director
    current=nil
    D.lastReport=P.lastReport
    if not t then return end
    local errors = {}
    local function attempt(fn)
        local ok, err = pcall(fn)
        if not ok then errors[#errors+1]=tostring(err) end
    end
    -- All restorations are attempted even if one creation cannot be removed.
    for i=#t.sounds,1,-1 do
        local sound=t.sounds[i]
        attempt(function() sound.emitter:stopSoundLocal(sound.id) end)
    end
    for i=#t.spawned,1,-1 do
        local object=t.spawned[i]
        attempt(function() PZDevKit.World.removeSpawned(object) end)
    end
    if D.restoreActor then attempt(function() D.restoreActor(c) end) end
    if t.observe then
        attempt(function()
            c.player:setDoRender(t.oldRender)
            c.player:setAlpha(c.playerIndex,t.oldAlpha)
            c.player:setTargetAlpha(c.playerIndex,t.oldTargetAlpha)
        end)
    end
    if t.oldFlags then
        attempt(function()
            local restore={}
            for key,old in pairs(t.oldFlags) do
                if c.player[flagMethods[key]](c.player)==t.flags[key] then restore[key]=old end
            end
            PZDevKit.World.setFlags(restore,c.playerIndex)
        end)
    end
    if t.muted~=nil then
        attempt(function()
            if getSoundManager():isUiSoundMuted() then getSoundManager():setUiSoundMuted(t.muted) end
        end)
    end
    if t.hidUI then
        attempt(function()
            if not ISUIHandler.allUIVisible then
                ISUIHandler.allUIVisible=true
                ISUIHandler.setVisibleAllUI(true)
            end
        end)
    end
    if #errors>0 then error("Nettoyage: " .. table.concat(errors," | ")) end
end

-- A genuine Puppeteer scenario, with extra methods on this instance only.
-- Its exact metatable is retained, so runFile/loadScenario also accept it.
function D.scene(name, options)
    options=options or {}
    local duration=number(options.duration or 20,0.1,600,"duration")
    local countdown=number(options.countdown or 5,0,60,"countdown")
    local observe=options.observe==true
    local cues={}
    local scene=P.scenario("PZDirector / " .. name)
    local originalStep=P.Scenario.step
    local sealed=false

    local function update(c)
        local t=c.vars.director
        if not t or not t.started then return true end
        assert(getGameSpeed()==1, "Tournage: reprendre a vitesse normale")
        local elapsed=P.status().duration-t.started
        t.elapsed=elapsed
        if t.observe then c.player:setDoRender(false); c.player:setAlphaAndTarget(c.playerIndex,0) end
        if D.updateActor then D.updateActor(c) end
        while t.cursor<=#cues and cues[t.cursor].at<=elapsed do
            local cue=cues[t.cursor]
            t.cursor=t.cursor+1 -- consume before calling: never replay an errored cue
            print("[PZDirector] " .. name .. " / " .. cue.label)
            cue.callback(c)
            if not current then return false end
        end
        return true
    end

    scene.step=function(self,label,definition)
        local poll=definition.poll
        local wrapped={start=definition.start,timeout=definition.timeout,
            poll=function(c,data)
                if not update(c) then return false end
                return poll(c,data)
            end}
        return originalStep(self,label,wrapped)
    end
    scene.cue=function(self,at,label,callback)
        assert(not self.used and not sealed,"Creer une nouvelle scene")
        number(at,0,duration,"cue time")
        assert(type(label)=="string" and label~="" and type(callback)=="function", "cue: label et fonction requis")
        cues[#cues+1]={at=at,label=label,callback=callback,order=#cues+1}
        return self
    end
    scene.moveBy=function(self,dx,dy,timeout)
        number(dx,-100,100,"dx"); number(dy,-100,100,"dy")
        return self:travelTo(function(c)
            local origin=c.vars.director.origin
            return origin.x+dx,origin.y+dy,origin.z
        end, nil, nil, timeout or 30)
    end
    scene.run=function(self,runOptions)
        solo()
        assert(not self.used,"Creer une nouvelle scene")
        assert(not current,"Une prise est deja en cours")
        if not sealed then
            sealed=true
            self:step("Fin de prise",{timeout=duration+30,poll=function(c)
                return c.vars.director.elapsed>=duration
            end})
        end
        -- The initial context is created on the first tick, but ownership starts now.
        local report=P.Scenario.run(self,runOptions)
        current=report
        D.lastReport=report
        return report
    end

    scene:check("PRE: solo debug, terrain libre, vitesse normale",function(c)
        solo()
        assert(getGameSpeed()==1,"Utiliser la vitesse normale")
        assert(not c.player:getVehicle(),"Sortir du vehicule")
        if options.preflight then options.preflight(c) end
        return true
    end)
    scene:wait(countdown)
    scene:call("CLAP: debut de prise",function(c)
        -- Store restoration data before applying any world or UI change.
        local t={origin={x=c.player:getX(),y=c.player:getY(),z=c.player:getZ()},
            sounds={},spawned={},cursor=1,elapsed=0}
        c.vars.director=t
        if D.captureActor then D.captureActor(c) end
        table.sort(cues,function(a,b) return a.at<b.at or (a.at==b.at and a.order<b.order) end)
        local flags={}
        if options.protect~=false then flags.god=true end
        if observe then flags.ghost=true; flags.invisible=true end
        t.flags=flags
        t.oldFlags=PZDevKit.World.setFlags(flags,c.playerIndex)
        if observe then
            t.oldRender=c.player:getDoRender()
            t.oldAlpha=c.player:getAlpha(c.playerIndex)
            t.oldTargetAlpha=c.player:getTargetAlpha(c.playerIndex)
            t.observe=true
            c.player:setDoRender(false)
            c.player:setAlphaAndTarget(c.playerIndex,0)
        end
        if options.muteUI~=false then
            t.muted=getSoundManager():isUiSoundMuted()
            getSoundManager():setUiSoundMuted(true)
        end
        if options.hideUI~=false and ISUIHandler.allUIVisible then
            t.hidUI=true
            ISUIHandler.allUIVisible=false
            ISUIHandler.setVisibleAllUI(false)
        end
        t.started=P.status().duration
    end)
    scene:finally(cleanup)
    return D.attachActor(scene)
end

-- Loaded outdoor tile, checked without modifying the world.
function D.square(x,y,z)
    local sq=getCell():getGridSquare(math.floor(x),math.floor(y),math.floor(z))
    assert(sq and sq:isOutside() and sq:isFree(false) and not sq:isWaterSquare(),
        "Choisir un terrain exterieur libre et deja charge")
    return sq
end

function D.sound(c,name,dx,dy,loop)
    assert(type(name)=="string" and name~="","Nom de son requis")
    local t=assert(c.vars.director,"Pas de prise active")
    local p=t.origin
    local emitter=getWorld():getFreeEmitter(p.x+(dx or 0),p.y+(dy or 0),p.z)
    local id
    if loop then id=emitter:playSoundLoopedImpl(name) else id=emitter:playSound(name) end
    t.sounds[#t.sounds+1]={emitter=emitter,id=id}
    return id
end

function D.zombie(c,dx,dy,options)
    local t=assert(c.vars.director,"Pas de prise active")
    local p=t.origin
    D.square(p.x+dx,p.y+dy,p.z)
    local zombie=PZDevKit.World.spawnZombie(p.x+dx,p.y+dy,p.z,options)
    t.spawned[#t.spawned+1]=zombie
    return zombie
end

function D.thunder(c,dx,dy)
    local p=c.vars.director.origin
    getClimateManager():getThunderStorm():triggerThunderEvent(p.x+(dx or 0),p.y+(dy or 0),true,true,true)
end

require "PZDevKit/Actions"
return D
