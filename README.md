# Fuel Supply Intelligence & Resilience Platform

BUP CSE Fest 2026 Hackathon Finals. Operator-facing decision-support platform on top of the organizer's [BUP Fuel Supply Simulator](problem/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf) — observes the simulated fuel network, predicts shortages, recommends constrained allocations, and stays usable when the simulator (or our own intelligence layer) fails.

See [`SPEC.md`](SPEC.md) for the full spec and [`tasks/plan.md`](tasks/plan.md) for the build plan.

## Architecture

```
BUP Fuel Supply Simulator (real, organizer image, /v1/* + /admin/*)
        │  REST (source of truth) + SSE (re-fetch hint)
        ▼
backend/ (FastAPI)
  simulator_client  → typed wrapper, retry+backoff on 503 FAULT_INJECTED
  state_cache       → short-TTL cache; serves last-known-good on stale/faulted reads
  intelligence/
    forecast        → exponential-smoothed demand, stockout probability
    detect          → disruption signals from live station/route/depot status
    allocate        → constrained greedy allocation recommender
    fallback        → dumb rule-based policy used only when the smart path fails
  api/
    routes_state    → /api/stations /api/depots /api/demand-history/{id} /api/events
    routes_decision → /api/predict/{id} /api/alerts /api/allocations/apply
    routes_health   → /health /metrics
    routes_admin    → passthrough to simulator /admin/* (self-test + demo control only)
        │  JSON
        ▼
frontend/ (React + Vite) — operator dashboard: inventory, alerts, allocation approval
```

## Live deployment (Azure)

Deployed as 3 separate Azure Container Instances in resource group `bup-fuel-platform-rg` (centralindia), pushed through Azure Container Registry `bupfuelacr10349`:

| Service | Public URL |
|---|---|
| **Dashboard** | http://bup-app-16491.centralindia.azurecontainer.io:8080 |
| Backend API | http://bup-backend-16491.centralindia.azurecontainer.io:8000 |
| Simulator | http://bup-sim-16491.centralindia.azurecontainer.io:8000 |

Each service is independently public (ACI container groups share one network namespace, and both the backend and simulator images listen on the same internal port 8000, so a single shared-network group would need a port remap — three separate instances was faster to stand up for a demo link). CORS on the backend is already permissive, so the frontend calls the backend's public URL directly.

The simulator is paused and pre-stepped to tick 45 so the dashboard shows populated alerts immediately. To reset or drive it: `curl -X POST http://bup-backend-16491.centralindia.azurecontainer.io:8000/api/admin/step?n=10` (same `/api/admin/*` passthrough as local).

**This bills your Azure subscription while running.** Tear down with:
```bash
az group delete --name bup-fuel-platform-rg --yes --no-wait
```

## Run it

Requires Docker + Compose.

```bash
cp .env.example .env   # optional, defaults are fine
docker compose up --build
```

| Service | URL |
|---|---|
| Operator dashboard | http://localhost:5173 |
| Backend API | http://localhost:8080 |
| Backend health | http://localhost:8080/health |
| Backend metrics (Prometheus text) | http://localhost:8080/metrics |
| Simulator API / Swagger / admin console | http://localhost:8000/docs, http://localhost:8000/admin |

### Deployment workflow

Source → Build (`docker compose build`) → Test (manual smoke test per vertical slice, see [`SPEC.md`](SPEC.md) §6) → Package (Docker images) → Deploy (`docker compose up -d`) → Health check (`curl :8080/health`, `curl :8000/v1/health`) → Running application.

### Simulator control

The simulator starts **paused** by default (see `SIMULATOR_START_MODE` in `.env.example`) — time only advances when you ask it to, which is the organizer-recommended way to get reproducible test/demo runs:

```bash
curl -X POST "http://localhost:8080/api/admin/step?n=10"   # advance 10 ticks deterministically
curl -X POST http://localhost:8080/api/admin/reset          # wipe back to baseline scenario
```

Leaving it in `running` mode is possible (`SIMULATOR_START_MODE=running`) but burns through the simulator's finite 22-arrival supply schedule in real time — fine for a passive demo, wasteful to leave running unattended during development.

## Resilience

The simulator can inject real faults (not simulated by us) via its own admin API, which our app must survive:

```bash
curl -X POST "http://localhost:8080/api/admin/faults?type=unavailable&duration_seconds=30"
# watch http://localhost:5173 show "DEGRADED MODE" — /api/alerts keeps serving from
# cached station/depot/route state plus a rule-based fallback recommendation instead
# of the forecasting path, and /health's decision_layer component flips to degraded.
curl -X POST http://localhost:8080/api/admin/faults/clear
# system recovers automatically on the next successful fetch.
```

Other fault types available: `latency`, `error_rate`, `stale_data`, `stream_disconnect` (see the integration guide §7.10).

## Observability

- `GET /health` — per-component status: `fuel_simulator` (via `/v1/health`, which bypasses fault injection by design — it's the liveness probe), `backend_api`, `decision_layer` (ours — reflects whether we're serving live or fallback data, which `/v1/health` alone cannot tell you).
- `GET /metrics` — Prometheus text format: `allocations_applied_total`, `allocations_rejected_total`, `alerts_active`, `integration_failures_total`.
- Structured JSON logs to stdout (`docker compose logs backend`) for `allocation.applied`, `allocation.rejected`, `integration_failure`, `recovery`.

## Load testing

`python3 loadtest/decision_api.py` — hammers `GET /api/alerts`, the decision API that runs the full forecast → detect → allocate path per station×fuel on every call (the realistic worst case).

**Finding, not just a benchmark:** the first run, at 20 concurrent requests, saturated the *simulator's own* SQLAlchemy connection pool (5 + 10 overflow = 15 max) and required restarting the simulator container to recover — each `/api/alerts` call was making 12 sequential simulator calls, so 20 concurrent requests alone meant ~20 simultaneous simulator connections, already over the ceiling. Two fixes:

1. **Parallelized** the 12 per-request simulator calls (`asyncio.gather` instead of a sequential loop) — cut single-request latency from ~2.3s to ~0.6s.
2. **Added a semaphore** (`_SIMULATOR_CONCURRENCY_LIMIT = asyncio.Semaphore(10)`, [`simulator_client.py`](backend/app/simulator_client.py)) capping our *total* concurrent outbound requests to the simulator regardless of caller concurrency — a bulkhead so we can never be the one to trigger that saturation again, no matter how many operators poll the dashboard at once.

Final measured numbers (concurrency 8, 15s, post-fix, 0 errors, simulator stayed healthy throughout):

| Metric | Value |
|---|---|
| Throughput | 3.5 req/s |
| Avg latency | 2419 ms |
| p50 | 1959 ms |
| p95 | 4361 ms |
| p99 | 5175 ms |
| Error rate | 0% |
| Resource usage | backend ~0.3% CPU / 105–130 MiB RAM; simulator ~1–2% CPU / 65–80 MiB RAM (`docker stats`) |

Latency under concurrency is still dominated by the semaphore intentionally throttling us to protect the shared simulator (a single isolated request is ~0.6s) — this is the correct trade-off (bounded queuing beats cascading failure), not an unaddressed bottleneck, and is the honest headline result: **the system degrades its own throughput under load rather than taking the shared simulator down.**
