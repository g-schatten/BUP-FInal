# Plan — Fuel Supply Intelligence & Resilience Platform

Budget: 6–7h. Vertical slices, dependency order. Stretch items (RL, LLM explanation layer, k8s, tracing, drift detection) only if all phases below finish early.

## Phase 0 — Scaffold & Simulator Contact (~20 min) — DONE, revised
- [x] 0.1 Scaffold backend/frontend skeleton, docker-compose, `.env.example`. **Accept:** `docker compose up` boots all 3 services; `GET :8080/health` → 200.
- [x] 0.2 Simulator client wrapping real `/v1/*` (health/instance/regions/depots/stations/routes/supply-arrivals/events/demand-history/metrics/allocations) + `/admin/*` (run/pause/step/reset/events/faults/audit). **Accept:** live JSON from `/v1/depots` and `/v1/stations`.
- **Revision:** the organizer's simulator is real and runnable (`asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, per `problem/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf`) — added as a compose service instead of a hand-rolled mock. Ports: simulator `:8000`, backend `:8080` (was `:8000`, moved to avoid the clash), frontend `:5173`. Health check now correctly calls `/v1/health` (bypasses faults) instead of a data endpoint.

## Phase 1 — State Ingestion (~1h)
- 1.1 Poll `/v1/depots` + `/v1/stations` on interval, cache into SQLite/in-memory. Invalidate the cache entry immediately on `X-Simulator-Stale: true` (don't just wait for next poll). **Accept:** `GET /api/stations` returns merged inventory+status.
- 1.2 Ingest `/v1/demand-history?station_id=&limit=` per station (limit clamped ≤2000) + `/v1/events` for forecasting. **Accept:** `GET /api/demand-history/{station}` returns a time series.
- 1.3 (recommended, not required) Consume `/v1/stream` SSE to trigger faster re-polls on `inventory.updated`/`allocation.status_changed` — REST stays source of truth, SSE only shortens the poll delay. Handle reconnect (no Last-Event-ID replay: full re-fetch on reconnect) and the 15s keepalive (not a disconnect).

## Phase 2 — Intelligence Layer (~1.5h) — 20% weight, required capability
- 2.1 Demand forecast (exponential smoothing) + stockout probability + hours-to-stockout. **Accept:** `GET /api/predict/{station}` returns all three.
- 2.2 Disruption/anomaly detection → alerts (station, fuel, projected stockout, current inventory, expected demand, recommended allocation, expected result — Section 9 shape). **Accept:** ≥1 populated alert under a seeded shortage.
- 2.3 Constrained allocation recommender (greedy priority rule; `scipy.optimize.linprog` if time allows), respecting `route.max_shipment` / `depot.dispatch_capacity_per_tick` / `station.capacity[fuel]` so recommendations don't just bounce off the simulator's own 409s. Wire to `POST /v1/allocations` with a generated `idempotency_key` per recommendation. **Accept:** recommendation beats a naive baseline on stockout-risk reduction, and a submitted allocation returns 201 (not a 409).
- **Checkpoint:** confirm this clears the "meaningful AI/ML/optimization" bar before touching UI.

## Phase 3 — Operator Frontend (~1h) — 20% weight
- 3.1 Dashboard: inventory table + status colors, demand/inventory trend chart.
- 3.2 Alerts panel + recommendation card with operator approve/simulate action. **Accept:** operator sees an alert, inspects the reasoning, triggers the allocation, sees inventory update.

## Phase 4 — Resilience (~45 min) — required deliverable #9
- 4.1 Fallback allocation policy when intelligence layer errors/times out or confidence is low → rule-based allocation + "degraded mode" UI banner.
- 4.2 Simulator-dependency failure handling: on `SimulatorError` with `code="FAULT_INJECTED"` (503), backoff+retry (client already retries once) then fall back to last cached state, surfaced in the UI not silent. **Accept:** trigger a *real* fault via `POST /admin/faults {"type":"unavailable","duration_seconds":30}` (or `error_rate`/`latency`), watch the app degrade visibly and self-recover once `POST /admin/faults/clear` or the duration expires — this is real fault injection from the simulator itself, not a simulated one (demo steps 11–13).

## Phase 5 — DevOps & Observability (~45 min) — 15%+10% weight
- 5.1 Dockerize cleanly, one-command compose up, document Build→Test→Package→Deploy→Health-check→Running in README.
- 5.2 `/health` status page (Section 15 table: backend API, DB, simulator, prediction, decision engine + p95 latency/error rate) + structured logs for decisions/alerts/recoveries. Prometheus metrics = stretch if time allows. **Accept:** health check reflects real dependency state, not a static OK.

## Phase 6 — Load Test & Evidence (~30 min) — required deliverable #10
- 6.1 Load-test the decision/allocation path (k6 or locust): avg/p50/p95/p99 latency, throughput, error rate, resource usage. **Accept:** numbers committed to README.

## Phase 7 — Demo Rehearsal (~30 min buffer)
- 7.1 One-page architecture diagram (simulator → backend data/intelligence → decision → app — deliverable #6).
- 7.2 Walk the 14-step suggested demo story end-to-end once; fix what breaks.

Total ≈ 6.5h incl. buffer.
