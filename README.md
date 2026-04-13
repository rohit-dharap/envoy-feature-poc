# Envoy Feature Routing — PoC

A proof-of-concept demonstrating **dynamic host replacement** via [Envoy Proxy](https://www.envoyproxy.io/). The goal is to selectively route traffic for a specific service (e.g. `feature-service`) to a test/feature environment at runtime — without any code changes or redeployments.

## How It Works

All traffic flows through an Envoy proxy. A **Lua filter** inspects the `x-hs-request-id` request header, which can carry a Base64-encoded JSON payload specifying per-service routing overrides. If no override is present, traffic follows the default cluster mapping (preprod). This routing decision is also **propagated downstream**, enabling multi-hop service calls to honour the same override.

```
Client
  │
  ▼
Envoy (port 10000)
  │  Lua filter reads x-hs-request-id header
  │  Decodes routing payload, picks target cluster
  ├─── (default) ──► preprod cluster
  └─── (override) ──► feature-env cluster  /  external host via Dynamic Forward Proxy
```

The mechanism works identically for **HTTP and gRPC** — the Lua filter operates on the `:authority` pseudo-header, which is protocol-agnostic. gRPC clusters additionally require `http2_protocol_options` on the upstream cluster and `codec_type: AUTO` on the listener.

### Why gRPC works out of the box

gRPC is built on HTTP/2. Every gRPC request carries an `:authority` pseudo-header that identifies the target host — the exact same header the Lua filter reads and rewrites. So the routing logic requires zero changes for gRPC.

The only gRPC-specific config needed is at the infrastructure level, not the routing level:

- **`codec_type: AUTO`** on the listener — lets Envoy accept both HTTP/1.1 and HTTP/2 (h2c) on the same port.
- **`http2_protocol_options`** on the upstream cluster — tells Envoy to speak h2c to that upstream instead of HTTP/1.1.

Everything else — header decoding, host rewriting, cluster selection — is identical to the HTTP path.

### Services in this PoC

| Service | Hostname | Type | Description |
|---|---|---|---|
| `service1` | `origin-service1.preprod.hotstar-labs.com` | Origin (HTTPS-style) | Entry point; calls service2 downstream via Envoy |
| `service2-preprod` | `origin-service2.preprod.hotstar-labs.com` | Origin (HTTPS-style) | Calls service3 downstream via Envoy; returns combined response |
| `service3-internal` | `service3.internal.preprod.hotstar.com` | Internal (HTTP) | Leaf service; represents an internal preprod endpoint |
| `gateway-auth-grpc-mock` | `gateway-auth-service.internal.preprod.hotstar.com` | gRPC (h2c) | Mock gRPC service implementing `envoy.service.auth.v3.Authorization/Check` |

**Default HTTP call chain:**
```
service1 ──► service2 (origin) ──► service3 (internal)
```

- `service1 → service2`: demonstrates routing to an **origin (HTTPS-style)** endpoint
- `service2 → service3`: demonstrates routing to an **internal (HTTP)** endpoint

**gRPC routing demo:** override `origin-service2` → `gateway-auth-service.internal` to show that the same mechanism works transparently for gRPC.

---

## Prerequisites

- [Podman](https://podman.io/) with `podman-compose`
- `curl` and `base64` (available by default on macOS/Linux)
- [`grpcurl`](https://github.com/fullstorydev/grpcurl) — for gRPC tests (`brew install grpcurl` on macOS)

---

## Steps to Try It Out

### 1. Start all services

```bash
podman-compose up
```

This brings up the Envoy proxy and all mock services. Envoy listens on port `10000`.

---

### 2. Verify default routing (no overrides)

Send requests using the `host` header matching the service's FQDN:

```bash
# Route to service1 — calls service2 (PP), which calls service3 (internal PP)
curl --request GET 'http://localhost:10000/health' \
  --header 'host: origin-service1.preprod.hotstar-labs.com'

# Route directly to service2 (PP) — calls service3 (internal PP)
curl --request GET 'http://localhost:10000/health' \
  --header 'host: origin-service2.preprod.hotstar-labs.com'

# Route directly to service3 (internal PP)
curl --request GET 'http://localhost:10000/health' \
  --header 'host: service3.internal.preprod.hotstar.com'
```

All requests should hit the default instances of each service.

---

### 3. Generate the routing override payload

Open the **Payload Builder UI** at [http://localhost:8888](http://localhost:8888).

The UI reads active aliases from `docker-compose.yml` and populates the **From** dropdown automatically. Pick the service you want to override, enter the target hostname in the **To** field, and click **Build payload**. It outputs the JSON, the Base64 value, and the ready-to-use `x-hs-request-id` header value — each with a copy button.

Example override — redirect the service2 hop to a QA feature-env instance:

| From | To | Effect |
|---|---|---|
| `origin-service2.preprod.hotstar-labs.com` | `service2.internal.qa.hotstar.com` | HTTP via Dynamic Forward Proxy |
| `origin-service2.preprod.hotstar-labs.com` | `origin-service2.qa.hotstar-labs.com` | HTTPS via Dynamic Forward Proxy |

Copy the generated `x-hs-request-id` value — you'll use it in the next step.

---

### 4. Test with the routing override

Replace `<encoded_data_from_above_step>` with the Base64 string from Step 3:

```bash
curl --request GET 'http://localhost:10000/health' \
  --header 'host: origin-service1.preprod.hotstar-labs.com' \
  --header 'x-hs-request-id: 1234-1233-222::<encoded_data_from_above_step>'
```

**What happens:**
1. The request arrives at Envoy with `host: origin-service1.preprod.hotstar-labs.com` → routed to `service1` (PP).
2. `service1` makes a downstream call to `origin-service2.preprod.hotstar-labs.com` via Envoy, propagating the same `x-hs-request-id` header.
3. Envoy's Lua filter decodes the payload, sees `origin-service2.preprod.hotstar-labs.com` is overridden with `service2.internal.qa.hotstar.com`, and redirects that hop to the QA feature-env instance instead.
4. The QA feature-env service responds; `service1` returns the combined response.

This demonstrates **multi-level dynamic routing**: a single header at the entry point drives routing decisions across the entire call chain.

---

### 5. Test gRPC routing

The same mechanism works for gRPC with no changes to the Lua filter or header format.

**Verify the mock directly (bypasses Envoy):**
```bash
bash grpc-test/test-direct.sh
```

**Test routing override through Envoy** — overrides `origin-service2` → `gateway-auth-service.internal`:
```bash
bash grpc-test/test.sh
```

Expected response in both cases:
```json
{
  "status": {
    "message": "OK - mock gateway-auth-service"
  }
}
```

**What makes gRPC work:**
- `codec_type: AUTO` on the Envoy listener accepts both HTTP/1.1 and HTTP/2 (h2c).
- `gateway_auth_grpc_cluster` has `http2_protocol_options` so Envoy speaks h2c to the upstream.
- The Lua filter rewrites `:authority` — the same header gRPC uses as its host identifier — so no filter changes are needed.

---

## Key Files

| File | Purpose |
|---|---|
| `envoy.yaml` | Envoy listener, route, and cluster configuration |
| `lua/routing_filter.lua` | Core routing logic — reads header, resolves target cluster |
| `lua/base64.lua` | Base64 decoder used by the Lua filter |
| `lua/json_utils.lua` | Lightweight JSON value extractor |
| `docker-compose.yml` | Service definitions for Envoy + all mock services |
| `mock-services/` | Python mock services simulating preprod and feature environments |
| `mock-services/gateway_auth_grpc_mock.py` | Mock gRPC service (grpcio, no codegen) |
| `payload-builder.py` | Web UI (port 8888) for building `x-hs-request-id` payloads |
| `grpc-test/` | grpcurl scripts and proto files for gRPC routing tests |
