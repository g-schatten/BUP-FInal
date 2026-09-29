# Todo

- [x] 0.1 Scaffold backend/frontend/docker-compose/.env.example
- [x] 0.2 Simulator client against real `/v1/*` + `/admin/*` (simulator now a compose service, not a mock)
- [x] 1.1 Poll + cache simulator state (`/v1/depots`, `/v1/stations`), normalized `/api/stations`, invalidate on `X-Simulator-Stale`
- [x] 1.2 Ingest `/v1/demand-history?station_id=&limit=` + `/v1/events`
- [ ] 1.3 (stretch) Consume `/v1/stream` SSE to shorten poll delay
- [x] (added) `/api/admin/*` passthrough (run/pause/step/reset/events/faults/audit) for deterministic dev + demo control
- [x] 2.1 Demand forecast + stockout probability + hours-to-stockout
- [x] 2.2 Anomaly/disruption detection → alerts
- [x] 2.3 Allocation recommender (respect max_shipment/dispatch_capacity/station capacity) + POST /v1/allocations wiring w/ idempotency_key
- [x] 3.1 Dashboard: inventory table + trend chart
- [x] 3.2 Alerts panel + recommendation card + approve/simulate action
- [x] 4.1 Fallback allocation policy + degraded-mode banner
- [x] 4.2 Handle real `POST /admin/faults` injection (unavailable/error_rate/latency) — retry, cache, recover
- [x] 5.1 Dockerize + compose up + README deploy steps
- [x] 5.2 /health status page + structured logs + /metrics (Prometheus text)
- [x] 6.1 Load test decision/allocation path, record metrics (found + fixed a real simulator connection-pool saturation bug along the way)
- [x] 7.1 Architecture diagram (README.md, ASCII — simulator → backend data/intelligence/decision → app)
- [x] 7.2 Full demo-story rehearsal — all 14 steps confirmed against the real simulator, incl. real fault injection + recovery
