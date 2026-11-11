-- Safe both when auto-loaded before Core and when required by Core.
require "PZDevKit/Game"
require "TimedActions/ISReloadWeaponAction"
require "TimedActions/ISRackFirearm"

PZDevKit = PZDevKit or {}
local D = PZDevKit.Production or {}
PZDevKit.Production = D
local P = PZDevKit.Scenario
local emotes=PZDevKit.World.EMOTES

local function fraction(value)
    value=value or 1
    assert(type(value)=="number" and value>0 and value<=1,"Fraction entre 0 et 1")
    return value
end

function D.captureActor(c)
    local p=c.player
    c.vars.director.actor={run=p:isForceRun(),sprint=p:isForceSprint(),forceAim=p:isForceAim(),
        aiming=p:isAiming(),sneak=p:isSneaking(),shove=p:isDoShove()}
end

function D.restoreActor(c)
    local t=c.vars.director
    local p=c.player
    if t.shotListener then Events.OnWeaponSwingHitPoint.Remove(t.shotListener) end
    if t.emoteOwned then p:setVariable("EmotePlaying",false) end
    if t.actor then
        p:setForceRun(t.actor.run); p:setForceSprint(t.actor.sprint)
        p:setForceAim(t.actor.forceAim); p:setIsAiming(t.actor.aiming); p:setSneaking(t.actor.sneak)
        p:setDoShove(t.actor.shove)
        p:setRunning(false); p:setSprinting(false)
    end
    if t.mouse then
        setMouseXY(t.mouse.x,t.mouse.y+getCore():getOffscreenHeight(0)-getCore():getScreenHeight())
    end
end

local function point(c,selector)
    local x,y,z
    local selected=selector
    if type(selected)=="function" then selected,y,z=selected(c) end
    if type(selected)=="number" then x=selected
    elseif type(selected)=="table" and selected.x then x,y,z=selected.x,selected.y,selected.z
    else
        assert(selected,"Cible absente")
        assert(not selected:isDead(),"Cible morte")
        x,y,z=selected:getX(),selected:getY(),selected:getZ()
        z=z+0.7 -- aim at the torso rather than the ground under the target
    end
    assert(type(x)=="number" and type(y)=="number" and type(z)=="number","Cible: x,y,z requis")
    assert(x==x and y==y and z==z and math.abs(x)<math.huge and math.abs(y)<math.huge,
        "Coordonnees de cible invalides")
    assert(math.floor(z)==math.floor(c.player:getZ()),"Viser sur le meme etage")
    assert(getCell():getGridSquare(math.floor(x),math.floor(y),math.floor(z)),"Cible hors zone chargee")
    return x,y,z
end

local function aim(c,selector)
    local p=c.player
    assert(c.playerIndex==0 and p:getJoypadBind()==-1,"Scripted aiming: player 0 on keyboard and mouse only")
    local x,y,z=point(c,selector)
    local sx=isoToScreenX(c.playerIndex,x,y,z)
    local sy=isoToScreenY(c.playerIndex,x,y,z)
    local core=getCore()
    assert(sx>=0 and sx<core:getScreenWidth() and sy>=0 and sy<core:getScreenHeight(),
        "Cible hors cadre: dezoomer avant la prise")
    local t=c.vars.director
    if not t.mouse then t.mouse={x=getMouseX(),y=getMouseY()} end
    -- Mouse.setXY in 42.21 flips Y using offscreen height; Mouse.update uses screen
    -- height. Compensate for this difference when zoom is not 100 percent.
    setMouseXY(math.floor(sx),math.floor(sy+core:getOffscreenHeight(0)-core:getScreenHeight()))
    p:setForceRun(false); p:setForceSprint(false); p:setForceAim(true); p:setIsAiming(true)
    p:setDoShove(false)
end

function D.updateActor(c)
    local t=c.vars.director
    local p=c.player
    if t.motion then
        p:setForceAim(false); p:setIsAiming(false)
        p:setForceRun(t.motion=="run"); p:setForceSprint(t.motion=="sprint")
        p:setRunning(t.motion=="run"); p:setSprinting(t.motion=="sprint")
    end
    if t.crouch~=nil then p:setSneaking(t.crouch) end
    if t.aimTarget then aim(c,t.aimTarget) end
end

local function weapon(c,selector)
    local gun=selector and P.Game.item(c,selector) or c.player:getPrimaryHandItem()
    assert(gun and instanceof(gun,"HandWeapon") and gun:isRanged() and gun:getCondition()>0,
        "Arme a feu utilisable requise")
    assert(c.player:getPrimaryHandItem()==gun,"Equiper l'arme avant l'action")
    return gun
end

local function owned(c,selector)
    local item=P.Game.item(c,selector)
    assert(item:getContainer() and item:getContainer():getOutermostContainer()==c.player:getInventory(),
        "Objet requis dans l'inventaire ou un sac porte")
    return item
end

local function motion(scene,dx,dy,timeout,mode)
    return scene:call("Allure: " .. mode,function(c)
        local t=c.vars.director
        assert(not t.aimTarget,"Terminer la visee avant de se deplacer")
        t.beforeMotion={run=c.player:isForceRun(),sprint=c.player:isForceSprint(),sneak=c.player:isSneaking()}
        t.motion=mode
        t.crouch=mode=="sneak"
        D.updateActor(c)
    end):moveBy(dx,dy,timeout):call("Fin du deplacement",function(c)
        local t=c.vars.director
        t.motion=nil; t.crouch=t.beforeMotion.sneak
        c.player:setForceRun(t.beforeMotion.run); c.player:setForceSprint(t.beforeMotion.sprint)
        c.player:setRunning(false); c.player:setSprinting(false); c.player:setSneaking(t.crouch)
    end)
end

-- Capture helpers, shared by every scene. The external director (pzdev film) reads them:
-- MARK lines from console.txt (timestamps for editing), PZDirector_<name>.png from Zomboid/Screenshots.
local function captureName(name)
    assert(type(name)=="string" and name:match("^[%w_%-]+$"),"Nom de capture : lettres, chiffres, _ et - seulement")
    return name
end
D.captureName=captureName

function D.attachActor(scene)
    scene.mark=function(self,name)
        local label=captureName(name)
        return self:call("REPERE: "..label,function() print("[PZDirector] MARK|"..label) end)
    end
    scene.screenshot=function(self,name)
        local label=captureName(name)
        return self:call("CAPTURE: "..label,function()
            takeScreenshot("PZDirector_"..label..".png")
            print("[PZDirector] SCREENSHOT|"..label)
        end)
    end
    scene.runBy=function(self,dx,dy,timeout) return motion(self,dx,dy,timeout,"run") end
    scene.sprintBy=function(self,dx,dy,timeout) return motion(self,dx,dy,timeout,"sprint") end
    scene.sneakBy=function(self,dx,dy,timeout) return motion(self,dx,dy,timeout,"sneak") end
    scene.crouch=function(self,value)
        assert(type(value)=="boolean","crouch: booleen requis")
        return self:call(value and "S'accroupir" or "Se relever",function(c)
            c.vars.director.crouch=value; c.player:setSneaking(value)
        end)
    end
    scene.stand=function(self) return self:crouch(false) end
    scene.emote=function(self,name,timeout)
        assert(emotes[name],"Geste inconnu: utiliser un identifiant vanilla exact")
        local hold
        if type(timeout)=="table" then
            hold=timeout.hold
            timeout=timeout.timeout or ((hold or 5)+10)
            assert(hold==nil or (type(hold)=="number" and hold>0 and hold<=60),"hold: 0 a 60 s")
        end
        return self:step("Geste: " .. name,{timeout=timeout or 15,
            start=function(c,data)
                assert(not c.player:getVariableBoolean("EmotePlaying"),"Geste deja en cours")
                assert(P.Game.queueSize(c.player)==0,"File d'actions occupee")
                c.vars.director.emoteOwned=true
                c.player:playEmote(name)
                data.started=true; data.start=c.vars.director.elapsed
            end,
            poll=function(c,data)
                if hold and c.vars.director.elapsed-data.start>=hold then
                    c.player:setVariable("EmotePlaying",false)
                end
                if data.started and not c.player:getVariableBoolean("EmotePlaying") then
                    c.vars.director.emoteOwned=false
                    return true
                end
                return false
            end})
    end
    scene.eat=function(self,selector,percent,timeout)
        percent=fraction(percent)
        local item,before
        return self:interact("Manger",function(c)
            item=owned(c,selector)
            assert(instanceof(item,"Food") and item:getHungChange()<0,"Aliment mangeable requis")
            before=math.abs(item:getHungChange())
            ISInventoryPaneContextMenu.eatItem(item,percent,c.playerIndex)
            assert(P.Game.queueSize(c.player)>0,"Action manger refusee")
        end,function()
            return item:getContainer()==nil or math.abs(item:getHungChange())<before
        end,timeout or 60)
    end
    scene.drink=function(self,selector,percent,timeout)
        percent=fraction(percent)
        local fluid,before
        return self:interact("Boire",function(c)
            local item=owned(c,selector)
            fluid=item:getFluidContainer()
            assert(fluid and not fluid:isEmpty() and fluid:canPlayerEmpty() and fluid:getCapacity()<=3,
                "Recipient ouvert non vide requis (3 litres maximum)")
            before=fluid:getAmount()
            ISInventoryPaneContextMenu.onDrinkFluid(item,percent,c.player)
            assert(P.Game.queueSize(c.player)>0,"Action boire refusee")
        end,function() return fluid:getAmount()<before end,timeout or 60)
    end
    scene.reload=function(self,selector,timeout)
        local gun,before
        return self:interact("Recharger",function(c)
            gun=weapon(c,selector); before=gun:getCurrentAmmoCount()
            assert(before<gun:getMaxAmmo(),"Arme deja pleine")
            ISReloadWeaponAction.BeginAutomaticReload(c.player,gun)
            assert(P.Game.queueSize(c.player)>0,"Munitions/chargeur manquants ou arme bloquee")
        end,function() return gun:getCurrentAmmoCount()>before end,timeout or 60)
    end
    scene.rack=function(self,selector,timeout)
        local gun
        return self:interact("Armer / des-enrayer",function(c)
            gun=weapon(c,selector)
            assert(ISReloadWeaponAction.canRack(gun),"Impossible d'armer cette arme")
            ISTimedActionQueue.add(ISRackFirearm:new(c.player,gun))
        end,function(c) return ISReloadWeaponAction.canShoot(c.player,gun)==true end,timeout or 30)
    end
    scene.aimAt=function(self,selector,seconds)
        seconds=seconds or 1
        assert(type(seconds)=="number" and seconds>0 and seconds<=60,"Duree de visee entre 0 et 60 s")
        return self:step("Viser",{timeout=seconds+10,start=function(c,data)
            assert(P.Game.queueSize(c.player)==0,"Terminer le deplacement avant de viser")
            data.before=c.player:isForceAim(); data.aiming=c.player:isAiming()
            c.vars.director.aimTarget=selector
            aim(c,selector)
            data.start=c.vars.director.elapsed
        end,poll=function(c,data)
            if c.vars.director.elapsed-data.start>=seconds and c.player:isAiming() then
                c.vars.director.aimTarget=nil
                c.player:setForceAim(data.before); c.player:setIsAiming(data.aiming)
                return true
            end
            return false
        end})
    end
    scene.shootAt=function(self,selector,options)
        options=options or {}
        local count=options.shots or 1
        local delay=options.interval or .6
        local settle=options.aimTime or .7
        assert(type(count)=="number" and count==math.floor(count) and count>=1 and count<=100,"shots: 1 a 100")
        assert(type(delay)=="number" and delay>=.1 and delay<=10,"interval: 0.1 a 10 s")
        assert(type(settle)=="number" and settle>=.2 and settle<=10,"aimTime: 0.2 a 10 s")
        return self:step("Tirer " .. count .. " coup(s)",{timeout=options.timeout or count*(delay+5)+15,
            start=function(c,data)
                assert(P.Game.queueSize(c.player)==0,"Terminer les actions avant de tirer")
                assert(not c.player:isUnlimitedAmmo(),"Desactiver munitions illimitees pour verifier les tirs")
                data.gun=weapon(c,options.weapon)
                data.shots=0; data.before=c.player:isForceAim(); data.aiming=c.player:isAiming()
                data.next=c.vars.director.elapsed+settle
                c.vars.director.aimTarget=selector
                c.vars.director.shotListener=function(p,gun)
                    if p==c.player and gun==data.gun and data.pending then
                        local ammo=gun:getCurrentAmmoCount()+(gun:isRoundChambered() and 1 or 0)
                        if ammo<data.beforeAmmo then
                            data.shots=data.shots+1
                            -- The final shot can kill the target before the next
                            -- scene poll. Finish the attack without re-aiming at a corpse.
                            if data.shots>=count then c.vars.director.aimTarget=nil end
                        else data.error="Tir non confirme: aucune munition consommee" end
                        data.pending=false
                    end
                end
                Events.OnWeaponSwingHitPoint.Add(c.vars.director.shotListener)
                aim(c,selector)
            end,
            poll=function(c,data)
                local p=c.player
                assert(not data.error,data.error)
                assert(p:getPrimaryHandItem()==data.gun,"Arme changee pendant le tir")
                if data.shots>=count and not p:isAttackStarted() and P.Game.queueSize(p)==0 then
                    Events.OnWeaponSwingHitPoint.Remove(c.vars.director.shotListener)
                    c.vars.director.shotListener=nil; c.vars.director.aimTarget=nil
                    p:setForceAim(data.before); p:setIsAiming(data.aiming)
                    c.queueOwned=false
                    return true
                end
                if not data.pending and data.shots<count and c.vars.director.elapsed>=data.next
                    and not p:isAttackStarted() and p:isWeaponReady() and p:CanAttack()
                    and p:getRecoilDelay()<=0 and p:getMeleeDelay()<=0 and P.Game.queueSize(p)==0 then
                    assert(ISReloadWeaponAction.canShoot(p,data.gun),"Arme vide, en securite ou enrayee: recharger/armer")
                    data.pending=true
                    data.beforeAmmo=data.gun:getCurrentAmmoCount()+(data.gun:isRoundChambered() and 1 or 0)
                    data.next=c.vars.director.elapsed+delay
                    c.queueOwned=true -- includes the vanilla rack queued after some shots
                    -- The ballistics controller only exists once the engine has updated an aiming
                    -- firearm (IsoGameCharacter.java:8437-8441); a shot without it throws a NPE in
                    -- CombatManager.isHittableBallisticsTarget.
                    if p:getBallisticsController()==nil then p:updateBallistics() end
                    ISReloadWeaponAction.attackHook(p,0,data.gun)
                end
                return false
            end})
    end
    scene.openDoor=function(self,selector,timeout) return self:door(selector,true,timeout) end
    scene.closeDoor=function(self,selector,timeout) return self:door(selector,false,timeout) end
    return scene
end

return D
