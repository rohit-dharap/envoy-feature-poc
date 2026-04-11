# Envoy Feature Routing — PoC

A proof-of-concept demonstrating **dynamic host replacement** via [Envoy Gateway](https://www.envoyproxy.io/). The goal is to selectively route traffic for a specific service (e.g. `feature-service`) to a test/feature environment at runtime — without any code changes or redeployments.

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

### Services in this PoC

| Service | Hostname | Type | Description |
|---|---|---|---|
| `service3-internal` | `service3.internal.preprod.hotstar.com` | Internal (HTTP) | Leaf service; represents an internal preprod endpoint |
| `feature-env-service` | `service2.internal.qa.hotstar.com` | Internal (HTTP) | Feature/QA override target for service2 |
| `service1` | `origin-service1.preprod.hotstar-labs.com` | Origin (HTTPS-style) | Entry point; calls service2 downstream via Envoy |
| `service2-preprod` | `origin-service2.preprod.hotstar-labs.com` | Origin (HTTPS-style) | Calls service3 downstream via Envoy; returns combined response |

**Call chain (default):**
```
service1  ──(origin)──►  service2  ──(internal)──►  service3
```

- `service1 → service2`: demonstrates routing to an **origin (HTTPS-style)** endpoint
- `service2 → service3`: demonstrates routing to an **internal (HTTP)** endpoint


---

## Prerequisites

- [Podman](https://podman.io/) with `podman-compose`
- `curl` and `base64` (available by default on macOS/Linux)

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

Both requests should hit the default instances of each service.

---

### 3. Generate the routing override payload

The routing override is passed as a Base64-encoded JSON object inside `x-hs-request-id`. The JSON maps the **current hostname** to the **target hostname** for that hop.

| JSON key (current host) | JSON value (target host) | Effect |
|---|---|---|
| `"origin-service2.preprod.hotstar-labs.com"` | `"service2.internal.qa.hotstar.com"` | Redirect service2 hop to QA feature-env (HTTP via DFP) |
| `"origin-service2.preprod.hotstar-labs.com"` | `"origin-service2.qa.hotstar-labs.com"` | Redirect service2 hop to a QA origin (HTTPS via DFP) |

Example — override service2 to the QA feature-env instance:

```bash
PAYLOAD=$(echo -n '{"origin-service2.preprod.hotstar-labs.com":"service2.internal.qa.hotstar.com"}' | base64)
echo $PAYLOAD
```

Copy the Base64 output — you'll use it in the next step.

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

## Envoy Admin Dashboard

An admin UI is available at [http://localhost:9901](http://localhost:9901). Useful for inspecting cluster health, active connections, and loaded configuration.

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
