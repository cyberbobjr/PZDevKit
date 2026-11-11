local T={}
local function eq(a,b) assert(a==b,"Expected " .. tostring(b) .. ", got " .. tostring(a)) end

function T.setup()
    local engine=assert(loadstring(readEngineTest()))()
    engine.setup()
    CLIENT,SERVER=false,false
    isClient=function() return CLIENT end
    isServer=function() return SERVER end
    local flags={god=false,ghost=false,invisible=false,noclip=false,noAttack=false,instant=false,ammo=false}
    for key,suffix in pairs({god="GodMod",ghost="GhostMode",invisible="Invisible",
        noclip="NoClip",noAttack="ZombiesDontAttack",instant="TimedActionInstantCheat",ammo="UnlimitedAmmo"}) do
        PLAYER["is" .. suffix]=function() return flags[key] end
        PLAYER["set" .. suffix]=function(_,value) flags[key]=value end
    end
    STATES={ForceRun=false,ForceSprint=false,ForceAim=false,Aiming=false,Sneaking=false,
        Running=false,Sprinting=false,DoShove=false}
    for key in pairs(STATES) do
        PLAYER["is" .. key]=function() return STATES[key] end
        PLAYER["set" .. key]=function(_,v) STATES[key]=v end
    end
    PLAYER.setIsAiming=PLAYER.setAiming
    PLAYER.getJoypadBind=function() return -1 end
    PLAYER.isAttackStarted=function() return ATTACK~=nil end
    PLAYER.isWeaponReady=function() return true end
    PLAYER.getBallisticsController=function(s) return s.ballistics end
    PLAYER.updateBallistics=function(s) s.ballistics=s.ballistics or {} end
    PLAYER.CanAttack=function() return true end
    PLAYER.getRecoilDelay=function() return 0 end
    PLAYER.getMeleeDelay=function() return 0 end
    PLAYER.getDoRender=function(s) return s.render~=false end
    PLAYER.setDoRender=function(s,v) s.render=v end
    PLAYER.getAlpha=function(s) return s.alpha or 1 end
    PLAYER.getTargetAlpha=function(s) return s.targetAlpha or 1 end
    PLAYER.setAlpha=function(s,_,v) s.alpha=v end
    PLAYER.setTargetAlpha=function(s,_,v) s.targetAlpha=v end
    PLAYER.setAlphaAndTarget=function(s,_,v) s.alpha=v; s.targetAlpha=v end
    VARIABLES={}
    PLAYER.setVariable=function(_,key,v) VARIABLES[key]=v end
    PLAYER.getVariableBoolean=function(_,key) return VARIABLES[key]==true end
    PLAYER.playEmote=function(_,name) VARIABLES.emote=name; VARIABLES.EmotePlaying=true; EMOTE_TICKS=5 end
    ATTACK=nil; EMOTE_TICKS=nil; SHOTS=0; BULLETS=true; SKIP_SHOT_EVENT=false
    getCore=function() return {
        getScreenWidth=function() return 1920 end,getScreenHeight=function() return 1080 end,
        getOffscreenHeight=function() return 1620 end,
    } end
    MX,MY=50,70
    getMouseX=function() return MX end; getMouseY=function() return MY end
    setMouseXY=function(x,y) MX=x; MY=y-540 end
    isoToScreenX=function(_,x) return 900+x end; isoToScreenY=function(_,_,y) return 500+y end
    GUN={kind="HandWeapon",ammo=3,chamber=false,
        isRanged=function() return true end,getCondition=function() return 10 end,
        getCurrentAmmoCount=function(s) return s.ammo end,getMaxAmmo=function() return 6 end,
        isRoundChambered=function(s) return s.chamber end}
    ISReloadWeaponAction={
        canShoot=function(_,g) return g.ammo>0 or g.chamber end,
        canRack=function() return true end,
        BeginAutomaticReload=function(_,g)
            if BULLETS then QUEUE[#QUEUE+1]={apply=function() g.ammo=6 end} end
        end,
        attackHook=function(_,_,g) ATTACK=g end}
    ISRackFirearm={new=function(_,p,g) return {character=p,apply=function() g.chamber=true end} end}
    FOOD={kind="Food",hunger=-.3,getContainer=function() return INV end,
        getHungChange=function(s) return s.hunger end}
    FLUID={amount=1,isEmpty=function(s) return s.amount<=0 end,canPlayerEmpty=function() return true end,
        getCapacity=function() return 1 end,getAmount=function(s) return s.amount end}
    BOTTLE={getContainer=function() return INV end,getFluidContainer=function() return FLUID end}
    ISInventoryPaneContextMenu.eatItem=function(item,percent)
        QUEUE[#QUEUE+1]={apply=function() item.hunger=item.hunger*(1-percent) end}
    end
    ISInventoryPaneContextMenu.onDrinkFluid=function(_,percent)
        QUEUE[#QUEUE+1]={apply=function() FLUID.amount=FLUID.amount*(1-percent) end}
    end
    MUTE=false
    getSoundManager=function() return {
        isUiSoundMuted=function() return MUTE end,
        setUiSoundMuted=function(_,value) MUTE=value end,
    } end
    UI_CALLS={}
    ISUIHandler={allUIVisible=true,setVisibleAllUI=function(value) UI_CALLS[#UI_CALLS+1]=value end}
    SOUNDS,SPAWNS,THUNDER={},{},0
    getWorld=function() return {getFreeEmitter=function()
        local sound={stopped=false}
        sound.playSound=function(_,name) sound.name=name; SOUNDS[#SOUNDS+1]=sound; return #SOUNDS end
        sound.playSoundLoopedImpl=sound.playSound
        sound.stopSoundLocal=function() sound.stopped=true end
        return sound
    end} end
    getClimateManager=function() return {getThunderStorm=function() return {
        triggerThunderEvent=function() THUNDER=THUNDER+1 end,
    } end} end
    OUTSIDE,FREE,WATER=true,true,false
    getCell=function() return {getGridSquare=function()
        if not LOADED then return nil end
        return {isOutside=function() return OUTSIDE end,isFree=function() return FREE end,
            isWaterSquare=function() return WATER end}
    end} end
    addZombiesInOutfit=function(x,y,z,count)
        local created={}
        for i=1,count do
            local zombie={kind="IsoZombie",x=x,y=y,z=z,useless=false,
                isUseless=function(s) return s.useless end,setUseless=function(s,v) s.useless=v end,
                removeFromWorld=function(s) if s.failRemoval then error("remove failure") end; s.removed=true end,
                removeFromSquare=function(s) s.squareRemoved=true end,
                pathToCharacter=function(s,p) s.target=p end,
                pathToLocationF=function(s,gx,gy,gz) s.goal={x=gx,y=gy,z=gz} end}
            zombie.setTarget=function(s,v) s.target=v end
            zombie.getTarget=function(s) return s.target end
            zombie.faceLocation=function(s,gx,gy) s.facing={x=gx,y=gy} end
            zombie.getX=function(s) return s.x end
            zombie.getY=function(s) return s.y end
            zombie.getZ=function(s) return s.z end
            zombie.getCurrentSquare=function(s) return not s.removed and {} or nil end
            zombie.isDead=function() return false end
            zombie.doFastShambler=function(s) s.speed="fast" end
            zombie.doSprinter=function(s) s.speed="sprint" end
            zombie.spotted=function(s,p) s.spottedBy=p end
            zombie.isFakeDead=function(s) return s.fakeDead==true end
            zombie.setFakeDead=function(s,v) s.fakeDead=v end
            zombie.isSolid=function(s) return s.solid~=false end
            zombie.setSolid=function(s,v) s.solid=v end
            zombie.isCollidable=function(s) return s.collidable~=false end
            zombie.setCollidable=function(s,v) s.collidable=v end
            for _,key in ipairs({"getDoRender","setDoRender","getAlpha","getTargetAlpha",
                "setAlpha","setTargetAlpha","setAlphaAndTarget"}) do zombie[key]=PLAYER[key] end
            created[i]=zombie
            SPAWNS[#SPAWNS+1]=zombie
        end
        return {size=function() return #created end,get=function(_,i) return created[i+1] end}
    end
    dofileMod("PZDevKit/Production")
    dofileMod("PZDevKit/Demos")
end

local function tick(ms)
    NOW=NOW+(ms or 100)
    local handlers={}
    for i,f in ipairs(Events.OnTick.handlers) do handlers[i]=f end
    for _,f in ipairs(handlers) do f() end
end
local function drive(count)
    for _=1,count do
        for _,action in ipairs(QUEUE) do if action.apply then action.apply(); action.apply=nil end end
        if #QUEUE>0 and QUEUE[1].apply==nil and not PATH then
            for i=#QUEUE,1,-1 do table.remove(QUEUE,i) end
        end
        if ATTACK and not SKIP_SHOT_EVENT then
            local gun=ATTACK
            gun.ammo=gun.ammo-1; SHOTS=SHOTS+1
            for _,handler in ipairs(Events.OnWeaponSwingHitPoint.handlers) do handler(PLAYER,gun) end
            ATTACK=nil
        end
        if EMOTE_TICKS then
            EMOTE_TICKS=EMOTE_TICKS-1
            if EMOTE_TICKS<=0 then EMOTE_TICKS=nil; VARIABLES.EmotePlaying=false end
        end
        if PATH and #QUEUE>0 then
            PLAYER.x,PLAYER.y,PLAYER.z=PATH.x,PATH.y,PATH.z
            for i=#QUEUE,1,-1 do table.remove(QUEUE,i) end
            PATH=nil
        end
        tick()
    end
end
local function report() return PZDevKit.Scenario.lastReport end

-- Production contracts only: simulated native objects, never an in-game proof.
local function staging()
    dofileMod("PZDevKit/Staging")
    HOUR=12.5
    getGameTime=function() return {getTimeOfDay=function() return HOUR end,
        setTimeOfDay=function(_,v) HOUR=v end} end
    CORE={level=1,auto=true,pan=true}
    CORE.getNextZoom=function(s,_,direction) return math.max(.5,math.min(2,s.level+direction*.25)) end
    CORE.doZoomScroll=function(s,index,direction) s.level=s:getNextZoom(index,direction) end
    CORE.getAutoZoom=function(s) return s.auto end
    CORE.setAutoZoom=function(s,_,value) s.auto=value end
    CORE.getOptionPanCameraWhileAiming=function(s) return s.pan end
    CORE.setOptionPanCameraWhileAiming=function(s,value) s.pan=value end
    getCore=function() return CORE end
    ORIGINAL_COAT={slot="coat",name="original coat"}
    ORIGINAL_BAG={slot="back",name="original bag"}
    WORN={ORIGINAL_COAT,ORIGINAL_BAG}
    WORN.size=function(s) return #s end
    WORN.get=function(s,i)
        local item=s[i+1]
        return {getLocation=function() return item.slot end,getItem=function() return item end}
    end
    WORN.contains=function(s,item) for _,w in ipairs(s) do if w==item then return true end end return false end
    PLAYER.getWornItems=function() return WORN end
    PLAYER.removeWornItem=function(_,item,drop)
        eq(drop,false)
        for i=#WORN,1,-1 do if WORN[i]==item then table.remove(WORN,i) end end
    end
    PLAYER.setWornItem=function(_,location,item,drop)
        eq(drop,false)
        for i=#WORN,1,-1 do if WORN[i].slot==location then table.remove(WORN,i) end end
        if item then WORN[#WORN+1]=item end
    end
    HAIR="original hair"
    PLAYER.getHumanVisual=function() return {
        getHairModel=function() return HAIR end,setHairModel=function(_,v) HAIR=v end} end
    PLAYER.resetModelNextFrame=function() end
    PLAYER.setPrimaryHandItem=function(s,item) s.primary=item end
    PLAYER.setSecondaryHandItem=function(s,item) s.secondary=item end
    PLAYER.getCurrentSquare=function(s) return {
        getX=function() return math.floor(s.x) end,getY=function() return math.floor(s.y) end,
        getZ=function() return math.floor(s.z) end} end
    PLAYER.faceLocation=function(_,x,y) FACING={x=x,y=y} end
    CREATED,LIGHTS,TOGGLES={},{},0
    PZDevKit.World.spawnItem=function(fullType)
        local item={fullType=fullType,slot=fullType:find("Bag",1,true) and "back" or "coat",active=true}
        item.getBodyLocation=function(s) if s.slot~="back" then return s.slot end end
        item.canBeEquipped=function(s) return s.slot end
        item.getContainer=function() return INV end
        item.setUsedDelta=function(s,v) s.charge=v end
        item.canBeActivated=function() return true end
        item.isActivated=function(s) return s.active end
        item.isEmittingLight=function(s) return s.active and (s.charge or 1)>0 end
        CREATED[#CREATED+1]=item
        return {item}
    end
    PZDevKit.World.removeSpawned=function(item)
        assert(not item.removed,"Only remove an owned item once")
        item.removed=true
    end
    PZDevKit.World.setTime=function(value) HOUR=value end
    PZDevKit.World.teleport=function(x,y,z) PLAYER.x,PLAYER.y,PLAYER.z=math.floor(x),math.floor(y),z end
    ISInventoryPaneContextMenu.onActivateItem=function(item) TOGGLES=TOGGLES+1; item.active=not item.active end
    BLOCK_ALL=false
    AMBIENT={}
    getAllOutfits=function() return {size=function() return 1 end,get=function() return "Generic02" end} end
    getCell=function() return {
        getZombieList=function() return {size=function() return #AMBIENT end,
            get=function(_,i) return AMBIENT[i+1] end} end,
        getGridSquare=function(_,x,y,z)
            return {isFree=function() return x~=40 or y~=50 end,isWaterSquare=function() return false end,
                isOutside=function() return true end,isBlockedTo=function() return BLOCK_ALL end,
                getChunk=function() return {} end,
                getX=function() return x end,getY=function() return y end,getZ=function() return z end}
        end,
        addLamppost=function()
            local light={setActive=function(s,v) s.active=v end}
            LIGHTS[#LIGHTS+1]=light; return light
        end,
        removeLamppost=function(_,light) light.removed=true end,
    } end
end

function T.production_disables_existing_debug_cheats_and_restores_them_on_cancel()
    staging()
    PLAYER:setGodMod(true); PLAYER:setGhostMode(true); PLAYER:setInvisible(true)
    PLAYER:setNoClip(true); PLAYER:setZombiesDontAttack(true)
    PLAYER:setTimedActionInstantCheat(true)
    PLAYER:setUnlimitedAmmo(true)
    PZDevKit.Production.production("visible actor",{countdown=0,duration=20})
        :check("Real actor",function(c)
            local p=c.player
            return not p:isGodMod() and not p:isGhostMode() and not p:isInvisible()
                and not p:isNoClip() and not p:isZombiesDontAttack() and not p:isTimedActionInstantCheat()
                and not p:isUnlimitedAmmo()
        end):wait(15):run()
    drive(10); eq(PLAYER:isGodMod(),false); eq(PLAYER:isNoClip(),false)
    PZDevKit.Production.stop("cancel")
    eq(report().status,"cancelled"); eq(PLAYER:isGodMod(),true)
    eq(PLAYER:isGhostMode(),true); eq(PLAYER:isInvisible(),true)
    eq(PLAYER:isNoClip(),true); eq(PLAYER:isZombiesDontAttack(),true)
    eq(PLAYER:isTimedActionInstantCheat(),true)
    eq(PLAYER:isUnlimitedAmmo(),true)
end

function T.production_holds_the_set_hour_while_actions_continue()
    staging()
    PZDevKit.Production.production("clock",{countdown=0,duration=20})
        :location("day",{point={x=40,y=50,z=0},hour=15.5,travelTiles=0})
        :wait(15):run()
    drive(20); eq(HOUR,15.5)
    HOUR=16.2; tick(); eq(HOUR,15.5)
    PZDevKit.Production.stop("cancel"); eq(HOUR,12.5)
end

function T.production_gait_runs_after_native_reset_on_one_action_only_and_cancels_cleanly()
    staging()
    local original=ISPathFindAction.pathToLocationF
    local calls=0
    local nativeUpdate=function(instance,arg)
        eq(instance.character,PLAYER); eq(arg,"argument preserved")
        eq(PLAYER:isSprinting(),true); eq(PLAYER:isRunning(),false)
        calls=calls+1
        return "return preserved"
    end
    ISPathFindAction.pathToLocationF=function(self,...)
        local action=original(self,...)
        action.update=nativeUpdate
        return action
    end
    local scene=PZDevKit.Production.production("physical gait",{countdown=0,duration=20})
        :location("set",{point={x=40,y=50,z=0},travelTiles=6})
        :moveOnSet("sprint",10):wait(15)
    scene:run()
    for _=1,25 do tick(); if #QUEUE>0 then break end end
    local action=assert(QUEUE[1])
    PLAYER:setForceSprint(false); PLAYER:setSprinting(false)
    eq(action:update("argument preserved"),"return preserved"); eq(calls,1)
    local unrelated=ISPathFindAction:pathToLocationF(PLAYER,20,20,0)
    eq(unrelated.update,nativeUpdate)
    PZDevKit.Production.stop("cancel during gait")
    eq(report().status,"cancelled"); eq(#QUEUE,0)
    eq(PLAYER:isForceSprint(),false); eq(PLAYER:isSprinting(),false)
end

function T.production_cast_zombie_hunts_visible_actor_and_ambient_zombie_is_restored()
    staging()
    local ambient=PZDevKit.World.spawnZombie(42,52,0)
    AMBIENT={ambient}
    PZDevKit.Production.production("encounter",{countdown=0,duration=20})
        :location("set",{point={x=40,y=50,z=0},hour=15,travelTiles=0,isolate=40})
        :extra("hunter",{dx=6,dy=0,speed="fast"})
        :check("Held until cue",function(c)
            return c.vars.production.namedExtras.hunter:isUseless()
        end):releaseExtra("hunter"):wait(15):run()
    drive(25)
    eq(ambient:isUseless(),true); eq(ambient:getDoRender(),false)
    eq(ambient:isSolid(),false); eq(ambient:isCollidable(),false)
    local hunter=SPAWNS[2]; eq(hunter.target,PLAYER); eq(hunter:isUseless(),false); eq(hunter.speed,"fast")
    eq(PLAYER:isGhostMode(),false); eq(PLAYER:isGodMod(),false)
    PZDevKit.Production.stop("cancel")
    eq(ambient.removed,nil); eq(ambient:isUseless(),false); eq(ambient:getDoRender(),true)
    eq(ambient:isSolid(),true); eq(ambient:isCollidable(),true)
    eq(hunter.removed,true)
end

function T.production_building_does_not_create_a_costume_or_move_the_actor()
    staging()
    PZDevKit.Production.production("cast"):cast({clothes={"Base.Coat","Base.Bag_ALICEpack_Army"}})
        :location("set",{point={x=40,y=50,z=0}}):light()
    eq(#CREATED,0); eq(#LIGHTS,0); eq(PLAYER.x,10.5); eq(#WORN,2)
    eq(CORE.level,1); eq(#Events.OnTick.handlers,0)
end

function T.production_restores_costume_hands_camera_position_time_and_lights()
    staging()
    local hand={name="original hand"}; PLAYER.primary=hand
    PZDevKit.Production.production("cast",{countdown=0,duration=2})
        :cast({clothes={"Base.Coat","Base.Bag_ALICEpack_Army"},primary={type="Base.HandTorch",charge=1}})
        :activate(function(c) return c.vars.production.props.primary end,true)
        :location("set",{point={x=40,y=50,z=0},hour=8,travelTiles=3}):light()
        :check("Original blocked anchor is avoided",function(c)
            return c.vars.production.block.x~=40 or c.vars.production.block.y~=50
        end):run()
    drive(90)
    eq(report().status,"passed"); eq(TOGGLES,0); eq(#CREATED,3)
    for _,item in ipairs(CREATED) do eq(item.removed,true) end
    eq(WORN[1],ORIGINAL_COAT); eq(WORN[2],ORIGINAL_BAG); eq(PLAYER.primary,hand)
    eq(PLAYER.x,10); eq(PLAYER.y,20); eq(HOUR,12.5)
    eq(CORE.level,1); eq(CORE.auto,true); eq(CORE.pan,true); eq(LIGHTS[1].removed,true)
end

function T.production_failure_restores_actor_and_does_not_accept_a_blocked_path()
    staging(); BLOCK_ALL=true
    PZDevKit.Production.production("blocked",{countdown=0,duration=2})
        :cast({clothes={"Base.Coat"}})
        :location("blocked",{point={x=40,y=50,z=0},travelTiles=3}):run()
    drive(60)
    eq(report().status,"failed"); assert(report().reason:find("Aucun blocking",1,true))
    eq(WORN[1],ORIGINAL_COAT); eq(WORN[2],ORIGINAL_BAG)
    eq(CREATED[1].removed,true); eq(PLAYER.x,10); eq(CORE.auto,true)
end

function T.production_activation_switches_an_off_prop_on_exactly_once()
    staging()
    PZDevKit.Production.production("activate",{countdown=0,duration=2})
        :cast({clothes={"Base.Coat"},primary={type="Base.HandTorch",charge=1}})
        :call("off",function(c) c.vars.production.props.primary.active=false end)
        :activate(function(c) return c.vars.production.props.primary end,true)
        :activate(function(c) return c.vars.production.props.primary end,true):run()
    drive(70); eq(report().status,"passed"); eq(TOGGLES,1)
end

function T.production_cancel_removes_only_its_costume_and_restores_settings()
    staging()
    PZDevKit.Production.production("cancel",{countdown=0,duration=20})
        :cast({clothes={"Base.Coat"}}):light():wait(15):run()
    drive(12); PZDevKit.Production.stop("manual cancellation")
    eq(report().status,"cancelled"); eq(CREATED[1].removed,true)
    eq(WORN[1],ORIGINAL_COAT); eq(WORN[2],ORIGINAL_BAG)
    eq(LIGHTS[1].removed,true); eq(CORE.pan,true)
end

function T.production_underground_set_does_not_require_nonexistent_corner_tiles()
    staging()
    local cell=getCell()
    local lookup=cell.getGridSquare
    cell.getGridSquare=function(self,x,y,z)
        if z==-17 and math.abs(x-40)<=1 and math.abs(y-50)<=1 then return lookup(self,x,y,z) end
    end
    getCell=function() return cell end
    PZDevKit.Production.production("underground",{countdown=0,duration=2})
        :location("small room",{point={x=40,y=50,z=-17},travelTiles=0}):run()
    drive(70); eq(report().status,"passed"); eq(PLAYER.z,0)
end

function T.registration_and_building_have_no_effects()
    PZDevKit.Production.demo(); PZDevKit.Production.observation()
    eq(#Events.OnTick.handlers,0); eq(#SOUNDS,0); eq(#SPAWNS,0)
    eq(ISUIHandler.allUIVisible,true); eq(PLAYER:isGodMod(),false)
    eq(PZDevKit.Scenario.factories["PZDevKit.Production.demo"],PZDevKit.Production.demo)
end

function T.cues_run_during_a_player_action_and_keep_order()
    local seen={}
    local s=PZDevKit.Production.scene("timing",{countdown=0,duration=2})
        :cue(.2,"second",function() seen[#seen+1]="b" end)
        :cue(.1,"first",function() seen[#seen+1]="a" end)
        :cue(.2,"third",function() seen[#seen+1]="c"; assert(#QUEUE>0) end)
        :moveBy(2,0)
    s:run()
    for _=1,7 do tick() end
    eq(table.concat(seen),"abc")
    drive(30)
    eq(report().status,"passed"); eq(PLAYER.x,12.5)
    eq(ISUIHandler.allUIVisible,true); eq(PLAYER:isGodMod(),false); eq(MUTE,false)
end

function T.mark_and_screenshot_steps_print_markers_and_name_the_file()
    local shots,printed={},{}
    takeScreenshot=function(name) shots[#shots+1]=name end
    local oldPrint=print
    print=function(line) printed[#printed+1]=line end
    PZDevKit.Production.scene("captures",{countdown=0,duration=.2})
        :mark("plan-1")
        :screenshot("still_1")
        :run()
    drive(10)
    print=oldPrint
    eq(report().status,"passed")
    eq(#shots,1); eq(shots[1],"PZDirector_still_1.png")
    local text=table.concat(printed," / ")
    assert(text:find("[PZDirector] MARK|plan-1",1,true),text)
    assert(text:find("[PZDirector] SCREENSHOT|still_1",1,true),text)
    for _,bad in ipairs({"../x","with space",""}) do
        assert(not pcall(function() PZDevKit.Production.scene("bad"):screenshot(bad) end),bad)
    end
end

function T.cancel_before_clap_releases_the_next_take()
    PZDevKit.Production.scene("delay",{countdown=5}):run()
    tick(); PZDevKit.Production.stop()
    eq(report().status,"cancelled"); eq(#UI_CALLS,0)
    PZDevKit.Production.scene("next",{countdown=0,duration=.2}):run()
    drive(10); eq(report().status,"passed")
end

function T.manual_cancellation_restores_flags_hud_and_creations()
    PZDevKit.Production.observation({countdown=0}):run()
    drive(30)
    eq(#SPAWNS,1); eq(PLAYER:isInvisible(),true); eq(MUTE,true)
    INPUT=true; tick()
    eq(report().status,"cancelled")
    eq(SPAWNS[1].removed,true); eq(SOUNDS[1].stopped,true)
    eq(PLAYER:isGhostMode(),false); eq(PLAYER:isInvisible(),false)
    eq(ISUIHandler.allUIVisible,true); eq(MUTE,false)
end

function T.erroring_cue_fails_once_and_restores_state()
    local calls=0
    PZDevKit.Production.scene("error",{countdown=0,duration=1})
        :cue(0,"bad",function(c)
            PZDevKit.Production.sound(c,"Helicopter",0,0,true)
            PZDevKit.Production.zombie(c,2,2)
            calls=calls+1; error("cue failure")
        end):run()
    drive(20)
    eq(calls,1); eq(report().status,"failed")
    assert(report().reason:find("cue failure",1,true))
    eq(SOUNDS[1].stopped,true); eq(SPAWNS[1].removed,true)
    eq(ISUIHandler.allUIVisible,true); eq(PLAYER:isGodMod(),false)
end

function T.cleanup_failure_still_restores_other_resources()
    PZDevKit.Production.scene("cleanup",{countdown=0,duration=.5})
        :cue(0,"objects",function(c)
            PZDevKit.Production.sound(c,"Helicopter",0,0,true)
            PZDevKit.Production.zombie(c,2,2).failRemoval=true
        end):run()
    drive(20)
    eq(report().status,"failed"); eq(SOUNDS[1].stopped,true)
    eq(ISUIHandler.allUIVisible,true); eq(MUTE,false); eq(PLAYER:isGodMod(),false)
end

function T.hidden_interface_and_existing_flags_are_preserved()
    ISUIHandler.allUIVisible=false; MUTE=true; PLAYER:setGodMod(true); PLAYER:setGhostMode(true)
    PZDevKit.Production.scene("existing",{countdown=0,duration=.2,observe=true}):run()
    drive(10)
    eq(report().status,"passed"); eq(#UI_CALLS,0); eq(ISUIHandler.allUIVisible,false)
    eq(MUTE,true); eq(PLAYER:isGodMod(),true); eq(PLAYER:isGhostMode(),true)
    eq(PLAYER:isInvisible(),false)
end

function T.unrelated_engine_scenario_is_never_stopped()
    PZDevKit.Scenario.scenario("foreign"):wait(5):run()
    PZDevKit.Production.stop(); eq(report().status,"running")
    local ok=pcall(function() PZDevKit.Production.demo():run() end)
    eq(ok,false); eq(report().status,"running"); eq(#UI_CALLS,0)
end

function T.multiplayer_and_missing_debug_are_rejected_before_changes()
    for _,mode in ipairs({"client","server","no-debug"}) do
        CLIENT=mode=="client"; SERVER=mode=="server"; DEBUG=mode~="no-debug"
        eq(pcall(function() PZDevKit.Production.demo():run() end),false)
        eq(#Events.OnTick.handlers,0); eq(#SPAWNS,0); eq(#UI_CALLS,0)
    end
end

function T.bad_terrain_stops_before_countdown_or_hud_changes()
    FREE=false
    PZDevKit.Production.demo({countdown=0}):run(); drive(10)
    eq(report().status,"failed"); eq(#SPAWNS,0); eq(#UI_CALLS,0)
    FREE=true
    PZDevKit.Production.demo({countdown=0}):run(); PZDevKit.Production.stop()
    eq(report().status,"cancelled")
end

function T.pause_does_not_skip_or_duplicate_cues()
    local calls=0
    PZDevKit.Production.scene("pause",{countdown=0,duration=1})
        :cue(.5,"once",function() calls=calls+1 end):run()
    drive(4); SPEED=0; tick(20000); eq(calls,0)
    SPEED=1; drive(20)
    eq(calls,1); eq(report().status,"passed")
end

function T.demo_uses_real_action_adapter_and_cleans_up()
    PZDevKit.Production.demo({countdown=0}):run(); drive(250)
    eq(report().status,"passed"); eq(#SPAWNS,1); eq(SPAWNS[1].target,PLAYER)
    eq(SPAWNS[1].removed,true); eq(THUNDER,1)
    eq(PLAYER.x,10.5); eq(PLAYER.y,20.5)
end

function T.observation_has_no_player_movement_and_restores_visibility()
    PZDevKit.Production.observation({countdown=0}):run(); drive(250)
    eq(report().status,"passed"); eq(#SPAWNS,2)
    eq(SPAWNS[1].goal.x,4.5); eq(SPAWNS[2].goal.x,4.5)
    eq(PLAYER.x,10.5); eq(PLAYER:isInvisible(),false)
    eq(PLAYER:getDoRender(),true); eq(PLAYER:getAlpha(),1)
    eq(SPAWNS[1].removed,true); eq(SPAWNS[2].removed,true)
end

function T.running_sprinting_and_crouching_are_restored_after_movement()
    PZDevKit.Production.scene("movement",{countdown=0,duration=3})
        :runBy(3,0):sprintBy(0,0):crouch(true):sneakBy(2,0):stand():run()
    drive(80)
    eq(report().status,"passed"); eq(PLAYER.x,12.5)
    eq(STATES.ForceRun,false); eq(STATES.ForceSprint,false); eq(STATES.Sneaking,false)
end

function T.run_inputs_are_reasserted_and_cancelled_after_path_failure()
    PZDevKit.Production.scene("run",{countdown=0,duration=2}):runBy(5,0):run()
    for _=1,6 do tick() end
    eq(STATES.ForceRun,true); eq(STATES.Running,true)
    STATES.ForceRun=false; tick(); eq(STATES.ForceRun,true)
    PATH.failed(); tick()
    eq(report().status,"failed"); eq(STATES.ForceRun,false); eq(STATES.Running,false)
end

function T.gesture_waits_for_animation_and_is_stopped_on_cancel()
    PZDevKit.Production.scene("gesture",{countdown=0,duration=2}):emote("wavehi"):run()
    for _=1,4 do tick() end
    eq(VARIABLES.emote,"wavehi"); eq(VARIABLES.EmotePlaying,true)
    PZDevKit.Production.stop(); eq(VARIABLES.EmotePlaying,false)
    PZDevKit.Production.scene("gesture again",{countdown=0,duration=2}):emote("saluteformal"):run()
    drive(40); eq(report().status,"passed")
end

function T.eating_and_drinking_wait_for_consumption()
    PZDevKit.Production.scene("consume",{countdown=0,duration=2}):eat(FOOD,.5):drink(BOTTLE,.5):run()
    drive(40); eq(report().status,"passed"); eq(FOOD.hunger,-.15); eq(FLUID.amount,.5)
end

function T.reload_uses_inventory_ammo_and_missing_ammo_fails()
    PLAYER.primary=GUN
    PZDevKit.Production.scene("reload",{countdown=0,duration=2}):reload():run()
    drive(40); eq(report().status,"passed"); eq(GUN.ammo,6)
    GUN.ammo=0; BULLETS=false
    PZDevKit.Production.scene("empty",{countdown=0,duration=2}):reload():run()
    drive(20); eq(report().status,"failed"); eq(GUN.ammo,0)
end

function T.shooting_waits_for_real_swing_events_and_consumes_ammo()
    PLAYER.primary=GUN
    PZDevKit.Production.scene("shoot",{countdown=0,duration=3})
        :shootAt({x=13,y=20,z=0},{shots=2,aimTime=.2}):run()
    drive(60); eq(report().status,"passed"); eq(SHOTS,2); eq(GUN.ammo,1)
    eq(#Events.OnWeaponSwingHitPoint.handlers,0); eq(STATES.ForceAim,false)
    eq(MX,50); eq(MY,70)
end

function T.final_confirmed_shot_can_kill_target_before_the_next_scene_poll()
    PLAYER.primary=GUN; SKIP_SHOT_EVENT=true
    local dead=false
    local target={isDead=function() return dead end,getX=function() return 13 end,
        getY=function() return 20 end,getZ=function() return 0 end}
    PZDevKit.Production.scene("final hit",{countdown=0,duration=2})
        :shootAt(target,{shots=1,aimTime=.2}):run()
    for _=1,8 do tick() end
    assert(ATTACK)
    GUN.ammo=GUN.ammo-1; dead=true
    for _,handler in ipairs(Events.OnWeaponSwingHitPoint.handlers) do handler(PLAYER,GUN) end
    ATTACK=nil
    drive(25)
    eq(report().status,"passed"); eq(#Events.OnWeaponSwingHitPoint.handlers,0)
    eq(STATES.ForceAim,false)
end

function T.empty_gun_and_absent_shot_event_never_report_success()
    PLAYER.primary=GUN; GUN.ammo=0
    PZDevKit.Production.scene("empty shot",{countdown=0,duration=2}):shootAt({x=13,y=20,z=0}):run()
    drive(30); eq(report().status,"failed"); eq(SHOTS,0)
    GUN.ammo=3; SKIP_SHOT_EVENT=true
    PZDevKit.Production.scene("no event",{countdown=0,duration=2})
        :shootAt({x=13,y=20,z=0},{timeout=1}):run()
    drive(30); eq(report().status,"failed"); eq(#Events.OnWeaponSwingHitPoint.handlers,0)
end

function T.door_aliases_delegate_to_vanilla_and_check_open_state()
    local door={kind="IsoDoor",opened=false,IsOpen=function(s) return s.opened end,
        getSquare=function() return {getX=function() return 10 end,getY=function() return 20 end,
            getZ=function() return 0 end} end}
    ISOpenCloseDoor.new=function(_,p,obj) return {character=p,apply=function() obj.opened=not obj.opened end} end
    PZDevKit.Production.scene("door",{countdown=0,duration=2}):openDoor(door):closeDoor(door):run()
    drive(40); eq(report().status,"passed"); eq(door.opened,false)
end

function T.gesture_hold_ends_a_loop_without_manual_input()
    PZDevKit.Production.scene("loop",{countdown=0,duration=2}):emote("surrender",{hold=.5}):run()
    for _=1,25 do tick() end
    eq(report().status,"passed"); eq(VARIABLES.EmotePlaying,false)
end

function T.foreign_shot_events_and_unchanged_ammo_are_not_accepted()
    PLAYER.primary=GUN; SKIP_SHOT_EVENT=true
    PZDevKit.Production.scene("shot check",{countdown=0,duration=2})
        :shootAt({x=13,y=20,z=0},{aimTime=.2,timeout=1}):run()
    for _=1,8 do tick() end
    assert(ATTACK)
    for _,handler in ipairs(Events.OnWeaponSwingHitPoint.handlers) do handler({},GUN) end
    eq(report().status,"running")
    for _,handler in ipairs(Events.OnWeaponSwingHitPoint.handlers) do handler(PLAYER,GUN) end
    tick(); eq(report().status,"failed")
    assert(report().reason:find("aucune munition consommee",1,true))
end

function T.aiming_restores_cursor_and_rejects_offscreen_targets()
    PZDevKit.Production.scene("aim",{countdown=0,duration=2}):aimAt({x=13,y=20,z=0},.5):run()
    drive(30); eq(report().status,"passed"); eq(MX,50); eq(MY,70)
    PZDevKit.Production.scene("far aim",{countdown=0,duration=2}):aimAt({x=4000,y=20,z=0},.5):run()
    drive(20); eq(report().status,"failed"); eq(STATES.ForceAim,false)
end

function T.actions_file_can_load_before_core_without_initializing_a_take()
    PZDevKit.Production=nil
    dofileMod("PZDevKit/Actions")
    dofileMod("PZDevKit/Production")
    assert(type(PZDevKit.Production.attachActor)=="function")
    PZDevKit.Production.scene("load order")
    eq(#Events.OnTick.handlers,0); eq(#SPAWNS,0)
end

function T.closed_or_empty_bottle_is_rejected_without_consumption()
    FLUID.canPlayerEmpty=function() return false end
    PZDevKit.Production.scene("sealed",{countdown=0,duration=2}):drink(BOTTLE):run()
    drive(20); eq(report().status,"failed"); eq(FLUID.amount,1)
end

function T.stop_from_cue_does_not_queue_a_new_action()
    PZDevKit.Production.scene("stop",{countdown=0,duration=2})
        :cue(.1,"stop",function() PZDevKit.Production.stop() end):moveBy(2,0):run()
    drive(30); eq(report().status,"cancelled"); eq(#QUEUE,0)
end

return T
