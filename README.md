# Fuel Supply Intelligence & Resilience Platform

BUP CSE Fest 2026 Hackathon Finals. Operator-facing decision-support platform on top of the organizer's [BUP Fuel Supply Simulator](problem/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf) — observes the simulated fuel network, predicts shortages, recommends constrained allocations, and stays usable when the simulator (or our own intelligence layer) fails.

See [`SPEC.md`](SPEC.md) for the full spec and [`tasks/plan.md`](tasks/plan.md) for the build plan.

## Architecture

```
BUP Fuel Supply Simulator (real, organizer image, /v1/* + /admin/*)
        │  REST (source of truth) + SSE (re-fetch hint)
        ▼
backend/ (FastAPI)
  simulator_client  → typed wrapper, retries w/ backoff on 503 FAULT_INJECTED, concurrency cap
  state_cache       → short-TTL cache; serves last-known-good on stale/faulted reads
  auth              → OPERATOR_TOKEN guard on shipments + /admin/*; reads stay open
  decision_log      → context each shipment was approved under + rejected attempts (in-memory)
  views             → regional demand, incoming supply, disruptions, system alerts, decision history
  intelligence/
    forecast        → profile-aware demand model (hour-of-day × region × live multiplier,
                      calibrated to observed demand), tick-by-tick projection incl. inbound shipments
    detect          → disruption signals from live station/route/depot status
    allocate        → coordinated planner: most-urgent-first, shared depot stock + dispatch budget,
                      returns per-depot budgets alongside the plan
    fallback        → dumb rule-based policy used only when the smart path fails
  api/
    routes_state    → /api/stations /api/depots /api/demand-history/{id} /api/events
    routes_decision → /api/dashboard (one call → plan+views) /api/predict/{id} /api/alerts /api/allocations/apply
    routes_health   → /health /metrics /api/config
    routes_admin    → passthrough to simulator /admin/* (self-test + demo control only)
        │  JSON
        ▼
frontend/ (React + Vite) — 5-tab operator dashboard (Overview, Allocation plan,
  Supply & demand, Disruptions & alerts, Decision history)

Monitoring taps every layer above without a separate pipeline: GET /health and
GET /metrics (routes_health) read state_cache + the intelligence layer directly;
logging_utils.log_event() writes structured JSON from state_cache and routes_decision
to stdout, and the same ring buffer feeds the dashboard's System alerts panel.
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

### CI/CD

[`.github/workflows/deploy-azure.yml`](.github/workflows/deploy-azure.yml) — on every push to `main`: typecheck + a backend import smoke test, then build and push both images to ACR, redeploy the backend and frontend container instances (the simulator is untouched — its state persists across app deploys), then poll both public URLs until they answer 200 (fails the run if they don't within ~2 minutes).

**One-time setup** (uses a resource-group-scoped service principal — `Contributor` on `bup-fuel-platform-rg` only, not the subscription):
```bash
gh auth login   # once, if not already
bash .azure/register-github-secrets.sh
```
This registers `AZURE_CREDENTIALS`, `ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD` as GitHub repo secrets from the local (gitignored) `.azure/` credential files — nothing is pasted or committed. `OPERATOR_TOKEN` is optional; unset, writes stay open (as the deployment is now).

The DNS labels (`bup-backend-16491`, `bup-app-16491`, `bup-sim-16491`) are hardcoded in the workflow to match the containers already running — if you ever recreate them under different labels, update the workflow's `env:` block to match.

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

## Decision intelligence

**Forecast.** The simulator's demand model is published in the integration guide (§8.5–8.6), and we checked it against a full simulated day of observed history: per 15-minute tick, demand is `daily profile liters ÷ 96 × hour-of-day factor × region demand_factor × station demand_multiplier`, plus ~10% noise. For every station × fuel we project that tick by tick across 24 hours, so a forecast made at night doesn't assume daytime demand all day. The projection includes shipments already `PENDING`/`IN_TRANSIT` to the station, and uses `/v1/events` to know when an active demand spike ends. A calibration ratio learned from the last 8h of observed demand scales the model (it sits at ~0.98–1.02 in the baseline scenario); if the organizers change a profile, the forecast corrects itself instead of staying silently wrong.

**Allocation.** Every projected shortage is planned together against one shared budget per depot: fuel on hand per fuel type, and dispatch capacity left this tick (shared across fuels, net of shipments already `PENDING` this tick — in-transit ones don't count, verified against the simulator). The most urgent station claims capacity first, and each assignment is subtracted before the next is planned, so every recommendation on screen is feasible alongside the ones ranked above it — applying them in any order gets 201s, not 409s. Route choice weighs urgency against arrival time: prefer a route that lands before the projected stockout (fastest first), otherwise take the fastest and flag it as arriving late. Alerts that get nothing this tick say why (e.g. depot dispatch budget already allocated).

## Operator dashboard

`GET /api/dashboard` returns everything the frontend renders in one call (built from a single pass over the simulator, so adding views cost no extra simulator calls):

| Tab | Shows |
|---|---|
| **Overview** | Station/depot inventory, demand trend on click, system alerts, stockout alerts with expected impact |
| **Allocation plan** | Full ranked plan, expected impact before → after per shipment and for the plan as a whole, depot dispatch/stock budgets, unserved shortages with the reason, "Approve all" |
| **Supply & demand** | Regional demand (now / 24h / coverage hours / projected unmet), incoming depot deliveries, shipments in transit |
| **Disruptions & alerts** | System alerts (deduplicated), disruptions detected from live state, the crisis-event feed |
| **Decision history** | Every shipment joined with the context it was approved under (risk, expected impact, priority), plus rejected attempts |

Approving a shipment shows the result explicitly — accepted (with the shipment id and expected impact) or rejected (with the simulator's reason) — rather than silently refreshing. A rejection is recorded either way: `degraded_mode: true` only for a real outage (`FAULT_INJECTED`/`UNREACHABLE`); a business rule (e.g. `ROUTE_DISRUPTED`) is reported as itself, not conflated with a system failure — verified live for both cases.

## Security

Reads are open; writes (`POST /api/allocations/apply`, `/api/admin/*`) require `X-Operator-Token` when `OPERATOR_TOKEN` is set (unset = open, for local dev). `/api/admin/step` is capped at 200 ticks per call. `fuel_type` is validated against the 3 real enum values. Verified live: no/wrong token → 401, correct token → 200, `step?n=99999` → 422.

**Not yet done:** the public Azure deployment doesn't have `OPERATOR_TOKEN` set — see `tasks/todo.md`.

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
- `GET /metrics` — Prometheus text format, all 3 layers from Section 14:
  - **Application:** `http_requests_total` (+ per-status), `http_errors_total`, `http_request_duration_seconds_avg`/`_count`
  - **System:** `process_cpu_seconds_total`, `process_max_rss_kb` (stdlib `resource`, no new dependency)
  - **Intelligence:** `allocations_applied_total`, `allocations_rejected_total`, `alerts_active`, `integration_failures_total`
- Structured JSON logs to stdout (`docker compose logs backend`) for `allocation.applied`, `allocation.rejected`, `integration_failure`, `recovery`.

## Load testing

`python3 loadtest/decision_api.py` — hammers `GET /api/alerts`, the decision API that runs the full forecast → detect → plan path for every station×fuel on every call (the realistic worst case).

**Finding, not just a benchmark:** the first run, at 20 concurrent requests, saturated the *simulator's own* SQLAlchemy connection pool (5 + 10 overflow = 15 max) and required restarting the simulator container to recover — each `/api/alerts` call was making 12 sequential simulator calls, so 20 concurrent requests alone meant ~20 simultaneous simulator connections, already over the ceiling. Fixes:

1. **Parallelized** the per-request simulator calls (`asyncio.gather` instead of a sequential loop).
2. **Added a semaphore** (`_SIMULATOR_CONCURRENCY_LIMIT = asyncio.Semaphore(10)`, [`simulator_client.py`](backend/app/simulator_client.py)) capping our *total* concurrent outbound requests to the simulator regardless of caller concurrency — a bulkhead so we can never be the one to trigger that saturation again, no matter how many operators poll the dashboard at once.
3. **Fewer calls per request.** The profile-aware forecast fetches demand history once per station (4 calls) instead of once per station×fuel (12).

Measured numbers (concurrency 8, 15s, 0 errors, simulator stayed healthy throughout):

| Metric | First fixed version | Current |
|---|---|---|
| Throughput | 3.5 req/s | 6.6 req/s |
| Avg latency | 2419 ms | 1242 ms |
| p50 | 1959 ms | 1099 ms |
| p95 | 4361 ms | 2329 ms |
| p99 | 5175 ms | 3817 ms |
| Single isolated request | ~0.6 s | ~0.44 s |
| Error rate | 0% | 0% |

Resource usage stays small: backend ~0.3% CPU / 105–130 MiB RAM, simulator ~1–2% CPU / 65–80 MiB RAM (`docker stats`).

Latency under concurrency is dominated by the semaphore intentionally throttling us to protect the shared simulator — the correct trade-off (bounded queuing beats cascading failure), and the honest headline result: **the system degrades its own throughput under load rather than taking the shared simulator down.**
