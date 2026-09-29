# SPEC — Fuel Supply Intelligence & Resilience Platform

BUP CSE Fest 2026 Hackathon Finals. Judged 20/20/15/15/10/10/10 across Working Product, Intelligence, Architecture, DevOps, Resilience, Observability, Demo.

## 1. Objective

Operator-facing decision-support app on top of the organizer's Fuel Supply Simulator. Must: observe network state, detect/predict shortages, recommend constrained allocations with explanation, demonstrate resilience to ≥1 injected failure, stay observable, and deploy with one command.

## 2. Commands

- Dev backend (simulator already on :8000 via compose): `cd backend && SIMULATOR_BASE_URL=http://localhost:8000 uvicorn app.main:app --reload --port 8080`
- Dev frontend: `cd frontend && npm run dev`
- Full stack (simulator + backend + frontend): `docker compose up --build`
- Simulator alone: `docker compose up simulator-api -d` — admin console at `:8000/admin`, Swagger at `:8000/docs`
- Load test: `k6 run loadtest/decision_api.js` (tool choice confirmed in Phase 6)

## 3. Simulator contract (source: problem/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf)

Real, runnable simulator — `asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, added as a `docker-compose` service (not a hand-rolled mock). World is fixed and deterministic: 2 regions, 2 depots, 4 stations, 6 routes, fuel types `DIESEL`/`PETROL`/`OCTANE`.

- **REST is source of truth**, SSE (`/v1/stream`) is only a re-fetch hint — no `Last-Event-ID` replay on reconnect.
- **`/v1/health` and `/admin/*` bypass fault injection** — use `/v1/health` as the liveness probe, never a data endpoint.
- Every other `/v1/*` GET can 503 `FAULT_INJECTED`, or return `X-Simulator-Stale: true` header — the cache layer (Phase 1) must invalidate on that header.
- `POST /v1/allocations` is the **only** domain write, requires `idempotency_key` (permanently consumed, even by cancel) + `source_depot_id` + `destination_station_id` + `route_id` + `fuel_type` + `quantity`. Same key + same body replays safely (still 201). 9 documented error codes (404/409/422/503) — see the PDF's status-code cheat sheet for exact handling per code.
- `/admin/*` (run/pause/step/reset, inject events/faults, audit log) bypasses faults — used for self-testing and to drive the resilience demo deterministically (Phase 4 triggers real faults via `POST /admin/faults`, not a simulated one).

## 4. Project structure

```
backend/
  app/
    main.py
    simulator_client.py       # wraps /v1/* (health/instance/regions/depots/stations/routes/supply-arrivals/events/demand-history/metrics/allocations) + /admin/*
    state_cache.py            # short-TTL cache, degraded-mode fallback
    auth.py                   # OPERATOR_TOKEN guard
    decision_log.py           # approval context + rejected attempts (in-memory)
    logging_utils.py          # structured logs + in-memory activity ring buffer
    metrics.py                # Prometheus text counters
    views.py                  # regional demand / incoming supply / disruptions / system alerts / history
    intelligence/
      forecast.py             # profile-aware demand model, tick-by-tick projection, calibration
      detect.py               # anomaly / disruption detection -> alerts
      allocate.py             # coordinated allocation planner + depot budgets
      fallback.py             # rule-based policy used only when the smart path fails
    api/
      routes_state.py         # cached passthrough of simulator state
      routes_decision.py      # /dashboard /predict /alerts /allocations/apply
      routes_health.py        # /health /metrics /api/config
      routes_admin.py         # passthrough to simulator /admin/*
    models.py                 # pydantic schemas
  Dockerfile
frontend/
  src/pages/Dashboard.tsx     # tab shell: header, notices, operator token, polling
  src/views/                  # NetworkView, PlanView, SupplyDemandView, DisruptionsView, HistoryView
  src/components/             # AlertCard, Sparkline, ui.tsx (shared styles/formatters)
  Dockerfile
docker-compose.yml
tasks/plan.md
tasks/todo.md
problem/                      # read-only, given
```

## 5. Code style

Python: type hints, pydantic at API boundaries, no premature abstraction (caveman/ponytail mode active — minimum code that works, YAGNI, mark deliberate corner-cuts with a `ponytail:` comment naming the ceiling). React: function components, no state library — `useState`/`useContext` is enough at this scope.

## 6. Testing strategy

No automated tests unless asked. Verify each vertical slice manually (curl / browser) as it lands. One load-test pass is a required deliverable (Section 17) — run once in Phase 6, not continuously.

## 7. Boundaries

**Always:** operate only against the simulator; validate every simulator response before use; keep a human-review flag on any allocation the system could auto-apply; log assumptions in README.
**Ask first:** any new dependency, using RL, calling a real LLM API (cost/key), changing the chosen stack.
**Never:** hardcode secrets, touch real fuel infrastructure, execute real purchases/dispatches, silently overwrite `tasks/plan.md` or `tasks/todo.md` if unchecked work exists there.
