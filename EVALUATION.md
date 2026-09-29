# Evaluation Methodology & Intelligence Capabilities

This document explains two things, in plain language first and technical detail second:

1. **How we measured things** — not just what the numbers say, but how we actually got them, and
   why we trusted the real simulator over guessing from the documentation.
2. **What "smart" features we built** — which of the problem statement's requested capabilities
   (prediction, detection, decision-making) we implemented, and why we made each one the way we
   did.

Each section starts with a short "in plain terms" explanation. The boxes with `code`-style text
underneath are the exact formulas/logic, for anyone who wants the technical detail.

## 1. How we measured things

**In plain terms:** before trusting anything the documentation said, we tested it against the
real simulator ourselves. Several decisions in this project only exist because a real test showed
something different from what we expected.

### Load testing — how fast and reliable is the system under pressure?

**In plain terms:** we wrote a small script that hammers the busiest part of our app with many
requests at once, for 15 seconds, and measures how fast it responds and how often it fails.

- **What we measured:** how many requests per second it can handle, how long a typical request
  takes (and how long the slowest ones take), and how often something fails — all against
  `GET /api/alerts`, which is the single most demanding thing our app does (it runs the full
  prediction + detection + decision-making process on every single call).

  ```
  latencies = []              # one entry per completed request, in milliseconds
  run N workers at the same time for 15 seconds:
      loop:
          start timer
          call GET /api/alerts
          record how long it took

  once time is up:
  sort the recorded times from fastest to slowest
  "p95" = the time that 95% of requests were faster than
  average = the mean of all recorded times
  throughput = total requests completed / 15 seconds
  error rate = failed requests / total requests
  ```

- **Why we built our own tiny script instead of a real load-testing tool** (like k6 or Locust):
  those tools would need installing. We already had a networking library (`httpx`) in the project,
  so a ~60-line script using what we already had did the same job for free.

- **What we found (and it wasn't just a number, it was a real bug):** the very first time we ran
  this test with 20 requests at once, the *simulator itself* choked — it has an internal limit of
  15 database connections at a time, and we exceeded it. It genuinely broke and had to be
  restarted. This wasn't something we made up to sound impressive — it really happened, and it's
  the reason two protections now exist in the code: requests are run in parallel more efficiently,
  and we now cap ourselves at 10 requests to the simulator at once, no matter how many people are
  using the dashboard. The exact before/after numbers are in `README.md` under "Load testing".

### Demand forecasting — checking the fuel-usage formula against reality

**In plain terms:** the organizers gave us a formula for how much fuel each station uses at
different times of day. Before trusting it, we compared it against real usage data from the
simulator to make sure it was actually correct — and it was, once we found the right factors.

- **What we measured:** for every station and fuel type, we compared what really happened (real
  demand numbers from the simulator) against what the formula predicted, across a full simulated
  day.

- **The formula**, once confirmed correct:

  ```
  How much fuel a station burns per time-step = its baseline daily amount
                                               × a "busy time of day" multiplier
                                               × a regional demand multiplier
                                               × a "crisis event" multiplier (like a demand spike)
  ```

- **Self-correcting over time:** on top of the formula, we keep a running average comparing what
  the formula predicts versus what's actually happening. If the organizers ever change something
  mid-event, our forecast notices the mismatch and adjusts itself automatically instead of quietly
  being wrong. We also show a "confidence" level (high / medium / low) next to every forecast, so
  the operator can tell when a prediction is based on solid data versus very little history.

  ```
  running_average = None
  for each real demand reading we have (oldest to newest):
      predicted = what the formula says for that moment
      actual_vs_predicted_ratio = real number / predicted number
      running_average = slowly blend in each new ratio (recent readings count more)
  keep running_average between 0.5x and 2x, so one weird reading can't break everything

  final_forecast = formula's answer × running_average
  ```

- **Looking ahead 24 hours, one step at a time:** rather than just multiplying the current rate by
  24 hours (which would be wrong — demand is higher in the day, lower at night), we walk forward
  one small time-step at a time, adding any fuel that's already on its way, and stopping the tank
  from ever going below zero (fuel that isn't there can't be "borrowed back" later).

  ```
  fuel_level = current stock
  for each of the next 96 time-steps (= 24 hours):
      add any fuel arriving at this exact step
      work out how much demand there is at this step
      if demand would drain the tank completely: this is the moment of the predicted stockout
      subtract demand, but never let the tank go below zero
      keep a running total of "how much demand went unmet" — this is what we plan against
  ```

### Checking the simulator's real rules — not just trusting the manual

**In plain terms:** the rulebook says a depot can only send out a limited amount of fuel per time
step. We didn't just believe that sentence — we tested it by actually sending shipments right up
to that limit and watching what got accepted or rejected.

  ```
  Step 1: send 6,500 L                                → accepted
  Step 2: send another 6,500 L (13,500 L total)        → rejected — over the 12,000 L limit
  Step 3: send 5,000 L instead (11,500 L total)        → accepted, right under the limit
  Time moves forward one step, those shipments depart
  Step 4: try another 5,000 L                          → accepted — the limit reset for the new step
  ```

  This confirmed exactly how the limit works (it only counts shipments still waiting to depart,
  not ones already on the road), so our planning code enforces the same rule the simulator does —
  not our best guess at it.

### Measuring how good our decisions actually are

**In plain terms:** for every fuel shipment we recommend, we calculate what would happen *with*
it and *without* it, and show the difference — so it's not just "trust us," it's a number you can
check.

  ```
  For one recommendation:
      risk before  = how likely is a stockout without this shipment?
      risk after   = how likely is a stockout with this shipment arriving?
      fuel saved   = how much demand would have gone unmet, that this shipment prevents?
  ```

  ```
  For the whole plan (all recommendations together):
      total demand expected in the next 24h
      total unmet demand before any shipments
      total unmet demand after all planned shipments
      "service level" = the percentage of demand that actually gets served
                       (this can be checked against the simulator's own official numbers)
  ```

### Testing resilience with a real, not fake, breakdown

**In plain terms:** the simulator has a built-in "break things on purpose" feature made for
testing exactly this. We used it for real, rather than pretending to simulate a failure ourselves.

- **What we tested:** we told the simulator to genuinely stop responding, then confirmed: the
  dashboard kept working using saved data, a clear "degraded mode" warning appeared, a failed
  shipment attempt during the real outage was correctly labeled as "the system is down" rather
  than "your request was invalid", and everything went back to normal by itself once the outage
  ended — no restart needed.
- **Why a real failure and not a pretend one:** this exact fault-injection tool is what judges
  will use to test resilience. Testing against anything else wouldn't prove our app can actually
  survive it.

### What we track continuously (`/metrics`)

**In plain terms:** we expose a small "status board" endpoint that reports numbers judges (or any
monitoring tool) can check at any time — not just when something's actively going wrong.

We track things across three levels:
- **The app itself:** how many requests came in, how many failed, how fast they were answered.
- **The computer running it:** how much processing power and memory it's using.
- **The decision-making brain:** how many shipments we've approved, how many got rejected, how
  many active risk alerts there are right now, how many times we've lost contact with the
  simulator.

### Newer detection features (added after re-checking the requirements)

**In plain terms:** we went back through the requirements a second time and added three more
specific checks that were still missing.

- **"One depot is the bottleneck"** — if a single depot's fuel-sending limit is the *only* reason
  multiple stations aren't getting fuel this round, we flag it explicitly, instead of just quietly
  skipping those stations. (We only raise this if it's blocking 2+ stations — one station simply
  waiting its turn isn't a real bottleneck.)

- **"This route tends to run late"** — we keep track of every shipment that's actually arrived,
  compare when it was supposed to arrive versus when it really did, and show an average delay and
  an "on-time rate" per route. **Honest note:** in this particular simulator, shipments we send
  never actually arrive late unless a route gets disrupted mid-transit — so right now this number
  usually reads "0 delay". We built the feature to work correctly either way, and we say so
  plainly rather than pretending it's finding something it isn't.

- **"This station's fuel dropped more than expected"** — separate from noticing an official
  "demand spike" event, we also compare how much fuel a station *actually* lost in one time-step
  against how much our forecast expected it to lose. If the real drop is much bigger (more than
  double, and at least 200 litres) than expected, we flag it — this can catch something odd even
  if the simulator hasn't officially labeled it as an event.

## 2. The "smart" features we actually built

The organizers asked for at least one genuinely useful smart capability — prediction, detection,
or decision-making. We built several, across three of the four categories they listed. We did
**not** build a Generative-AI chatbot feature (that would need an external paid API and a
decision from the user on cost — declined for now). We also did **not** use any trained machine
learning model anywhere — every "smart" feature below is a clear, explainable formula or rule, and
that was a deliberate choice explained at the end ("Why not machine learning").

### Prediction

- **Demand forecasting** — explained in full in Section 1 above. The short version: we predict
  fuel usage hour by hour rather than assuming a flat rate, so a forecast made at 2am correctly
  expects tomorrow's morning rush instead of assuming it'll stay quiet all day.

- **Shortage prediction** — how much demand would go completely unmet in the next 24 hours,
  taking into account fuel already on the way. This is the actual number our planner tries to
  minimize — not just "how much fuel is used", but "how much fuel runs out."

- **Stockout risk score** — turns "hours until empty" into a simple 0–100% risk number. We
  deliberately call this a *risk score*, not a scientific probability — it's a useful ranking
  tool, not a claim of statistical precision.

  ```
  risk = 0%                              if more than 24 hours until empty (or no risk at all)
  risk = (24 - hours left) / 24          otherwise — closer to empty = higher risk
  ```

- **Delivery delay prediction** — explained in Section 1 above: learns from real shipment history
  whether a route tends to run late, instead of just assuming the timetable is always right.

### Detection

- **Unusual demand** — flags a station whose demand has spiked, straight from the simulator's own
  signal.

- **Unexplained inventory drop** — flags a bigger-than-expected fuel drop that our own forecast
  didn't predict, which is a different (and sometimes earlier) signal than waiting for the
  simulator to officially declare an event.

- **Regional problems** — a closed station, a blocked delivery route, or a restricted depot, read
  directly from live status — not by waiting for the simulator's event feed to mention it.

- **Bottleneck detection** — explained in Section 1 above: spots when one depot is the real
  reason several stations aren't getting fuel.

### Decision-making

- **Smart, fair fuel allocation** (the core of the whole system) — when several stations need
  fuel at once, we don't just react to each one separately. We rank every shortage by urgency
  (soonest to run dry goes first), and for each one, we check what's actually available (which
  routes still work, how much fuel is left at each depot, how much that depot is still allowed to
  send out this round). Once we recommend a shipment, we subtract it from what's available before
  looking at the next station — so two "individually correct" recommendations can never
  accidentally add up to more fuel than a depot actually has. Every recommendation also always
  respects the simulator's real hard limits, so when the operator clicks "approve," it's accepted,
  not rejected.

  **Why this matters:** with only 2 depots serving 4 stations, fuel is genuinely limited and
  shared. Treating each shortage as its own separate problem (instead of planning them together)
  is exactly the kind of mistake that would let the system recommend more fuel than actually
  exists.

- **Recommendations you can inspect, not just trust** (a specific requirement from the problem
  statement) — every recommendation comes with: *why* the system thinks this station is at risk,
  *how confident* it is in that prediction and why, *what the expected result* of the shipment
  would be, and *what other options* it considered and rejected (and why). Nothing is a black box.

- **A simple backup plan for when the smart system can't run** — if a real fault means we can't
  get the data we need to forecast properly, the system doesn't just give up. It falls back to a
  much simpler rule: if a station's fuel is below 30% of capacity, recommend a fixed, safe amount
  from the nearest working route. It's deliberately dumb — the goal here isn't to still be smart,
  it's to still be *useful* when the smart path is broken.

### Why we didn't use machine learning

The fuel-demand formula is published by the organizers, and we checked it against real data and
confirmed it's accurate. Training a machine-learning model to *re-learn* a formula that's already
known and already correct would be strictly worse: slower to build, worse at the start (no
training data yet), and much harder to explain to an operator or a judge than just... the formula.
The one place things genuinely drift over time — small real-world corrections — is handled by a
simple running average, which is the right tool for that specific job, not a full trained model.
Reinforcement learning is explicitly listed as optional in the problem statement, and we've written
up a plan to properly test it against our current approach later (including checking it isn't
slower to respond) rather than adding it without evidence it's actually better.
