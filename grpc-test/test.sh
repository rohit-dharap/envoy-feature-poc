#!/usr/bin/env bash
# test.sh — Send a gRPC Check request via Envoy with a feature routing override.
#
# Demo scenario:
#   Authority (default target) : origin-service2.preprod.hotstar-labs.com
#   Override target (feature env): origin-gateway-auth-service.preprod.hotstar-labs.com
#
# Envoy sees the override header, rewrites :authority to gateway-auth-service,
# and forwards the request over HTTP/2 + TLS to the real gRPC service.

set -e

ENVOY="${ENVOY:-localhost:10000}"
PROTO_DIR="$(cd "$(dirname "$0")/proto" && pwd)"

FROM="origin-service2.preprod.hotstar-labs.com"
TO="gateway-auth-service.internal.preprod.hotstar.com"

# Build base64-encoded routing override payload
PAYLOAD=$(printf '%s' "{\"$FROM\":\"$TO\"}" | base64 | tr -d '\n')
ROUTING_HEADER="1234-0000-0001::${PAYLOAD}"

echo "Envoy         : $ENVOY"
echo "Authority     : $FROM"
echo "Override      : $FROM -> $TO"
echo "x-hs-request-id: $ROUTING_HEADER"
echo ""

grpcurl \
  -plaintext \
  -import-path "$PROTO_DIR" \
  -proto envoy/service/auth/v3/authorization.proto \
  -authority "$FROM" \
  -H "x-hs-request-id: $ROUTING_HEADER" \
  -d '{
    "attributes": {
      "request": {
        "http": {
          "host": "origin-gateway-dummy-service.preprod.hotstar-labs.com",
          "path": "/v1/passport",
          "method": "GET",
          "headers": {
            "x-hs-platform": "android",
            "x-hs-app":      "8861",
            "x-country-code": "in"
          }
        }
      }
    }
  }' \
  "$ENVOY" \
  envoy.service.auth.v3.Authorization/Check
