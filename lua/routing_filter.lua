local b64chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
local b64lookup = {}
for i = 1, #b64chars do
  b64lookup[b64chars:sub(i,i)] = i - 1
end

local function base64_decode(data)
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

local function extract_target(json_str, key)
  local escaped_key = key:gsub("%-", "%%-")
  local pattern = '"' .. escaped_key .. '"%s*:%s*"([^"]+)"'
  return json_str:match(pattern)
end

-- maps target service name → envoy cluster name
local cluster_map = {
  ["feature-env-service"]                                              = "feature_env_cluster",
  ["origin-sports-test-data-service.preprod.hotstar-labs.com"]        = "pp_cluster",
  ["sports-test-data-service.internal.preprod.hotstar.com"]        = "pp_cluster_internal"
}

function envoy_on_request(request_handle)
  request_handle:headers():add("x-feature-target-cluster", "preprod_cluster")

  local header_val = request_handle:headers():get("x-hs-request-id")
  if not header_val then
    request_handle:logInfo("[FEATURE-ROUTING] no x-hs-request-id, routing to preprod")
    return
  end

  local uuid, encoded = header_val:match("^(.-)::(.+)$")
  if not encoded then
    request_handle:logInfo("[FEATURE-ROUTING] plain request id, routing to preprod")
    return
  end

  local ok, decoded = pcall(base64_decode, encoded)
  if not ok or not decoded then
    request_handle:logInfo("[FEATURE-ROUTING] decode failed, routing to preprod")
    return
  end

  request_handle:logInfo("[FEATURE-ROUTING] decoded: " .. decoded)

  local target = extract_target(decoded, "preprod-service")
  request_handle:logInfo("[FEATURE-ROUTING] extracted target: " .. tostring(target))

  if target then
    local cluster = cluster_map[target]
    if cluster then
      request_handle:logInfo("[FEATURE-ROUTING] match! routing to: " .. cluster)
      request_handle:headers():replace("x-feature-target-cluster", cluster)
      request_handle:headers():replace("x-hs-request-id", uuid)
      request_handle:headers():replace(":authority", target)
    else
      request_handle:logInfo("[FEATURE-ROUTING] target not in cluster map, routing to preprod")
    end
  else
    request_handle:logInfo("[FEATURE-ROUTING] no mapping found, routing to preprod")
  end
end