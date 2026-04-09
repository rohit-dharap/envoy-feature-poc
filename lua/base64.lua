local b64chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
local b64lookup = {}
for i = 1, #b64chars do
  b64lookup[b64chars:sub(i,i)] = i - 1
end

function base64_decode(data)
  data = data:gsub('[^'..b64chars..'=]', '')
  local result = {}
  local i = 1
  while i <= #data do
    local c1 = b64lookup[data:sub(i,i)] or 0
    local c2 = b64lookup[data:sub(i+1,i+1)] or 0
    local c3 = b64lookup[data:sub(i+2,i+2)] or 0
    local c4 = b64lookup[data:sub(i+3,i+3)] or 0
    local n = (c1 * 262144) + (c2 * 4096) + (c3 * 64) + c4
    table.insert(result, string.char(math.floor(n / 65536)))
    if data:sub(i+2,i+2) ~= '=' then
      table.insert(result, string.char(math.floor((n % 65536) / 256)))
    end
    if data:sub(i+3,i+3) ~= '=' then
      table.insert(result, string.char(n % 256))
    end
    i = i + 4
  end
  return table.concat(result)
end