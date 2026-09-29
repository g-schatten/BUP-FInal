# Todo

- [x] 0.1 Scaffold backend/frontend/docker-compose/.env.example
- [x] 0.2 Simulator client against real `/v1/*` + `/admin/*` (simulator now a compose service, not a mock)
- [x] 1.1 Poll + cache simulator state (`/v1/depots`, `/v1/stations`), normalized `/api/stations`, invalidate on `X-Simulator-Stale`
- [x] 1.2 Ingest `/v1/demand-history?station_id=&limit=` + `/v1/events`
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
- [x] 8.1 Profile-aware forecast: hour-of-day × region × live multiplier (event-aware), calibrated to observed demand, tick-by-tick projection incl. PENDING/IN_TRANSIT inbound
- [x] 8.2 Coordinated allocation: most-urgent-first against shared depot stock + dispatch budget; urgency vs arrival time; notes on why an alert got nothing
- [x] 9.1 Forecast: stock floors at zero (no negative-inventory bug), added `unmet_over_horizon_l`; planner plans against unmet, not raw shortage
- [x] 9.2 Expected impact per recommendation (risk/stockout-hours/unmet before → after) + plan-level totals (service level, unmet avoided)
- [x] 9.3 Depot budgets in the plan response (dispatch capacity/pending/planned/left, stock now/planned/after per fuel)
- [x] 9.4 In-memory activity log (ring buffer) + decision log (context at approval time, rejected attempts)
- [x] 9.5 `GET /api/dashboard`: one call → plan + budgets + impact + regional demand + incoming supply + disruptions + system alerts + decision history
- [x] 9.6a Rejection correctly split: business 409 vs real outage (`degraded_mode` only set for FAULT_INJECTED/UNREACHABLE) — verified both paths live
- [x] 9.6b Operator token (`OPERATOR_TOKEN`) guarding `/api/admin/*` + `/api/allocations/apply`; reads stay open; `step?n` capped at 200 — verified 401/200/422 live
- [x] 9.6c `fuel_type` validated via `Literal[...]` on apply → 422 on garbage input
- [x] 9.6d Real backoff between retries (0.2s, 0.4s) in `simulator_client`
- [x] 9.6e Fallback skips depots not OPEN/CONSTRAINED
- [x] Dashboard: 5 tabs (Overview, Allocation plan, Supply & demand, Disruptions & alerts, Decision history) — disruptions, regional demand, incoming supply, system alerts and decision history are all now visible, not just alerts
- [x] Dashboard: apply results shown explicitly (success with shipment id + impact, or rejection reason) instead of silently refreshing
- [x] Fixed while building: parallelized the 4 read-state cache fetches too — during a fault, retry+backoff on 4 sequential reads was adding ~3s to every response
- [x] Dark mode: CSS vars (`index.css`, light default + `prefers-color-scheme: dark`), `colors` object in `ui.tsx` now refs `var(--x)` — every component themed for free
- [x] Intelligence gap: bottleneck detection (`allocate.py` returns `bottlenecks`, surfaced as a system alert) — verified live (2 depots, 3-5 shortages each)
- [x] Intelligence gap: transport delay prediction (`views.transport_delays`, per-route avg delay + on-time rate from arrived shipments) — verified live; this simulator has no transit randomness for player shipments, so delay stays 0 absent a mid-transit route disruption
- [x] Intelligence gap: abnormal inventory change detection (`detect.inventory_anomalies`, actual vs forecast-expected drop, needs 2 polls) — verified fires on an artificial multi-tick jump, silent under normal single-tick cadence

- [x] Section 9 "important recommendations should be inspectable": added `signals` (why at risk — active spike, peak hours, calibration drift, regional factor), `confidence`/`confidence_note` (history sample size), `alternatives` (other feasible routes + why not chosen) — `forecast.py`, `allocate.py`, surfaced via `<details>` in AlertCard + PlanView. Verified live.

- [x] Observability gap: `/metrics` only had Intelligence-layer counters — added Application layer (`http_requests_total`+per-status, `http_errors_total`, `http_request_duration_seconds_avg`/`_count` via middleware) and System layer (`process_cpu_seconds_total`, `process_max_rss_kb` via stdlib `resource`, no new dep) — all 3 Section 14 layers now covered, verified live
- [x] README architecture diagram didn't show the monitoring path explicitly — added a one-line note (health/metrics/logs all read the same backend state, no separate pipeline)
- [x] `DEMO.md` — full 14-step demonstration runbook with exact commands, verified live (including fixing a wrong curl form for the event-injection step before it made it into the doc)
- [x] Deleted `naive_baseline_allocation` todo item — function no longer exists (removed when `allocate.py` became the coordinated planner); todo was stale

- [x] Depot display fixes (Overview tab): liter numbers now shown next to each fuel bar (were hover-tooltip-only before), depot status now a colored pill instead of plain text, and a new critical `system_alert` fires when a depot actually runs out of a fuel type (previously only stations had this — a depot hitting zero was invisible until a shipment failed because of it). Verified live (bars/pill) and via direct function test (the alert, since draining a real depot fully would take too long).
- [ ] Risk score can't show improvement for a station that's *already* stocked out (hours_to_stockout locks to ~0 in both the before and after projection the moment current stock is 0, since the forecast loop finds the very first tick where demand≥level, which is immediate regardless of a shipment landing a few ticks later) — the "X L saved" number is still correct, but risk%/"runs dry in" look stuck at 100%→100% even when a real, working shipment is approved. Confusing in a demo if the world has been stepped past tick ~45 and stations are already empty, not just low. Possible fix: for already-empty stations, report something like "still out for the next Xh" instead of a flat 100%.

## Known open issue
- [ ] Redesign in progress (dark, modern UI, generous spacing — user request): CSS custom-property theming and elevation tokens are in place and verified (`index.css`, `ui.tsx`), but the `.tab` nav styling isn't visually applying padding/gap despite correct className, correct CSS in the served stylesheet, and correct DOM (triple-checked via dumped DOM + fetched raw CSS) — root cause not yet found, parked mid-investigation when priorities shifted. Revisit before calling the redesign done.

## Later
- [ ] Idempotency key still generated per click, not per shown recommendation — a lost response to the *browser* followed by a manual retry can still double-ship (retries backend→simulator are already safe; this is browser→backend only). Lower priority now that in-transit fuel is counted, which shrinks/clears the alert once shipped.
- [ ] `state_cache.py`: one shared degraded flag across stations/depots/routes/regions — a success on one can clear the flag while another is still serving from cache.
- [ ] `/health`'s `decision_layer` only reads the degraded flag, doesn't force a refresh — can lag a few seconds behind `/api/dashboard`.
- [ ] Reuse one shared `httpx.AsyncClient` instead of opening a new one per call in `simulator_client.py`.
- [ ] Two-operator race: no lock around apply, so two simultaneous clicks against the same depot budget aren't serialized (the simulator's own dispatch-capacity check is still the final guard).
- [ ] Minor: a rapid burst of `/api/admin/step` immediately followed by a read can see a stale (up to 3s old) cached snapshot from `state_cache` mid-burst — self-corrects on the next request, not reachable through normal dashboard use, only found by hammering step+read back-to-back with no delay.

## Intelligence Requirement
Generative AI: skipped by user decision — forecasting/detection/coordinated allocation/bottleneck/transport-delay/inventory-anomaly already clear the "at least one meaningful capability" bar without it.

## RL vs heuristic — later, not started
Goal: RL-based allocation policy, benchmarked against current greedy planner (`allocate.py`), verdict on which wins where — response time included, not just outcome quality. If each wins in different cases, wire a hybrid that picks per-case.

Needs deciding first (new dependency — ask before picking):
- Library: `gymnasium` + `stable-baselines3` (standard, heavier) vs hand-rolled tabular/DQN in plain numpy (lighter, no new dep beyond numpy).
- Env: wrap the simulator (state = station/depot stock + demand + inbound; action = allocation choice per need; reward = unmet-demand-avoided, matches `_impact()` already in `routes_decision.py`). Training needs many episodes — run against `/admin/step` + `/admin/reset` in a tight loop, not the live dashboard sim.
- Training data/time budget: this simulator is deterministic (seed 12345) — a policy trained and tested on the same seed proves nothing; need seed variation or synthetic demand perturbation for a real train/test split.

Benchmark plan once built:
1. Same scenario (reset, fixed tick range), run heuristic planner and RL policy independently, log: unmet demand avoided, service level, decisions rejected by simulator (409s), and wall-clock time per decision (RL inference vs greedy loop) — response time matters for the live dashboard's 6s poll budget.
2. Break down by case type (single shortage / contested depot capacity / crisis event active / degraded-fallback mode) — expect heuristic to win on speed and on explainability always; RL might win on multi-step tradeoffs (e.g. sacrificing a low-priority station now to save two later) that the greedy one-tick-at-a-time planner can't see.
3. If mixed results: hybrid = greedy by default (cheap, explainable, always feasible-by-construction), call RL only for contested cases (multiple stations competing for one depot's capacity) where lookahead might help, with a timeout/fallback to greedy if RL inference is too slow or its pick fails simulator validation.

Risk: RL adds real complexity (training pipeline, model versioning, non-determinism, "why did it recommend this" gets harder to answer for judges) for a problem statement that explicitly says complexity ≠ higher score and RL is optional. Revisit only if there's spare time after everything else is solid.

### Prep step, do this first, no RL infra needed
Offline constraint-ablation script: drive `/admin/reset` + `/admin/step` in a loop, replay the same scenario with variants of the current heuristic (coordination on/off, calibration on/off, in-transit counting on/off, sweep `LOW_INVENTORY_RATIO` / `CALIBRATION_ALPHA` / `BOTTLENECK_MIN_STATIONS`), score each with the `_impact()` metric already computed live (unmet avoided, service level) + wall-clock per decision. Tunes the existing greedy planner's constants with evidence instead of guesswork — zero runtime cost, no new dependency, no model. Do this before touching RL; may close most of the gap RL would've been reached for.
