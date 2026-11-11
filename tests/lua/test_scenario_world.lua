local T={}
local function list(values)
    return {size=function() return #values end,get=function(_,i) return values[i+1] end}
end
function T.setup()
    assert(loadstring(readTests("test_engine.lua")))().setup()
    CLIENT,SERVER,FREE,WATER,OCCUPIED=false,false,true,false,false
    SPAWNS,REMOVED,ADDED,PERK_LEVEL,TIME=0,0,0,0,12
    isClient=function() return CLIENT end
    isServer=function() return SERVER end
    IsoDirections={N=1,S=2,E=3,W=4}
    IsoFlagType={water="water"}
    ItemTag={GENERATOR="Generator"}
    PLAYER.teleportTo=function(s,x,y,z) s.x,s.y,s.z=x,y,z end
    PLAYER.setPrimaryHandItem=function(s,item) s.primary=item end
    PLAYER.setSecondaryHandItem=function(s,item) s.secondary=item end
    INV.AddItem=function(_,item) ADDED=ADDED+1; item.container=INV; return item end
    INV.Remove=function(_,item) REMOVED=REMOVED+1; item.container=nil end
    local function item(name)
        return {kind="InventoryItem",getFullType=function() return name end,
            getContainer=function(s) return s.container end,getWorldItem=function(s) return s.world end,
            isHumanCorpse=function() return name=="Base.Corpse" end,isAnimalCorpse=function() return false end,
            hasTag=function() return false end,getWorldObjectSprite=function() return nil end}
    end
    -- The observed 42.21 Lua environment has instanceItem, not this Java class.
    InventoryItemFactory=nil
    instanceItem=function(name) return item(name) end
    local function script(name)
        return {getFullName=function() return name end,getObsolete=function() return false end,
            getSkinCount=function() return 2 end}
    end
    ScriptManager={instance={getItem=function(_,name)
        if name=="Base.TestItem" or name=="Base.Corpse" then return script(name) end
    end,getVehicle=function(_,name) if name=="Base.TestCar" then return script(name) end end,
        getAllItems=function() return list({script("Other.Tool"),script("Base.TestItem")}) end,
        getAllVehicleScripts=function() return list({script("Base.TestCar")}) end}}
    SQUARE={isFree=function() return FREE end,getProperties=function() return {has=function() return WATER end} end,
        AddWorldInventoryItem=function(s,it)
            ADDED=ADDED+1
            it.world={getSquare=function() return s end}
            return it
        end,transmitRemoveItemFromSquare=function() REMOVED=REMOVED+1 end}
    getCell=function() return {getGridSquare=function() return LOADED and SQUARE or nil end} end
    addVehicleDebug=function(name,dir,skin,sq)
        assert(name=="Base.TestCar" and dir==1 and skin==1 and sq==SQUARE)
        SPAWNS=SPAWNS+1
        return {kind="BaseVehicle",getSquare=function() return sq end,getSqlId=function() return 1 end,
            getMaxPassengers=function() return 1 end,getCharacter=function() return OCCUPIED and PLAYER or nil end,
            createVehicleKey=function() return item("Base.CarKey") end,
            permanentlyRemove=function() REMOVED=REMOVED+1 end}
    end
    getAllOutfits=function() return list({"Police"}) end
    addZombiesInOutfit=function(x,y,z,count,outfit,chance,crawler,fall,fake,knocked,invulnerable,sitting,health)
        assert(x==15 and y==20 and z==0 and outfit=="Police" and chance==100 and health==2)
        assert(crawler==true and fall==false and fake==false and knocked==false and invulnerable==false and sitting==false)
        SPAWNS=SPAWNS+count
        local zombies={}
        for i=1,count do zombies[i]={kind="IsoZombie",useless=false,isUseless=function(s) return s.useless end,
            setUseless=function(s,b) s.useless=b end,removeFromWorld=function() REMOVED=REMOVED+1 end,
            removeFromSquare=function() end} end
        return list(zombies)
    end
    for name,methods in pairs({god={"isGodMod","setGodMod"},ghost={"isGhostMode","setGhostMode"},
        invisible={"isInvisible","setInvisible"},instant={"isTimedActionInstantCheat","setTimedActionInstantCheat"},
        carry={"isUnlimitedCarry","setUnlimitedCarry"}}) do
        local key=name
        PLAYER[key]=false
        PLAYER[methods[1]]=function(s) return s[key] end
        PLAYER[methods[2]]=function(s,b) s[key]=b end
    end
    local hunger={getMinimumValue=function() return 0 end,getMaximumValue=function() return 1 end}
    CharacterStat={getById=function(name) return name=="Hunger" and hunger or nil end}
    PLAYER.hunger=.5
    PLAYER.getStats=function() return {get=function() return PLAYER.hunger end,set=function(_,_,value) PLAYER.hunger=value end} end
    PLAYER.getBodyDamage=function() return {RestoreToFullHealth=function() PLAYER.healed=true end} end
    Perks={MAX={},None={},FromString=function(name) return name=="Aiming" and "Aiming" or nil end}
    PLAYER.getPerkLevel=function() return PERK_LEVEL end
    PLAYER.setPerkLevelDebug=function(_,perk,level) assert(perk=="Aiming"); PERK_LEVEL=level end
    PLAYER.getXp=function() return {setXPToLevel=function(_,perk,level) assert(perk=="Aiming"); XP_LEVEL=level end} end
    getGameTime=function() return {getTimeOfDay=function() return TIME end,setTimeOfDay=function(_,n) TIME=n end} end
    getClimateManager=function() return {stopWeatherAndThunder=function() WEATHER="clear" end,
        triggerCustomWeatherStage=function(_,stage,hours) WEATHER,HOURS=stage,hours; return true end} end
    dofileMod("PZDevKit/World")
end
local function tick()
    NOW=NOW+100
    Events.OnTick.handlers[1]()
end
function T.teleport_waits_for_loaded_destination_and_refuses_busy_player()
    local D=PZDevKit.World
    QUEUE[1]={}
    assert(not pcall(D.teleport,30,40,0))
    QUEUE[1]=nil
    assert(not pcall(D.teleport,0/0,40,0))
    LOADED=false
    assert(not pcall(D.teleport,30,40,.5))
    PZDevKit.Scenario.scenario("fixture"):teleport(30.9,40.9,0):run()
    tick(); assert(PLAYER.x==30 and PZDevKit.Scenario.lastReport.status=="running")
    LOADED=true; tick(); assert(PZDevKit.Scenario.lastReport.status=="passed")
end
function T.documented_file_fixture_equips_then_cleans_up()
    local factory=assert(loadstring(readExample("04-equipped-fixture.lua")))()
    local scenario=factory({itemType="Base.TestItem"})
    scenario:run(); tick(); tick()
    local action=QUEUE[1]
    assert(action and action.equip)
    PLAYER.primary=action.equip; QUEUE[1]=nil
    tick(); tick()
    assert(PZDevKit.Scenario.lastReport.status=="passed" and REMOVED==1 and PLAYER.primary==nil)
end
return T
