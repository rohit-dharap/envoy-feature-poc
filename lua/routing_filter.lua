dofile("/etc/envoy/lua/base64.lua")
dofile("/etc/envoy/lua/json_utils.lua")

local ORIGIN_PREFIX = "origin-"

-- default cluster for each known local service
local default_cluster_map = {
  ["preprod-service"]   = "preprod_cluster",
  ["feature-env-service"] = "feature_env_cluster",
  ["service1-preprod"]  = "service1_cluster",
  ["service2-preprod"]  = "service2_preprod_cluster",
}

-- resolve which cluster and authority to use for a given target
local function resolve_routing(target)
  -- check if it's a known local Docker service first
  if default_cluster_map[target] then
    return default_cluster_map[target], nil
  end
  -- external HTTPS service (origin- prefix convention)
  if target:sub(1, #ORIGIN_PREFIX) == ORIGIN_PREFIX then
    return "dynamic_forward_proxy_cluster_https", target .. ":443"
  end
  -- internal HTTP service via DFP
  return "dynamic_forward_proxy_cluster_http", target .. ":80"
end

function envoy_on_request(request_handle)
  -- determine which service is being called at this hop
  local authority = request_handle:headers():get(":authority")
  local service_name = authority and authority:match("^([^:]+)") or ""

  -- set default cluster based on the service being called
  local default_cluster = default_cluster_map[service_name] or "service1_cluster"
  request_handle:headers():add("x-feature-target-cluster", default_cluster)

  -- check for routing payload
  local header_val = request_handle:headers():get("x-hs-request-id")
  if not header_val then return end

  local _, encoded = header_val:match("^(.-)::(.+)$")
  if not encoded then return end

  local ok, decoded = pcall(base64_decode, encoded)
  if not ok or not decoded then
    request_handle:logInfo("[FEATURE-ROUTING] decode failed, routing to default")
    return
  end

  -- look up routing override specifically for THIS service at THIS hop
  local target = extract_json_value(decoded, service_name)
  if not target then return end

  local cluster, authority_override = resolve_routing(target)
  request_handle:logInfo("[FEATURE-ROUTING] " .. service_name .. " → " .. cluster)
  request_handle:headers():replace("x-feature-target-cluster", cluster)
  if authority_override then
    request_handle:headers():replace(":authority", authority_override)
  end
end