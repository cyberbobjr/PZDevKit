require "PZDevKit/Demos"
require "ISUI/ISCollapsableWindow"
require "ISUI/ISComboBox"

local D = PZDevKit.Production
local Window=ISCollapsableWindow:derive("PZDirectorWindow")
local instance
local function text(key) return getText("IGUI_PZDirector_" .. key) end

function Window:createChildren()
    ISCollapsableWindow.createChildren(self)
    local margin=16
    local line=getTextManager():getFontHeight(UIFont.Small)+8
    local y=self:titleBarHeight()+margin
    self.choice=ISComboBox:new(margin,y,self.width-2*margin,line,self,nil)
    self.choice:initialise()
    self.choice:addOption(text("Actor"))
    self.choice:addOption(text("Observer"))
    self:addChild(self.choice)
    y=y+line+margin
    self.start=ISButton:new(margin,y,self.width-2*margin,line,text("Start"),self,Window.startTake)
    self.start:initialise()
    self:addChild(self.start)
    y=y+line+8
    self.stopButton=ISButton:new(margin,y,self.width-2*margin,line,text("Stop"),self,function() D.stop() end)
    self.stopButton:initialise()
    self:addChild(self.stopButton)
    self.statusY=y+line+margin
    self.errorY=self.statusY+line*3
    self:setHeight(self.errorY+line*5+margin)
end

function Window:startTake()
    local factory=self.choice.selected==2 and D.observation or D.demo
    local ok,err=pcall(function() factory():run() end)
    self.error=not ok and tostring(err) or nil
    if self.error then print("[PZDirector] " .. self.error) end
end

function Window:prerender()
    ISCollapsableWindow.prerender(self)
    local line=getTextManager():getFontHeight(UIFont.Small)+8
    local status=D.status()
    local running=status and status.status=="running"
    self.start:setEnable(not running)
    self.stopButton:setEnable(running==true)
    local label=status and (status.status .. " / " .. string.format("%.1fs",status.duration or 0)) or text("Idle")
    self:drawText(label,16,self.statusY,1,1,1,1,UIFont.Small)
    if status and status.label then self:drawText(status.label,16,self.statusY+line,0.9,0.8,0.6,1,UIFont.Small) end
    self:drawText(text("Requirements"),16,self.errorY,0.8,0.8,0.8,1,UIFont.Small)
    self:drawText(text("Recording"),16,self.errorY+line,0.8,0.8,0.8,1,UIFont.Small)
    self:drawText(text("Emergency"),16,self.errorY+line*2,1,0.7,0.4,1,UIFont.Small)
    if self.error or (status and status.reason) then
        self:drawText(text("Error"),16,self.errorY+line*3,1,0.45,0.4,1,UIFont.Small)
    end
end

function Window:close()
    self:setVisible(false)
    self:removeFromUIManager()
    instance=nil
end

function D.open()
    if not isDebugEnabled() or isClient() or isServer() or not getSpecificPlayer(0) then return end
    if instance then instance:setVisible(true); instance:bringToTop(); return end
    local tm=getTextManager()
    local width=420
    for _,key in ipairs({"Actor","Observer","Requirements","Recording","Emergency"}) do
        width=math.max(width,tm:MeasureStringX(UIFont.Small,text(key))+48)
    end
    local w=Window:new(40,80,width,340)
    w:setTitle(text("Title"))
    w.resizable=false
    w:initialise()
    w:addToUIManager()
    instance=w
end

local function onContext(player,context,_,test)
    if player~=0 or not isDebugEnabled() or isClient() or isServer() then return end
    if test then return end
    context:addOption(text("Title"),nil,D.open)
end

local function onKey(key)
    local ctrl=isKeyDown(Keyboard.KEY_LCONTROL) or isKeyDown(Keyboard.KEY_RCONTROL)
    local shift=isKeyDown(Keyboard.KEY_LSHIFT) or isKeyDown(Keyboard.KEY_RSHIFT)
    if not ctrl or not shift then return end
    if key==Keyboard.KEY_F10 then D.open() end
    if key==Keyboard.KEY_F11 then D.stop("Arret d'urgence") end
end

-- Lua reload: remove exactly our old subscriptions before replacing them.
if D.onContext then Events.OnFillWorldObjectContextMenu.Remove(D.onContext) end
if D.onKey then Events.OnKeyPressed.Remove(D.onKey) end
D.onContext=onContext
D.onKey=onKey
Events.OnFillWorldObjectContextMenu.Add(onContext)
Events.OnKeyPressed.Add(onKey)
