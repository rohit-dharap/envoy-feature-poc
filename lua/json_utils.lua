function extract_json_value(json_str, key)
  local escaped_key = key:gsub("%-", "%%-")
  local pattern = '"' .. escaped_key .. '"%s*:%s*"([^"]+)"'
  return json_str:match(pattern)
end