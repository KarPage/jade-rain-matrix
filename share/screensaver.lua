-- Exit the Jade Rain Matrix screensaver on any key or mouse button.
local function quit()
  mp.commandv("quit")
end

for code = 33, 126 do
  mp.add_forced_key_binding(string.char(code), "jade-rain-" .. code, quit)
end

local named = {
  "SPACE", "ENTER", "ESC", "BS", "TAB",
  "UP", "DOWN", "LEFT", "RIGHT",
  "MBTN_LEFT", "MBTN_RIGHT", "MBTN_MID",
  "WHEEL_UP", "WHEEL_DOWN", "KP_ENTER",
}
for _, key in ipairs(named) do
  mp.add_forced_key_binding(key, "jade-rain-" .. key, quit)
end
