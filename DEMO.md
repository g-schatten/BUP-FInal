# Demonstration Workflow

A runbook for the live/judge-supervised demo (problem statement §22's 14-step story, §23
evaluation criteria). Follow top to bottom; every command has been run against the real
simulator and produces the stated result.

Pick **one** target before starting:
- **Local:** `docker compose up --build` — dashboard http://localhost:5173, backend http://localhost:8080
- **Azure:** dashboard http://bup-app-16491.centralindia.azurecontainer.io:8080, backend
  http://bup-backend-16491.centralindia.azurecontainer.io:8000

Set `B` to the backend URL for the commands below (`export B=http://localhost:8080` locally).

## Pre-demo checklist (do this 2 minutes before judges arrive)

```bash
curl -s -X POST "$B/api/admin/faults/clear"   # clear any leftover fault
curl -s -X POST "$B/api/admin/reset"          # wipe to a clean, deterministic tick 0
curl -s -X POST "$B/api/admin/step?n=45"      # advance to a populated, interesting state
curl -s "$B/health"                           # confirm: status "healthy", decision_layer.reason null
```

Why tick 45, not tick 0 or "leave it running": the simulator's supply schedule is
finite (22 deliveries total) and defaults to real-time ticking if left in `RUNNING`
mode — leaving it running for even a few minutes of small talk drains the world
permanently (this happened once on the Azure deployment mid-project; see `tasks/todo.md`).
Tick 45 gives populated stockout alerts without wasting the schedule. The simulator
stays `PAUSED` between steps below — nothing moves in the background while you talk.

Open the dashboard, land on **Overview**.

## The 14 steps

| # | Story beat | What to do | What it proves |
|---|---|---|---|
| 1 | Normal operations | Point at the header: `system healthy · tick 45` | Live connection to the real simulator |
| 2 | Operator dashboard | Walk the 5 tabs (Overview, Allocation plan, Supply & demand, Disruptions & alerts, Decision history) | Operator Interface deliverable |
| 3 | Demand starts increasing | `curl -s -X POST "$B/api/admin/events?type=demand_spike&start_tick=45&duration_ticks=20"` | A real crisis event, not scripted UI |
| 4 | System detects risk | Switch to **Disruptions & alerts** — `anomalous_demand` entries appear | Detection capability |
| 5 | Intelligence predicts shortage | **Overview** → a Stockout alert card, click **Why at risk** | Forecasting + inspectability (§9) |
| 6 | Recommendation generated | Same card: "Recommend N L from depot-X, arrives in Yh" + Expected impact line | Decision Intelligence + expected-impact requirement |
| 7 | Operator inspects | Click **N other option(s) considered** on the recommendation | Alternatives shown, not a black box |
| 8 | Allocation is simulated | Click **Approve shipment** — notice banner shows `Shipment #N created` | Real `POST /v1/allocations`, 201 not 409 |
| 9 | Crisis event occurs | `curl -s -X POST "$B/api/admin/faults?type=unavailable&duration_seconds=25"` | Real injected fault, not simulated by us |
| 10 | System adapts | **Overview** header flips to `DEGRADED MODE (...)`; alerts keep serving from cache/fallback | Resilience: stays usable, not down |
| 11 | Dependency failure injected | (same as #9 — the fault *is* the injected failure) | — |
| 12 | Monitoring detects failure | **Disruptions & alerts** → a `bottleneck`/`integration` system alert; `curl -s "$B/health"` shows `decision_layer: degraded` | Observability catches it, not just the UI |
| 13 | Fallback/recovery activates | Wait ~25s (or `curl -s -X POST "$B/api/admin/faults/clear"`), refresh — banner returns to `system healthy`, a `recovery` alert appears | Auto-recovery, no manual restart needed |
| 14 | Operations continue | **Allocation plan** tab — plan is still coordinated correctly (depot budgets, priorities) | Nothing was left broken by the fault |

## Optional: show the load test live

```bash
python3 loadtest/decision_api.py
```
~15s, prints throughput/latency/error-rate for the real decision path. Numbers and the
connection-pool-saturation story behind them are in `README.md` → "Load testing".

## Optional: show the CI/CD pipeline

`.github/workflows/deploy-azure.yml` on GitHub Actions — push to `main` → typecheck →
build+push images → redeploy Azure containers → health-check gate. Shows the Azure tab
already deployed from the last run if asked "does this rebuild automatically".

## If something goes wrong mid-demo

- **Dashboard shows an empty/drained world:** simulator was probably left `RUNNING`.
  Run the pre-demo checklist again — it's idempotent, ~2 seconds.
- **A fault won't clear:** `curl -s -X POST "$B/api/admin/faults/clear"` is safe to call
  even if nothing is active.
- **Numbers look inconsistent right after a burst of `step` calls:** known cache-timing
  edge case (`tasks/todo.md`), self-corrects within 3 seconds — just re-fetch.

## Reference docs

- `README.md` — architecture, run instructions, resilience, load testing
- `EVALUATION.md` — how every metric was measured + intelligence capability rationale, with
  the exact formulas/pseudocode
- `SPEC.md` — objective, code style, boundaries
- `tasks/plan.md` / `tasks/todo.md` — build history and known follow-ups
