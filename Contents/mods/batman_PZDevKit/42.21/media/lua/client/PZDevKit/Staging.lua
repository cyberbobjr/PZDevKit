-- Casting, blocking and light: preparation for a film, not progression helpers.
require "PZDevKit/Production"
local D,P=PZDevKit.Production,PZDevKit.Scenario
D.VERSION="0.4.0"

D.COSTUMES={
    field={"Base.Tshirt_ArmyGreen","Base.Jacket_ArmyCamoGreen","Base.Trousers_CamoGreen",
        "Base.Shoes_ArmyBoots","Base.Hat_BonnieHat_OliveDrab","Base.Bag_ALICEpack_Army"},
    civilian={"Base.Tshirt_ArmyGreen","Base.Trousers_Denim","Base.Shoes_BlackBoots",
        "Base.Bag_ALICEpack"},
}

local function range(value,min,max,label)
    assert(type(value)=="number" and value==value and value>=min and value<=max,label..": valeur invalide")
    return value
end
local function square(x,y,z) return getCell():getGridSquare(math.floor(x),math.floor(y),z) end
local function free(sq,outside)
    return sq~=nil and sq:isFree(false) and not sq:isWaterSquare()
        and (outside==nil or sq:isOutside()==outside)
end

-- Public vanilla zoom controls only; 0 returns the current target level.
local function zoom(core,index,target)
    local current=core:getNextZoom(index,0)
    for _=1,24 do
        local direction=target>current and 1 or -1
        local nextLevel=core:getNextZoom(index,direction)
        if math.abs(nextLevel-target)>=math.abs(current-target) then break end
        core:doZoomScroll(index,direction)
        current=nextLevel
    end
end

local function removeLights(t)
    t.blinking=nil; t.namedLights=nil
    for i=#t.lights,1,-1 do
        local light=t.lights[i]
        light:setActive(false)
        getCell():removeLamppost(light)
        table.remove(t.lights,i)
    end
end

local actorCheats={
    god={"isGodMod","setGodMod"},ghost={"isGhostMode","setGhostMode"},
    invisible={"isInvisible","setInvisible"},noclip={"isNoClip","setNoClip"},
    noAttack={"isZombiesDontAttack","setZombiesDontAttack"},
    instant={"isTimedActionInstantCheat","setTimedActionInstantCheat"},
    ammo={"isUnlimitedAmmo","setUnlimitedAmmo"},
}

local function restoreAmbient(c)
    local t=c.vars.production
    for zombie,old in pairs(t.ambient) do
        -- Virtualized zombies no longer belong to the loaded set.
        if zombie:getCurrentSquare() then
            zombie:setUseless(old.useless)
            zombie:setDoRender(old.render)
            zombie:setSolid(old.solid); zombie:setCollidable(old.collidable)
            zombie:setAlpha(c.playerIndex,old.alpha)
            zombie:setTargetAlpha(c.playerIndex,old.targetAlpha)
        end
    end
    t.ambient={}
end

local function updateSet(c)
    local t=c.vars.production
    if not t then return end
    if t.lockedHour then getGameTime():setTimeOfDay(t.lockedHour) end
    if t.blinking then
        local now=P.status().duration
        for light,b in pairs(t.blinking) do
            local on=math.floor((now-b.start)/b.period)%2==0
            if b.on~=on then light:setActive(on); b.on=on end
        end
    end
    if not t.block then return end
    if t.isolate then
        local list=getCell():getZombieList()
        for i=0,list:size()-1 do
            local zombie=list:get(i)
            if not t.extras[zombie] and zombie:getZ()==t.block.z
                and math.abs(zombie:getX()-c.player:getX())<=t.isolate
                and math.abs(zombie:getY()-c.player:getY())<=t.isolate then
                if not t.ambient[zombie] then
                    t.ambient[zombie]={useless=zombie:isUseless(),render=zombie:getDoRender(),
                        solid=zombie:isSolid(),collidable=zombie:isCollidable(),
                        alpha=zombie:getAlpha(c.playerIndex),targetAlpha=zombie:getTargetAlpha(c.playerIndex)}
                end
                -- Only the cast participates. Existing zombies are retained and restored.
                zombie:setUseless(true); zombie:setDoRender(false)
                zombie:setSolid(false); zombie:setCollidable(false)
                zombie:setAlphaAndTarget(c.playerIndex,0)
            end
        end
    end
    for zombie,extra in pairs(t.extras) do
        if extra.behavior=="hunt" and not zombie:isDead() then
            zombie:setUseless(false)
            zombie:setTarget(c.player)
            -- Let vanilla lunge/attack finish; repeatedly restarting a nearby path
            -- can turn an encounter into a succession of interrupted approaches.
            local dx,dy=zombie:getX()-c.player:getX(),zombie:getY()-c.player:getY()
            if not extra.nextPath or (dx*dx+dy*dy>16 and P.status().duration>=extra.nextPath) then
                zombie:pathToCharacter(c.player)
                extra.nextPath=P.status().duration+2
            end
        end
    end
end

local function restore(c)
    local t=c.vars.production
    if not t then return end
    local errors={}
    local function attempt(fn)
        local ok,err=pcall(fn)
        if not ok then errors[#errors+1]=tostring(err) end
    end
    attempt(function() restoreAmbient(c) end)
    attempt(function() removeLights(t) end)
    for _,win in ipairs(t.windows or {}) do
        attempt(function() UIManager.RemoveElement(win.javaObj) end)
    end
    t.windows=nil
    for page,old in pairs(t.pages or {}) do
        attempt(function()
            page:setX(old.x); page:setY(old.y); page:setWidth(old.w); page:setHeight(old.h)
            if old.pin then page:setPinned() else page:collapse() end
        end)
    end
    t.pages=nil
    if t.containerOutline~=nil then
        attempt(function() getCore():setOptionDoContainerOutline(t.containerOutline) end)
        t.containerOutline=nil
    end
    for _,window in ipairs(t.radioWindows or {}) do attempt(function() window:setVisible(true) end) end
    t.radioWindows=nil
    if t.infoPanel~=nil then
        attempt(function() getPlayerInfoPanel(c.playerIndex):setVisible(t.infoPanel) end)
        t.infoPanel=nil
    end
    if t.debugConsole~=nil then
        attempt(function() UIManager.getDebugConsole():setVisible(t.debugConsole) end)
        t.debugConsole=nil
    end
    local p=c.player
    -- Stashed inventory first: the original clothes must be back before they are worn again.
    if t.stash then
        attempt(function()
            local inventory,bag=p:getInventory(),t.stash.bag
            local box=bag:getItemContainer()
            local list,items=box:getItems(),{}
            for i=0,list:size()-1 do items[#items+1]=list:get(i) end
            -- AddItem moves an item out of its previous container (ItemContainer.java:444).
            for _,item in ipairs(items) do inventory:AddItem(item) end
            assert(box:getItems():isEmpty(),"Sac de rangement non vide")
            inventory:Remove(bag)
            t.stash=nil
        end)
    end
    if t.cheats then
        for key,old in pairs(t.cheats) do
            attempt(function() p[actorCheats[key][2]](p,old) end)
        end
    end
    if t.cast then
        attempt(function()
            p:setPrimaryHandItem(t.primary); p:setSecondaryHandItem(t.secondary)
            local worn=p:getWornItems()
            for i=worn:size()-1,0,-1 do p:removeWornItem(worn:get(i):getItem(),false) end
            for _,old in ipairs(t.wardrobe) do p:setWornItem(old.location,old.item,false) end
            p:getHumanVisual():setHairModel(t.hair)
            p:resetModelNextFrame()
        end)
    end
    for i=#t.items,1,-1 do
        local item=t.items[i]
        attempt(function() PZDevKit.World.removeSpawned(item) end)
    end
    attempt(function()
        local core=getCore()
        zoom(core,c.playerIndex,t.zoom)
        core:setAutoZoom(c.playerIndex,t.autoZoom)
        core:setOptionPanCameraWhileAiming(t.pan)
    end)
    attempt(function() PZDevKit.World.setTime(t.hour) end)
    attempt(function() PZDevKit.World.teleport(t.origin.x,t.origin.y,t.origin.z,c.playerIndex) end)
    assert(#errors==0,"Nettoyage de production: "..table.concat(errors," | "))
end

local function prop(c,spec)
    if type(spec)=="string" then spec={type=spec} end
    assert(type(spec)=="table" and type(spec.type)=="string","Accessoire: type requis")
    local item=PZDevKit.World.spawnItem(spec.type,1,c.playerIndex)[1]
    local t=c.vars.production
    t.items[#t.items+1]=item
    if spec.charge then item:setUsedDelta(range(spec.charge,0,1,"charge")) end
    if spec.radio then
        local data=item:getDeviceData()
        assert(data,"Accessoire radio requis")
        data:setHasBattery(true); data:setPower(1); data:setIsTurnedOn(false)
        if spec.radio.channel then data:setChannel(spec.radio.channel) end
        data:setDeviceVolume(spec.radio.volume or 0.65)
    end
    return item
end

-- No player lookup or mutation during construction.
function D.production(name,options)
    options=options or {}
    -- A production actor must be visible, collidable and vulnerable even when
    -- the dedicated debug save was opened with cheats already enabled.
    local sceneOptions={}
    for key,value in pairs(options) do sceneOptions[key]=value end
    sceneOptions.protect=false
    local targetZoom=range(options.zoom or 0.75,0.25,3,"zoom")
    -- immortal=true: the actor stays visible, collidable and attacked on screen, but cannot be
    -- hurt or killed (god mode only; ghost/invisible stay off). Restored with the other cheats.
    local immortal=options.immortal==true
    local scene=D.scene(name,sceneOptions)
    local originalStep=scene.step
    scene.step=function(self,label,definition)
        local poll=definition.poll
        return originalStep(self,label,{start=definition.start,timeout=definition.timeout,
            poll=function(c,data) updateSet(c); return poll(c,data) end})
    end
    scene:call("REGIE: conserver acteur, camera et plateau",function(c)
        local core=getCore()
        local t={items={},lights={},props={},wardrobe={},ambient={},extras={},namedExtras={},cheats={},
            origin=PZDevKit.World.position(c.playerIndex),hour=getGameTime():getTimeOfDay(),
            zoom=core:getNextZoom(c.playerIndex,0),autoZoom=core:getAutoZoom(c.playerIndex),
            pan=core:getOptionPanCameraWhileAiming()}
        c.vars.production=t
        for key,methods in pairs(actorCheats) do
            t.cheats[key]=c.player[methods[1]](c.player)
            c.player[methods[2]](c.player,false)
            assert(not c.player[methods[1]](c.player),"Acteur: cheat encore actif / "..key)
        end
        if immortal then c.player:setGodMod(true) end
        core:setAutoZoom(c.playerIndex,false)
        core:setOptionPanCameraWhileAiming(false)
        zoom(core,c.playerIndex,targetZoom)
    end)
    scene:finally(restore)

    scene.cast=function(self,definition)
        definition=definition or {}
        local clothes=definition.clothes or D.COSTUMES[definition.costume or "field"]
        assert(type(clothes)=="table" and #clothes>0,"Costume inconnu ou vide")
        return self:call("CASTING: "..(definition.name or "acteur principal"),function(c)
            local t,p=c.vars.production,c.player
            assert(not t.cast,"Un seul casting par production")
            t.primary=p:getPrimaryHandItem(); t.secondary=p:getSecondaryHandItem()
            t.hair=p:getHumanVisual():getHairModel()
            local worn=p:getWornItems()
            for i=0,worn:size()-1 do
                local w=worn:get(i)
                t.wardrobe[#t.wardrobe+1]={location=w:getLocation(),item=w:getItem()}
            end
            t.cast=true -- ownership is recorded before the first mutation
            local costumes={}
            for _,fullType in ipairs(clothes) do
                local item=prop(c,fullType)
                local location=item:getBodyLocation() or item:canBeEquipped()
                assert(location,"Objet non portable: "..fullType)
                costumes[#costumes+1]={item=item,location=location}
            end
            for i=worn:size()-1,0,-1 do p:removeWornItem(worn:get(i):getItem(),false) end
            for _,costume in ipairs(costumes) do p:setWornItem(costume.location,costume.item,false) end
            p:resetModelNextFrame()
            for _,costume in ipairs(costumes) do
                assert(p:getWornItems():contains(costume.item),"Costume non porte")
            end
            if definition.primary then
                t.props.primary=prop(c,definition.primary); p:setPrimaryHandItem(t.props.primary)
            end
            if definition.secondary then
                t.props.secondary=prop(c,definition.secondary); p:setSecondaryHandItem(t.props.secondary)
            end
            print("[PZDirector] casting="..(definition.name or "acteur").." costume="..(definition.costume or "custom"))
        end)
    end

    scene.activate=function(self,selector,wanted)
        assert(type(wanted)=="boolean","Etat d'activation requis")
        return self:interact("ACCESSOIRE: activation verifiee",function(c)
            local item=P.Game.item(c,selector)
            assert(item:canBeActivated(),"Accessoire non activable")
            -- Equipping a vanilla lamp may already have switched it on.
            if item:isActivated()~=wanted then ISInventoryPaneContextMenu.onActivateItem(item,c.playerIndex) end
        end,function(c)
            return P.Game.item(c,selector):isActivated()==wanted
        end,5)
    end

    scene.location=function(self,label,definition)
        local anchor=assert(definition.point,"Point de decor requis")
        local radius=range(definition.radius or 4,0,6,"rayon de placement")
        local length=range(definition.travelTiles or 4,0,16,"trajet de plateau")
        assert(radius==math.floor(radius) and length==math.floor(length),"Placement entier requis")
        local timeout=range(definition.timeout or 60,1,120,"delai de chargement")
        return self:call("LIBERER LE PLATEAU PRECEDENT",function(c)
                restoreAmbient(c); c.vars.production.block=nil
                c.vars.production.lockedHour=nil; c.vars.production.isolate=nil
                for _ in pairs(c.vars.production.namedExtras) do
                    error("Retirer les figurants avant de changer de decor")
                end
            end):teleport(anchor.x,anchor.y,anchor.z,timeout)
            :await("DECOR CHARGE: "..label,function()
                -- Underground levels may have no tiles outside their rooms.
                -- Requiring distant corner squares would wait for nonexistent floors.
                local sq=square(anchor.x,anchor.y,anchor.z)
                return sq~=nil and sq:getChunk()~=nil
            end,timeout)
            :call("BLOCKING: position et trajet praticables / "..label,function(c)
                local best,bestDistance
                for r=0,radius do
                    for dx=-r,r do for dy=-r,r do
                        if math.max(math.abs(dx),math.abs(dy))==r then
                            local x,y=math.floor(anchor.x)+dx,math.floor(anchor.y)+dy
                            local start=square(x,y,anchor.z)
                            if free(start,definition.outside) then
                                for _,dir in ipairs({{1,0},{0,1},{-1,0},{0,-1}}) do
                                    local previous=start
                                    local valid=true
                                    for n=1,length do
                                        local nextSquare=square(x+dir[1]*n,y+dir[2]*n,anchor.z)
                                        if not free(nextSquare,definition.outside) or previous:isBlockedTo(nextSquare) then
                                            valid=false; break
                                        end
                                        previous=nextSquare
                                    end
                                    local distance=dx*dx+dy*dy
                                    if valid and (not best or distance<bestDistance) then
                                        bestDistance=distance
                                        best={x=x,y=y,z=anchor.z,
                                            dx=dir[1]*length,dy=dir[2]*length}
                                    end
                                end
                            end
                        end
                    end end
                    if best then break end
                end
                assert(best,"Aucun blocking sur decor: "..label)
                c.vars.production.block=best
                removeLights(c.vars.production)
                if definition.hour~=nil then
                    c.vars.production.lockedHour=range(definition.hour,0,23.999,"heure de plateau")
                    PZDevKit.World.setTime(definition.hour)
                end
                c.vars.production.isolate=definition.isolate and range(definition.isolate,8,80,"zone de plateau")
                PZDevKit.World.teleport(best.x,best.y,best.z,c.playerIndex)
                print("[PZDirector] plateau="..label.." x="..best.x.." y="..best.y.." z="..best.z)
            end)
            :await("ACTEUR EN PLACE: "..label,function(c)
                local b=c.vars.production.block
                local sq=c.player:getCurrentSquare()
                return P.Game.near(c.player,b.x,b.y,b.z,0.8) and sq~=nil
                    and sq:getX()==math.floor(c.player:getX())
                    and sq:getY()==math.floor(c.player:getY())
                    and sq:getZ()==math.floor(c.player:getZ())
            end,timeout)
            :call("AXE: "..label,function(c)
                local p,b=c.player,c.vars.production.block
                c.vars.director.origin={x=p:getX(),y=p:getY(),z=p:getZ()}
                if length>0 then p:faceLocation(b.x+b.dx,b.y+b.dy) end
            end)
    end

    scene.extra=function(self,label,definition)
        assert(type(label)=="string" and label~="","Nom de figurant requis")
        local e=definition or {}
        local dx=range(e.dx or 0,-30,30,"figurant x")
        local dy=range(e.dy or 0,-30,30,"figurant y")
        local behind=e.behind and range(e.behind,2,20,"distance du poursuivant")
        assert(e.speed==nil or e.speed=="fast" or e.speed=="sprint","Allure de figurant inconnue")
        local side=range(e.side or 0,-8,8,"decalage lateral")
        -- Native poses of addZombiesInOutfit: lying as a corpse, crawling or sitting against a wall.
        for _,flag in ipairs({"fakeDead","crawler","sitting"}) do
            assert(e[flag]==nil or type(e[flag])=="boolean",flag.." doit etre booleen")
        end
        assert(e.at==nil or (type(e.at)=="table" and e.at.x and e.at.y),"Position absolue {x,y,z} attendue")
        return self:call("FIGURANT: "..label,function(c)
            local t,o=c.vars.production,c.vars.director.origin
            assert(not t.namedExtras[label],"Figurant deja distribue")
            local x,y,z
            if e.at then
                x,y,z=math.floor(e.at.x),math.floor(e.at.y),e.at.z or o.z
            else
                local ox,oy=dx,dy
                if behind then
                    local b=t.block
                    local length=math.abs(b.dx)+math.abs(b.dy)
                    assert(length>0,"Trajet requis pour placer un poursuivant")
                    ox=-b.dx/length*behind-b.dy/length*side
                    oy=-b.dy/length*behind+b.dx/length*side
                end
                x,y,z=math.floor(o.x+ox),math.floor(o.y+oy),o.z
            end
            -- A blocked mark moves to the nearest free square; with none, the extra is left out
            -- (logged) rather than raising an error, which opens the Kahlua debugger in -debug.
            if not free(square(x,y,z)) then
                local found
                for r=1,3 do
                    for ddx=-r,r do for ddy=-r,r do
                        if not found and math.max(math.abs(ddx),math.abs(ddy))==r and free(square(x+ddx,y+ddy,z)) then
                            found={x+ddx,y+ddy}
                        end
                    end end
                end
                if not found then
                    print("[PZDirector] figurant omis, aucune case libre: "..label)
                    return
                end
                x,y=found[1],found[2]
            end
            local zombie=PZDevKit.World.spawnZombie(x,y,z,{outfit=e.outfit or "Generic02",
                fakeDead=e.fakeDead,crawler=e.crawler,sitting=e.sitting})
            c.vars.director.spawned[#c.vars.director.spawned+1]=zombie
            t.extras[zombie]={behavior="hold"}; t.namedExtras[label]=zombie
            if e.speed=="fast" then zombie:doFastShambler() end
            if e.speed=="sprint" then zombie:doSprinter() end
            zombie:setUseless(true)
            if e.face then zombie:faceLocation(e.face.x,e.face.y)
            elseif not e.fakeDead then zombie:faceLocation(o.x,o.y) end
        end)
    end
    -- rise=true: a fake corpse gets up (setFakeDead(false)) instead of grabbing from the floor.
    scene.releaseExtra=function(self,label,optionsRelease)
        local r=optionsRelease or {}
        return self:call("TOP FIGURANT: poursuite / "..label,function(c)
            local t=c.vars.production
            local zombie=t.namedExtras[label]
            if not zombie or zombie:isDead() then
                print("[PZDirector] top ignore, figurant absent ou mort: "..label)
                return
            end
            if r.rise and zombie:isFakeDead() then zombie:setFakeDead(false) end
            t.extras[zombie].behavior="hunt"
            updateSet(c)
            zombie:spotted(c.player,true)
            assert(zombie:getTarget()==c.player and not zombie:isUseless(),"Figurant ne poursuit pas l'acteur")
        end)
    end
    -- Several extras at once, on the same cue (a waking room, a charging garrison).
    scene.releaseExtras=function(self,labels,optionsRelease)
        for _,label in ipairs(labels) do self:releaseExtra(label,optionsRelease) end
        return self
    end
    scene.clearExtras=function(self)
        return self:call("COUPE FIGURANTS",function(c)
            local t,spawned=c.vars.production,c.vars.director.spawned
            for i=#spawned,1,-1 do
                local zombie=spawned[i]
                PZDevKit.World.removeSpawned(zombie); table.remove(spawned,i)
                t.extras[zombie]=nil
            end
            t.namedExtras={}
        end)
    end

    -- Keep the gait inside this timed action's update, after the player's input
    -- reset, before path movement/animation. Never change the vanilla class.
    scene.moveOnSet=function(self,mode,timeout)
        assert(mode=="walk" or mode=="run" or mode=="sprint","Allure de plateau inconnue")
        local goal,before,started
        return self:act("DEPLACEMENT JOUE: "..mode,function(c)
            local p,b=c.player,c.vars.production.block
            assert(b and math.abs(b.dx)+math.abs(b.dy)>0,"Trajet de plateau requis")
            assert(not p:getVehicle(),"Acteur a pied requis")
            before={run=p:isForceRun(),sprint=p:isForceSprint()}
            goal={x=b.x+b.dx+0.5,y=b.y+b.dy+0.5,z=b.z}
            started=P.status().duration
            local action=ISPathFindAction:pathToLocationF(p,goal.x,goal.y,goal.z)
            local update=action.update
            action.update=function(instance,...)
                p:setForceAim(false); p:setIsAiming(false)
                p:setForceRun(mode=="run"); p:setForceSprint(mode=="sprint")
                p:setRunning(mode=="run"); p:setSprinting(mode=="sprint")
                return update(instance,...)
            end
            return action
        end,function(c)
            return P.Game.near(c.player,goal.x,goal.y,goal.z,0.8)
        end,timeout or 20):call("FIN DE DEPLACEMENT JOUE",function(c)
            local p=c.player
            p:setForceRun(before.run); p:setForceSprint(before.sprint)
            p:setRunning(false); p:setSprinting(false)
            local b=c.vars.production.block
            print("[PZDirector] movement="..mode.." tiles="..(math.abs(b.dx)+math.abs(b.dy))
                .." seconds="..(P.status().duration-started))
        end)
    end

    scene.light=function(self,optionsLight)
        local l=optionsLight or {}
        local r=range(l.r or 0.28,0,1,"rouge")
        local g=range(l.g or 0.26,0,1,"vert")
        local b=range(l.b or 0.22,0,1,"bleu")
        local radius=range(l.radius or 8,1,20,"rayon de lumiere")
        local dx=range(l.dx or 0,-20,20,"decalage x")
        local dy=range(l.dy or 0,-20,20,"decalage y")
        -- Lighting is recomputed ~15 times/s with a fade: phases under 0.5 s are not visible.
        local blink=l.blink and range(l.blink,0.5,5,"periode de clignotement")
        local label=l.name
        return self:call("LUMIERE: source de plateau temporaire",function(c)
            local o=c.vars.director.origin
            local x,y=math.floor(o.x+dx),math.floor(o.y+dy)
            assert(square(x,y,o.z),"Case de lumiere non chargee")
            local light=getCell():addLamppost(x,y,o.z,r,g,b,math.floor(radius))
            assert(light,"Lumiere non creee")
            local t=c.vars.production
            t.lights[#t.lights+1]=light
            if label then t.namedLights=t.namedLights or {}; t.namedLights[label]=light end
            if blink then
                t.blinking=t.blinking or {}
                t.blinking[light]={period=blink,start=P.status().duration}
            end
        end)
    end
    -- Start/stop the blinking of a named light on a cue (an alarm that goes off).
    scene.blinkLight=function(self,label,period)
        local value=period and range(period,0.5,5,"periode de clignotement")
        return self:call("LUMIERE: clignotement / "..tostring(label),function(c)
            local t=c.vars.production
            local light=assert(t.namedLights and t.namedLights[label],"Lumiere nommee absente")
            t.blinking=t.blinking or {}
            if value then t.blinking[light]={period=value,start=P.status().duration}
            else t.blinking[light]=nil; light:setActive(true) end
        end)
    end

    -- Keep the actor's own items out of shots that show the inventory (no spoilers, no clutter).
    -- Nothing is deleted: the items wait in a duffel bag kept in the actor's inventory, saved with
    -- the character, and are put back before the original clothes are worn again. Never leave it
    -- on the ground: a teleport unloads that chunk to disk, and restoring from the in-memory bag
    -- then duplicates every item when the chunk is read back.
    scene.stashInventory=function(self)
        return self:call("INVENTAIRE: objets de l'acteur ranges hors champ",function(c)
            local t,p=c.vars.production,c.player
            assert(not t.stash,"Inventaire deja range")
            local keep={}
            for _,item in ipairs(t.items) do keep[item]=true end
            local worn=p:getWornItems()
            for i=0,worn:size()-1 do keep[worn:get(i):getItem()]=true end
            if p:getPrimaryHandItem() then keep[p:getPrimaryHandItem()]=true end
            if p:getSecondaryHandItem() then keep[p:getSecondaryHandItem()]=true end
            local bag=instanceItem("Base.Bag_DuffelBag")
            assert(bag and bag.getItemContainer,"Sac de rangement non cree")
            local inventory,box=p:getInventory(),bag:getItemContainer()
            local list,moved=inventory:getItems(),{}
            local items={}
            for i=0,list:size()-1 do items[#items+1]=list:get(i) end
            for _,item in ipairs(items) do
                if not keep[item] then box:AddItem(item); moved[#moved+1]=item end
            end
            inventory:AddItem(bag)
            t.stash={bag=bag}
            print("[PZDirector] inventaire range: "..#moved.." objets dans un sac de l'inventaire")
        end)
    end

    -- Framing per shot: wider for a chase (threat in frame), closer for a document.
    scene.frame=function(self,level)
        local target=range(level,0.25,3,"zoom")
        return self:call("CADRAGE: zoom "..target,function(c) zoom(getCore(),c.playerIndex,target) end)
    end

    -- Interface for shots where the player reads, loots or checks an objective.
    scene.showUI=function(self,visible)
        assert(type(visible)=="boolean","Visibilite de l'interface attendue")
        return self:call("INTERFACE: "..(visible and "visible" or "masquee"),function(c)
            local t=c.vars.production
            ISUIHandler.allUIVisible=visible
            ISUIHandler.setVisibleAllUI(visible)
            -- After setVisibleAllUI, which shows them again: the -debug console and the radio
            -- windows are not part of a loot or reading shot.
            local console=UIManager.getDebugConsole and UIManager.getDebugConsole()
            if console then
                if t.debugConsole==nil then t.debugConsole=console:isVisible() end
                console:setVisible(false)
            end
            if visible and ISRadioWindow then
                t.radioWindows=t.radioWindows or {}
                for _,list in ipairs({ISRadioWindow.instances or {},ISRadioWindow.instancesIso or {}}) do
                    for _,window in pairs(list) do
                        if window and window.isVisible and window:isVisible() then
                            t.radioWindows[#t.radioWindows+1]=window; window:setVisible(false)
                        end
                    end
                end
            end
            -- The character info panel (portrait, skills) is not part of a loot shot.
            local info=getPlayerInfoPanel and getPlayerInfoPanel(c.playerIndex)
            if visible and info then
                if t.infoPanel==nil then t.infoPanel=info:isVisible() end
                info:setVisible(false)
            end
        end)
    end
    -- Show a printMedia document (the reading window of an item) without a reading action:
    -- no timed action, no read hook, no story side effect. Closed after `seconds`.
    -- optionsDocument.still: screenshot once the window is drawn (Zomboid/Screenshots/PZDirector_<name>.png).
    scene.document=function(self,selector,seconds,optionsDocument)
        local duration=range(seconds or 3,0.5,20,"duree du document")
        local still=optionsDocument and optionsDocument.still and D.captureName(optionsDocument.still)
        local win
        local shown=self:call("DOCUMENT: ouverture",function(c)
            local item=P.Game.item(c,selector)
            local media=item:getModData().printMedia
            assert(media and media.info,"Document sans printMedia")
            win=PZAPI.UI.PrintMedia{x=730,y=100}
            win.media_id=media.id
            win.data=getText(media.info)
            win.children.bar.children.name.text=getText(media.title)
            win.textTitle=getText(media.title)
            win.textData=string.gsub(getText(media.text),"\\n","\n")
            win:instantiate()
            win.javaObj:setAlwaysOnTop(true)
            win:centerOnScreen(c.playerIndex)
            local t=c.vars.production
            t.windows=t.windows or {}
            t.windows[#t.windows+1]=win
        end)
        if still then
            shown=shown:wait(math.min(0.6,duration/2)):call("DOCUMENT: capture "..still,function()
                takeScreenshot("PZDirector_"..still..".png")
                print("[PZDirector] SCREENSHOT|"..still)
            end)
            duration=duration-math.min(0.6,duration/2)
        end
        return shown:wait(duration):call("DOCUMENT: fermeture",function(c)
            if win then UIManager.RemoveElement(win.javaObj) end
            local t=c.vars.production
            for i=#(t.windows or {}),1,-1 do if t.windows[i]==win then table.remove(t.windows,i) end end
            win=nil
        end)
    end
    -- Show the inventory and the loot window opened on a container (corpse, furniture).
    scene.openLoot=function(self,selector)
        return self:call("INVENTAIRE: fenetre de butin",function(c)
            local container=type(selector)=="function" and selector(c) or selector
            assert(container,"Conteneur de butin absent")
            local inventory,loot=getPlayerInventory(c.playerIndex),getPlayerLoot(c.playerIndex)
            assert(inventory and loot,"Fenetres d'inventaire absentes")
            local t=c.vars.production
            -- A pinned page stays expanded without the mouse over it (ISInventoryPage:update).
            t.pages=t.pages or {}
            -- Side by side above the actor, inside the centered 16:9 area kept by captures.
            local core=getCore()
            local cx,cy=core:getScreenWidth()/2,core:getScreenHeight()/2
            local width,height=math.min(560,cx-40),math.min(320,cy-120)
            local placement={[inventory]=cx-width-12,[loot]=cx+12}
            for _,page in ipairs({inventory,loot}) do
                if t.pages[page]==nil then
                    t.pages[page]={pin=page.pin==true,x=page:getX(),y=page:getY(),
                        w=page:getWidth(),h=page:getHeight()}
                end
                page:setVisible(true); page:setPinned()
                page:setX(placement[page]); page:setY(cy-height-90)
                page:setWidth(width); page:setHeight(height)
            end
            loot:setForceSelectedContainer(container,8000)
            loot:refreshBackpacks()
            -- No orange outline on the looted object (ISInventoryPage:updateContainerHighlight draws
            -- it only with this option; ObjectsHighlightedElsewhere is local to that file).
            if t.containerOutline==nil then t.containerOutline=core:getOptionDoContainerOutline() end
            core:setOptionDoContainerOutline(false)
            local parent=loot:getContainerParent(container)
            if parent then parent:setOutlineHighlight(c.playerIndex,false) end
        end)
    end
    -- A thought over the actor's head (game text, not a subtitle).
    scene.think=function(self,text,color)
        assert(type(text)=="string" and text~="","Texte de pensee requis")
        local rgb=color or {0.85,0.85,0.75}
        return self:call("PENSEE: "..text:sub(1,40),function(c)
            c.player:addLineChatElement(getTextOrNull(text) or text,rgb[1],rgb[2],rgb[3])
        end)
    end
    return scene
end
return D
