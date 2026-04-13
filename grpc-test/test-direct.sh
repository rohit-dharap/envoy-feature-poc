#!/usr/bin/env bash
# test-direct.sh — Send a gRPC Check request directly to the service (bypasses local Envoy).
# Use this to verify the service is reachable before testing through Envoy routing.

set -e

TARGET="localhost:3000"
PROTO_DIR="$(cd "$(dirname "$0")/proto" && pwd)"

echo "Target (direct, bypasses Envoy) : $TARGET"
echo ""

grpcurl \
  -plaintext \
  -import-path "$PROTO_DIR" \
  -proto envoy/service/auth/v3/authorization.proto \
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
  "$TARGET" \
  envoy.service.auth.v3.Authorization/Check
