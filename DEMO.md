# Demo Guide

This is a step-by-step script for showing the project to judges. Every command in here has
already been tested against the real system, so you can follow it exactly.

## Where things are

You'll be demoing the version running on Azure (not your own laptop), so these are the two links
you need:

- **Dashboard (what you show on screen):** http://bup-app-16491.centralindia.azurecontainer.io:8080
- **Backend (what the commands below talk to):** http://bup-backend-16491.centralindia.azurecontainer.io:8000

Before running any command below, set this once in your terminal:

```bash
export B=http://bup-backend-16491.centralindia.azurecontainer.io:8000
```

Every command from here on starts with `curl ... "$B/..."` — that `$B` is just shorthand for the
line above, so you don't have to type the full Azure address every time.

## Step 0: Get the world ready (do this 2 minutes before the judges arrive)

Run these four commands in order:

```bash
curl -s -X POST "$B/api/admin/faults/clear"
curl -s -X POST "$B/api/admin/reset"
curl -s -X POST "$B/api/admin/step?n=45"
curl -s "$B/health"
```

What each one does, in plain terms:
1. **Clear any leftover problem** — in case a fault was left switched on from earlier testing.
2. **Reset the world** — puts the simulator back to its very first moment (empty history, full
   starting fuel).
3. **Fast-forward 45 steps** — the simulated world moves forward in small time-steps called
   "ticks" (see the Ticks section below). This gets us to a point where some stations are running
   a bit low on fuel, which is what makes the demo interesting to watch.
4. **Check it's healthy** — the last command should print `"status":"healthy"`. If it doesn't,
   something's wrong — see the troubleshooting section at the bottom.

**Why step 3 matters:** the simulated world doesn't run by itself — it only moves forward when we
tell it to (or if the organizer's simulator page is put into "auto" mode). If we accidentally leave
it running, it burns through its entire fuel-delivery schedule in a few minutes and then never
gets restocked again for the rest of the day. So we keep it "paused" and only nudge it forward
when we want to, using this "step" command. This happened once by accident during development —
which is exactly why this checklist exists now.

Once this is done, open the dashboard link and make sure you're on the **Overview** tab.

## The demo script (14 things to show)

Go through these in order. Each row says what to click or type, and what it's meant to prove to
the judges.

| # | What's happening | What you do | What it shows the judges |
|---|---|---|---|
| 1 | Everything is running normally | Point at the top-right of the screen: it should say "system healthy · tick 45" | The app is talking to the real simulator live, not showing fake data |
| 2 | Tour the dashboard | Click through the 5 tabs: Overview, Allocation plan, Supply & demand, Disruptions & alerts, Decision history | The operator has a full, usable screen to work from |
| 3 | Demand suddenly spikes | Run: `curl -s -X POST "$B/api/admin/events?type=demand_spike&start_tick=45&duration_ticks=20"` | This is a real "crisis event" pushed through the simulator's own system — not something faked in our app |
| 4 | The system notices the spike | Go to **Disruptions & alerts** tab — you'll see new entries about unusual demand | The app actually detects problems, it doesn't just wait to be told |
| 5 | The system predicts a shortage | On **Overview**, find a red/orange alert card and click **"Why at risk"** | Shows the reasoning behind the prediction, not just a number |
| 6 | A fix is recommended | Same card — it says something like "Recommend 6,500L from depot-X, arrives in 0.5h" plus an "Expected impact" line | The system doesn't just flag a problem, it proposes a specific, useful fix |
| 7 | You inspect the recommendation | Click **"N other option(s) considered"** | Shows the other choices the system looked at and rejected, and why — nothing is hidden |
| 8 | You approve the shipment | Click **"Approve shipment"** — a green message appears saying the shipment was created | Proves the "send fuel" action is real and actually accepted by the simulator |
| 9 | Something breaks | Run: `curl -s -X POST "$B/api/admin/faults?type=unavailable&duration_seconds=25"` | This tells the simulator to genuinely stop responding for 25 seconds — a real outage, not a fake one |
| 10 | The app copes with the outage | The banner at the top turns into "DEGRADED MODE" — but the alerts and dashboard keep working using saved data | The app doesn't crash or go blank when its data source disappears |
| 11 | (same failure as step 9) | — | — |
| 12 | The failure is logged, not just visible on screen | Check the **Disruptions & alerts** tab for a system alert, and/or run `curl -s "$B/health"` | Proves the failure is tracked properly in the background, not just a UI trick |
| 13 | The app recovers on its own | Wait about 25 seconds (or run `curl -s -X POST "$B/api/admin/faults/clear"` to end it early), then refresh | Banner goes back to "system healthy" by itself — nobody had to restart anything |
| 14 | Everything still works after the outage | Go to the **Allocation plan** tab and show it's still making sensible, coordinated decisions | The one earlier failure didn't leave anything broken |

## Optional extras, if you have time

**Show the load test:**
```bash
python3 loadtest/decision_api.py
```
Takes about 15 seconds. Prints out how fast the system responds and how many requests it can
handle at once. (Full explanation of how this works is in `EVALUATION.md`.)

**Show the automatic deployment pipeline:**
Open `.github/workflows/deploy-azure.yml` on GitHub and mention: every time code is pushed to the
main branch, it automatically gets tested, packaged, and re-deployed to this exact Azure link —
without anyone manually running deploy commands.

## If something goes wrong during the demo

- **Dashboard looks empty, stations show 0 fuel everywhere:** the simulator was probably left
  running by accident. Just re-run the 4 commands from Step 0 — it's completely safe to run them
  again at any time.
- **A "fault" seems stuck on:** run `curl -s -X POST "$B/api/admin/faults/clear"` — safe to run
  even if nothing is actually broken.
- **Numbers look slightly off right after typing several commands quickly:** this is a known,
  harmless timing quirk (explained in `tasks/todo.md`) that fixes itself within 3 seconds — just
  wait a moment and refresh.

## Other documents, if judges ask for more detail

- `README.md` — how the whole system is built and how to run it
- `EVALUATION.md` — how we measured everything, and why we built the "smart" parts the way we did
- `SPEC.md` — the original plan and ground rules for the project
- `tasks/todo.md` — an honest list of what's done and what's still a known limitation
