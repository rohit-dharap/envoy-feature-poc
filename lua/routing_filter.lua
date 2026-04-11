dofile("/etc/envoy/lua/base64.lua")
dofile("/etc/envoy/lua/json_utils.lua")

-- maps full hostname → static cluster (POC-specific, mirrors Docker service aliases)
local cluster_map = {
  ["origin-service1.preprod.hotstar-labs.com"]    = "service1_cluster",
  ["origin-service2.preprod.hotstar-labs.com"]    = "service2_preprod_cluster",
  ["service3.internal.preprod.hotstar.com"]       = "service3_internal_cluster",
}

function envoy_on_request(request_handle)
  local authority = request_handle:headers():get(":authority") or ""
  local host, port = authority:match("^(.+):(%d+)$")
  if not host then host = authority end

  -- set default cluster for this hop (POC-specific, K8s uses route config)
  local default_cluster = cluster_map[host] or "service1_cluster"
  request_handle:headers():add("x-feature-target-cluster", default_cluster)

  local header_val = request_handle:headers():get("x-hs-request-id")
  if not header_val then return end

  local _, encoded = header_val:match("^(.-)::(.+)$")
  if not encoded then return end

  local ok, decoded = pcall(base64_decode, encoded)
  if not ok or not decoded then
    request_handle:logInfo("[FEATURE-ROUTING] decode failed, routing to default")
    return
  end

  -- JSON key = full current hostname, value = full target hostname
  local target = extract_json_value(decoded, host)
  if not target then return end

  local new_authority = port and (target .. ":" .. port) or target
  request_handle:logInfo("[FEATURE-ROUTING] " .. host .. " -> " .. new_authority)
  request_handle:headers():replace(":authority", new_authority)

  -- POC-specific: pick the right upstream cluster for the new host
  if cluster_map[target] then
    request_handle:headers():replace("x-feature-target-cluster", cluster_map[target])
  elseif target:sub(1, 7) == "origin-" then
    request_handle:headers():replace("x-feature-target-cluster", "dynamic_forward_proxy_cluster_https")
  else
    request_handle:headers():replace("x-feature-target-cluster", "dynamic_forward_proxy_cluster_http")
  end
end
