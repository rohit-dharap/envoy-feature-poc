dofile("/etc/envoy/lua/base64.lua")
dofile("/etc/envoy/lua/json_utils.lua")

-- constants
local PREPROD_SERVICE_KEY = "preprod-service"
local LOCAL_FEATURE_ENV   = "feature-env-service"
local ORIGIN_PREFIX       = "origin-"

-- determine which cluster and authority to use for a given target
local function resolve_routing(target)
  if target == LOCAL_FEATURE_ENV then
    return "feature_env_cluster", nil
  end
  if target:sub(1, #ORIGIN_PREFIX) == ORIGIN_PREFIX then
    return "dynamic_forward_proxy_cluster_https", target .. ":443"
  end
  return "dynamic_forward_proxy_cluster_http", target .. ":80"
end

function envoy_on_request(request_handle)
  -- default to preprod
  request_handle:headers():add("x-feature-target-cluster", "preprod_cluster")

  -- step 1: check header exists
  local header_val = request_handle:headers():get("x-hs-request-id")
  if not header_val then return end

  -- step 2: check for routing payload delimiter
  local _, encoded = header_val:match("^(.-)::(.+)$")
  if not encoded then return end

  -- step 3: decode base64 payload
  local ok, decoded = pcall(base64_decode, encoded)
  if not ok or not decoded then
    request_handle:logInfo("[FEATURE-ROUTING] decode failed, routing to preprod")
    return
  end

  -- step 4: extract target service
  local target = extract_json_value(decoded, PREPROD_SERVICE_KEY)
  if not target then return end

  -- step 5: resolve cluster and apply routing
  local cluster, authority = resolve_routing(target)
  request_handle:logInfo("[FEATURE-ROUTING] routing to: " .. cluster)
  request_handle:headers():replace("x-feature-target-cluster", cluster)
  if authority then
    request_handle:headers():replace(":authority", authority)
  end
end