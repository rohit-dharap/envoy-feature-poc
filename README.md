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

| Service | Default host | Description |
|---|---|---|
| `preprod-service` | `preprod-service:8080` | Represents a preprod environment |
| `feature-env-service` | `feature-env-service:8080` | Represents a feature/test environment |
| `service1-preprod` | `service1-preprod:8080` | Calls `service2-preprod` downstream via Envoy |
| `service2-preprod` | `service2-preprod:8080` | Downstream service called by service1 |

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

Send requests to two services using the `host` header to specify which service to reach:

```bash
# Route to service1-preprod
curl --request GET 'http://localhost:10000/health' \
  --header 'host: service1-preprod'

# Route to service2-preprod
curl --request GET 'http://localhost:10000/health' \
  --header 'host: service2-preprod'
```

Both requests should hit the preprod instances of each service.

---

### 3. Generate the routing override payload

The routing override is passed as a Base64-encoded JSON object inside `x-hs-request-id`. The JSON maps a service name to the target host you want traffic redirected to.

In this example, we override `service2-preprod` to route to an external host:

```bash
echo -n '{"service2-preprod":"origin-hs-subscription-service-1304146998.qa.hotstar-labs.com"}' | base64
```

> **Tip:** The `origin-` prefix in the target host tells the Lua filter to route via the Dynamic Forward Proxy (DFP) over HTTPS, enabling routing to arbitrary external hosts without any static cluster config.

Copy the Base64 output — you'll use it in the next step.

---

### 4. Test with the routing override

Replace `<encoded_data_from_above_step>` with the Base64 string from Step 3:

```bash
curl --request GET 'http://localhost:10000/health' \
  --header 'host: service1-preprod' \
  --header 'x-hs-request-id: 1234-1233-222::<encoded_data_from_above_step>'
```

**What happens:**
1. The request arrives at Envoy with `host: service1-preprod` → routed to `service1`.
2. `service1` makes a downstream call to `service2-preprod` via Envoy, propagating the same `x-hs-request-id` header.
3. Envoy's Lua filter decodes the payload, sees `service2-preprod` is overridden, and redirects that call to the external feature host instead of the default preprod cluster.

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
