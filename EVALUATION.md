# Evaluation Methodology & Intelligence Capabilities

This document covers two things: how the metrics and parameters in this project were actually
measured (not just quoted from docs), and which "meaningful intelligent capability" bullets from
the problem statement's Section 7 this system implements, and why each one was the right tool for
this specific problem rather than a heavier alternative. Pseudocode and equations are given inline
wherever a mechanism is more than a one-line check, using the same variable names as the source.

## 1. How metrics were measured

The guiding principle throughout: verify against the **real** simulator's actual behavior first,
then build against that — never trust documentation or intuition alone when the real system was
one API call away. Several design decisions below only exist because a measurement contradicted
an assumption.

### Load testing (`loadtest/decision_api.py`)
- **What we measured:** throughput (req/s), avg/p50/p95/p99 latency, error rate, and container
  resource usage (`docker stats`) for `GET /api/alerts` — the endpoint that runs the full
  forecast → detect → plan path on every call, the realistic worst case.

  ```
  latencies = []              # one entry per completed request, milliseconds
  run N workers concurrently for duration_s seconds:
      loop:
          t0 = now()
          response = GET /api/alerts
          latencies.append(now() - t0)

  latencies.sort()
  p(k)      = latencies[floor(k * len(latencies))]     # e.g. p(0.95) = p95
  avg       = sum(latencies) / len(latencies)
  throughput = len(latencies) / duration_s
  error_rate = errors / (len(latencies) + errors)
  ```

- **Tooling choice:** a small `httpx` + `asyncio` script instead of k6/Locust. Both are new
  dependencies; `httpx` was already a backend requirement, so a ~60-line script covered the same
  ground (concurrent requests, latency percentiles) at zero install cost.
- **What it found, not just measured:** the first run (20 concurrent requests) saturated the
  *simulator's own* SQLAlchemy connection pool (5 + 10 overflow = 15 max connections) and required
  restarting the simulator container to recover. This wasn't a synthetic number — it was a real
  operational limit discovered empirically, and it drove two fixes: parallelizing the per-request
  simulator calls, and a `Semaphore(10)` bulkhead in `simulator_client.py` capping our total
  concurrent outbound requests regardless of caller concurrency. Before/after numbers are in
  `README.md` under "Load testing".

### Demand model calibration (`forecast.py`)
- **What we measured:** for every station × fuel, the ratio of observed `demand_liters` (from
  `/v1/demand-history`) to what the integration guide's published formula predicted for that same
  tick and hour, across a full simulated day.
- **The published demand model**, as encoded in `DAILY_LITERS` and `_HOUR_FACTORS` (values in the
  latter were the ones that matched the empirical ratios — confirmed to line up exactly, not
  guessed):

  ```
  base_rate(profile, fuel)        = DAILY_LITERS[profile][fuel] / TICKS_PER_DAY      # L / tick
  hour_factor(profile, hour)      = busy_factor   if hour falls in a busy window
                                   = off_peak_factor  otherwise
  spike_multiplier(tick, station) = product of every active demand_spike event's
                                     "multiplier" (default 1.5) whose station/region
                                     filter matches this station, else 1.0

  model_rate(tick, hour) = base_rate(profile, fuel)
                          × hour_factor(profile, hour)
                          × region_factor
                          × spike_multiplier(tick, station)
  ```

- **Runtime calibration** — an exponential moving average of the ratio between observed and
  modeled demand over the available history, clamped to a sane range so one bad row can't send it
  wild:

  ```
  calibration = None
  for each history row (oldest → newest):
      expected = model_rate(row.tick, hour_of(row.sim_time))
      if expected <= 0: skip
      ratio = row.demand_liters / expected
      calibration = ratio                                         if calibration is None
                  = ALPHA * ratio + (1 - ALPHA) * calibration      otherwise    # ALPHA = 0.3
  calibration = clamp(calibration, 0.5, 2.0)   # skip clamp, default to 1.0, if < 4 rows seen

  rate(tick, hour) = model_rate(tick, hour) × calibration
  ```

  So if the organizers change a profile mid-event, `calibration` drifts away from 1.0 and the
  forecast corrects itself instead of silently staying wrong. `confidence`/`confidence_note` in the
  API response report how many ticks of history that ratio is based on (< 4 ticks → `low`, < 8 →
  `medium`, ≥ 8 → `high`), so the operator can see when a forecast is running on thin data.

- **Tick-by-tick projection across the 24h horizon** (not a flat extrapolation of the current
  rate), including fuel already inbound and a floor at zero (unserved demand is lost, not
  back-ordered):

  ```
  level = current_inventory
  demand_total = inbound_total = unmet_total = 0
  stockout_tick = None

  for k in 1..HORIZON_TICKS:                       # HORIZON_TICKS = 96 (24h at 15 min/tick)
      tick = now_tick + k
      level += inbound_by_tick.get(tick, 0)
      inbound_total += inbound_by_tick.get(tick, 0)
      demand = rate(tick, hour_of(now_time + k * 15min))
      demand_total += demand
      if stockout_tick is None and demand > 0 and demand >= level:
          stockout_tick = (k - 1) + level / demand      # fractional tick of first stockout
      unmet_total += max(0, demand - level)             # demand that goes unserved this tick
      level = max(0, level - demand)                    # tank floors at 0, never negative

  hours_to_stockout = stockout_tick * 15 / 60   if stockout_tick is not None   else None
  ```

### Simulator constraint semantics (`allocate.py`)
- **What we measured:** whether `dispatch_capacity_per_tick` counts `PENDING` allocations only, or
  also `IN_TRANSIT` ones, by posting real allocations at the boundary:

  ```
  tick T:  POST 6,500 L (Gazipur→Tongi, DIESEL)   → 201 PENDING
           POST 6,500 L (Gazipur→Tongi, DIESEL)   → 6,500 + 6,500 = 13,500 > 12,000 → 409 REJECTED
           POST 5,000 L (Gazipur→Tongi, PETROL)   → 6,500 + 5,000 = 11,500 < 12,000 → 201 PENDING
  step one tick → both PENDING shipments become IN_TRANSIT
  tick T+1: POST 5,000 L (Gazipur→Mirpur, OCTANE) → accepted (dispatch budget refreshed;
                                                      the two now-IN_TRANSIT shipments no
                                                      longer count against it)
  ```

- **Why:** the guide states the rule in prose; we confirmed it against actual API responses so the
  planner's shared-budget bookkeeping (`dispatch_used`) matches the simulator's real enforcement,
  not our reading of the sentence.

### Decision-quality metrics (`routes_decision.py::_impact`, `views.py`)
- **What we measured, per recommendation:** stockout risk and hours-to-stockout before vs. after
  the recommended shipment is simulated as arriving, and unmet demand avoided:

  ```
  impact(before, after):
      risk_before = stockout_probability(before.hours_to_stockout)
      risk_after  = stockout_probability(after.hours_to_stockout)
      unmet_avoided_l = before.unmet_over_horizon_l - after.unmet_over_horizon_l
  ```

  where `after` re-runs the exact same 24h projection above with the candidate shipment added to
  `inbound_by_tick` at its arrival tick — i.e. the "expected impact" is a real re-simulation, not a
  guess.

- **Plan-level totals**, aggregated the same way, plus the counts a judge can check by eye:

  ```
  unmet_before   = sum(f.unmet_over_horizon_l for every station×fuel forecast)
  unmet_avoided  = sum(a.impact.unmet_avoided_l for every alert with a recommendation)
  unmet_after    = unmet_before - unmet_avoided
  demand_total   = sum(f.demand_over_horizon_l for every forecast)

  service_level_before = 1 - unmet_before / max(1, demand_total)
  service_level_after  = 1 - unmet_after  / max(1, demand_total)
  ```

- **Why these and not something else:** they map directly onto the problem statement's own
  "Success Criteria" framing (a useful application turning intelligence into measurable results) —
  every number here is something an operator or judge can independently check against the
  simulator's `/v1/metrics` (`service_level`, `unmet_demand_liters`).

### Resilience testing (real fault injection, not simulated)
- **What we measured:** using the simulator's own `POST /admin/faults` (`unavailable`,
  `error_rate`), we confirmed: alerts kept serving (`degraded_mode` flips true, cached/fallback
  data used), a rejected allocation during a real outage is tagged `degraded_mode: true` while a
  business rejection (e.g. `ROUTE_DISRUPTED`) is tagged `false`, and the system auto-recovers on
  the next successful poll after the fault clears (verified via `system_alerts`' `recovery` entry
  and `/health`'s `decision_layer` component).
- **Why real faults, not mocks:** the simulator's fault injection is deterministic and the exact
  mechanism judges will use to test resilience — testing against anything else would prove nothing
  about the actual grading path.

### Observability metrics (`/metrics`, Prometheus text format)
- **What we expose:** `allocations_applied_total`, `allocations_rejected_total`, `alerts_active`,
  `integration_failures_total`.
- **Why these four:** each answers a specific operational question ("is the system deciding
  correctly", "is it failing to ship", "how much risk is currently open", "is the simulator
  connection healthy") rather than generic request counters — chosen to match Section 14's
  "decision frequency, fallback activation" observability ask.

### New capability-specific metrics (added after re-reading Section 7's Detection list)
- **Bottleneck detection** — a depot is flagged only once it is the sole blocker for at least 2
  shortages in the same tick, so ordinary one-station queuing isn't misreported as a "bottleneck":

  ```
  for each unserved need, if its only blocking reason at every candidate route was
  "depot X's dispatch capacity already committed this tick":
      bottlenecks[X] += 1
  system_alerts: for each depot X, if bottlenecks[X] >= 2: raise a bottleneck alert
  ```

- **Transport delay prediction** — per-route sample size, average delay, on-time rate, computed
  from the allocation ledger:

  ```
  for each ARRIVED allocation on this route:
      expected_arrival = created_tick + route.transit_ticks
      delay_ticks       = actual_arrival_tick - expected_arrival        # 0 or negative = on time
  avg_delay_hours = mean(delay_ticks) * 15 / 60
  on_time_rate    = count(delay_ticks <= 0) / count(all samples)
  ```

  Honest finding: in this simulator, player-submitted shipments have no built-in transit
  randomness, so `avg_delay_hours` stays at 0 absent a mid-transit route disruption. Documented as
  such rather than presented as more meaningful than it is.

- **Abnormal inventory change** — flagged only above a ratio *and* an absolute floor, to avoid
  noise, and only once two polls of history exist:

  ```
  actual_drop_l   = previous_poll.inventory[fuel] - current.inventory[fuel]
  expected_drop_l = forecast.demand_now_l                     # model's 1-tick expectation
  flag if actual_drop_l >= max(200, 2.0 * max(expected_drop_l, 1))
  ```

  Verified it fires on an artificial multi-tick jump (44 ticks stepped between polls — a drop the
  1-tick model can't explain by construction) and stays silent under normal single-tick polling —
  tuned against a real false-positive case, not guessed.

## 2. Intelligence capabilities implemented

The problem statement asks for "at least one meaningful AI/ML/optimization/detection capability."
This system implements several, spanning three of the four listed categories (Prediction,
Detection, Decision Intelligence); Generative AI was considered and explicitly declined by the
user (would require an external API key and real per-call cost). No traditional ML model
(regression, neural net, etc.) is used anywhere — every capability below is deterministic math,
and that was a deliberate choice, not a gap: see "Why not ML" at the end.

### Prediction

- **Demand forecasting** (`forecast.py`) — the calibrated model and 24h tick-by-tick projection
  given in full under §1 above. Idea: projects tick-by-tick rather than extrapolating the current
  rate flat, so a forecast made at 2am correctly expects the next morning's peak instead of
  assuming quiet demand all day.

- **Shortage / stockout prediction** — `unmet_over_horizon_l` (same loop as above): liters of
  demand that would go unserved in the next 24h, accounting for stock already on hand and
  shipments already in transit. This is the number the planner actually optimizes against, not raw
  demand.

- **Stockout probability (risk score)** — a linear rescale of hours-until-stockout against the 24h
  horizon, not a fitted probability:

  ```
  risk(hours_left) = 0                                     if hours_left is None or >= 24
                    = min(1, (24 - hours_left) / 24)        otherwise
  ```

  Deliberately presented as a *risk score* — it doesn't claim statistical precision it doesn't
  have.

- **Transport delay prediction** — the empirical per-route lateness formula in §1 above, learned
  from the allocation ledger rather than assumed from the schedule.

### Detection

- **Anomalous demand** — `demand_multiplier >= 1.15` on the station's live value. Reads the
  simulator's own signal directly.

- **Abnormal inventory change** — the actual-vs-expected-drop formula in §1 above. Deliberately a
  different signal from anomalous demand: one reads the simulator's own flag, the other reasons
  about the gap between what the *model* expected and what actually happened, so it can catch a
  drop the simulator hasn't (or wouldn't) label as an event at all.

- **Regional disruption detection** — a station whose `status != OPEN`, a route whose
  `status != AVAILABLE`, or a depot whose `status != OPEN` — read directly from live state,
  independent of the simulator's own `/v1/events` feed.

- **Supply-chain bottleneck detection** — the counting rule in §1 above: identifies when a single
  depot's exhausted dispatch capacity is the shared blocker for multiple stations' shortages in the
  same tick.

### Decision Intelligence

- **Coordinated, priority-based, constrained allocation** (`allocate.py`) — greedy, most-urgent-
  first, against a shared per-depot budget that shrinks as each shipment is planned:

  ```
  sort needs by urgency:  key = (hours_to_stockout ?? +infinity, -shortage_l)
                          # soonest-to-run-dry first; larger shortage breaks a tie

  remaining_stock[depot][fuel]     = depot.inventory[fuel]              # per depot, per fuel
  remaining_dispatch[depot]        = depot.dispatch_capacity_per_tick
                                    - liters already PENDING from that depot this tick

  for need in needs (in urgency order):
      candidates = []
      for route serving need.station:
          skip if route.status != AVAILABLE or depot.status not in {OPEN, CONSTRAINED}
          qty = floor1( min(need.shortage_l,
                             route.max_shipment,
                             remaining_stock[depot][fuel],
                             remaining_dispatch[depot],
                             need.headroom_l) )               # never round up — could
                                                                # push past a hard limit
          if qty > 0:
              arrival_hours = route.transit_ticks * 15 / 60
              in_time = need.hours_to_stockout is None or arrival_hours < need.hours_to_stockout
              candidates.append({route, qty, arrival_hours, in_time})

      if candidates:
          best = min(candidates, key = (not in_time, route.transit_ticks, -qty))
                 # prefer arriving in time, then fastest, then largest
          remaining_stock[best.depot][fuel]    -= best.qty
          remaining_dispatch[best.depot]       -= best.qty
          record best as the recommendation; every other candidate becomes an
              "alternative" with a reason it wasn't picked (slower / less fuel / late)
      else:
          record why nothing could ship (route disrupted / depot closed / out of fuel /
              tank full / dispatch capacity already committed)
  ```

  Idea: this is the actual decision problem in this scenario — 2 depots serving 4 stations means
  shipments compete for the same limited capacity. Treating each alert independently (as an
  uncoordinated version would) lets two individually-valid recommendations jointly exceed a
  depot's real limit; subtracting the shared budget *before* planning the next need guarantees
  every recommendation on screen stays feasible alongside the ones ranked above it, in whatever
  order the operator approves them. Every route choice also respects the simulator's own hard
  limits before it's ever recommended, so an approved shipment is accepted (201), not bounced
  (409) — confirmed against the real boundary case in §1.

- **Inspectable recommendations** (Section 9's explicit requirement) — every recommendation
  exposes, alongside the plan above: the *signals* driving it (active spike, peak-hour demand,
  calibration drift ≥15% from 1.0, regional factor ≥1.05), a *confidence* level with the reason,
  the *expected impact* (the before/after re-simulation from §1), and the *alternatives* considered
  with why each lost (see the `candidates` list above).

- **Fallback policy** (`fallback.py`) — used only when the forecast path can't run (a real injected
  fault, verified live):

  ```
  for each station × fuel:
      if inventory / capacity >= 0.3: skip           # not low enough to act on
      route = first AVAILABLE route to this station
      depot = that route's source depot, if OPEN/CONSTRAINED and has this fuel
      recommend min(3000 L, route.max_shipment, depot.inventory[fuel])
      risk = 1 - inventory / capacity                # ratio-based, not forecast-based
  ```

  Idea: deliberately simple — no forecasting, first feasible route, fixed conservative quantity —
  because the point of this path is staying usable when the smart path can't run, not staying
  smart. This is what keeps the system usable during an outage instead of failing outright.

### Why not ML
The simulator's demand model is *published* in the integration guide, and we verified it matches
observed data exactly (see §1 above). Fitting a model to *learn* a formula that's already known
and confirmed correct would be strictly worse: slower to build, less accurate on day one (no
training data yet), and harder to explain to an operator or judge than the formula itself. The one
place real-world drift correction happens — the calibration ratio — uses an exponential moving
average, which is the right minimal tool for that job, not a trained model. Reinforcement learning
is explicitly optional in the problem statement and is tracked as a deferred `tasks/todo.md` item
(with a benchmark plan against this heuristic, including response time) rather than implemented
speculatively.
