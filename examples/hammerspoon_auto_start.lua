--[[
    Example: Auto-start Keychron MIDI Bridge with Ableton Live
    Add this to your ~/.hammerspoon/init.lua to automatically start/stop
    the bridge when Ableton Live opens/closes.
]]

local PYTHON_VENV = "/path/to/keychron-ableton-bridge/venv/bin/python"
local BRIDGE_SCRIPT = "/path/to/keychron-ableton-bridge/bridge.py"

local bridgeTask = nil

local function startBridge()
    if not bridgeTask or not bridgeTask:isRunning() then
        bridgeTask = hs.task.new(PYTHON_VENV, function(exitCode, stdOut, stdErr)
            bridgeTask = nil
        end, { BRIDGE_SCRIPT })
        bridgeTask:start()
        print("[Keychron Bridge] Started")
    end
end

local function stopBridge()
    if bridgeTask and bridgeTask:isRunning() then
        bridgeTask:terminate()
        bridgeTask = nil
        print("[Keychron Bridge] Stopped")
    end
    hs.execute("pkill -f 'keychron-ableton-bridge/bridge.py'", true)
end

-- Watch for Ableton Live
abletonWatcher = hs.application.watcher.new(function(applicationName, eventType, appObject)
    if applicationName == "Live" then
        if eventType == hs.application.watcher.launched then
            -- Small delay to let Ableton fully load
            hs.timer.doAfter(2.0, startBridge)
        elseif eventType == hs.application.watcher.terminated then
            stopBridge()
        end
    end
end)
abletonWatcher:start()
