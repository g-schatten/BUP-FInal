"""Operator-facing read models, built from data the planner already fetched — no extra
simulator calls. Each function backs one section of the dashboard."""

import time

from app import decision_log
from app.logging_utils import recent_events

TICK_HOURS = 0.25
FUEL_TYPES = ["DIESEL", "PETROL", "OCTANE"]
RECENT_ACTIVITY_S = 600
IMMINENT_STOCKOUT_HOURS = 6.0


def _eta_tick(allocation: dict, routes_by_id: dict) -> int:
    route = routes_by_id.get(allocation["route_id"])
    return allocation["expected_arrival_tick"] or allocation["created_tick"] + (route["transit_ticks"] if route else 0)


def regional_demand(stations: list[dict], depots: list[dict], regions: list[dict], forecasts: dict) -> list[dict]:
    rows = []
    for region in regions:
        rs = [s for s in stations if s["region_id"] == region["id"]]
        rd = [d for d in depots if d["region_id"] == region["id"]]
        for fuel in FUEL_TYPES:
            fcs = [forecasts[(s["id"], fuel)] for s in rs if (s["id"], fuel) in forecasts]
            stock = sum(s["inventory"].get(fuel, 0) for s in rs)
            demand_24h = sum(f["demand_over_horizon_l"] for f in fcs) if fcs else None
            inbound = sum(f["inbound_l"] for f in fcs) if fcs else None
            rows.append(
                {
                    "region_id": region["id"],
                    "region_name": region["name"],
                    "demand_factor": region["demand_factor"],
                    "fuel_type": fuel,
                    "demand_per_hour_now_l": sum(f["demand_now_l"] for f in fcs) / TICK_HOURS if fcs else None,
                    "demand_24h_l": demand_24h,
                    "station_stock_l": stock,
                    "inbound_l": inbound,
                    "depot_stock_l": sum(d["inventory"].get(fuel, 0) for d in rd),
                    "projected_unmet_24h_l": sum(f["unmet_over_horizon_l"] for f in fcs) if fcs else None,
                    # hours the region's stations + fuel already en route last at the average 24h rate
                    "coverage_hours": (stock + inbound) / (demand_24h / 24) if demand_24h else None,
                    "peak_demand_multiplier": max((s["demand_multiplier"] for s in rs), default=1.0),
                }
            )
    return rows


def incoming_supply(supply_arrivals: list[dict] | None, allocations: list[dict], routes_by_id: dict, now_tick: int) -> dict:
    depot_arrivals = None
    if supply_arrivals is not None:
        depot_arrivals = [
            {
                "id": a["id"],
                "depot_id": a["depot_id"],
                "fuel_type": a["fuel_type"],
                "quantity": a["quantity"],
                "planned_tick": a["planned_tick"],
                "hours_until": max(0.0, (a["planned_tick"] - now_tick) * TICK_HOURS),
                "status": a["status"],
            }
            for a in supply_arrivals
            if a["status"] != "ARRIVED"
        ]
    shipments = []
    for a in allocations:
        if a["status"] not in ("PENDING", "IN_TRANSIT"):
            continue
        eta = _eta_tick(a, routes_by_id)
        shipments.append(
            {
                "id": a["id"],
                "station_id": a["destination_station_id"],
                "fuel_type": a["fuel_type"],
                "quantity": a["quantity"],
                "source_depot_id": a["source_depot_id"],
                "route_id": a["route_id"],
                "status": a["status"],
                "eta_tick": eta,
                "hours_until": max(0.0, (eta - now_tick) * TICK_HOURS),
            }
        )
    shipments.sort(key=lambda s: s["eta_tick"])
    return {"depot_arrivals": depot_arrivals, "shipments": shipments}


def transport_delays(allocations: list[dict], routes_by_id: dict) -> list[dict]:
    """Predicted route reliability from history: mean lateness of ARRIVED shipments vs.
    the ETA at creation (created_tick + route.transit_ticks). Not the simulator's own
    per-shipment field — a route-level estimate for routes not yet used this run."""
    samples: dict[str, list[float]] = {}
    for a in allocations:
        if a["status"] != "ARRIVED" or a["actual_arrival_tick"] is None:
            continue
        route = routes_by_id.get(a["route_id"])
        if not route:
            continue
        expected = a["created_tick"] + route["transit_ticks"]
        samples.setdefault(a["route_id"], []).append(a["actual_arrival_tick"] - expected)

    out = []
    for route_id, delays in samples.items():
        route = routes_by_id[route_id]
        avg = sum(delays) / len(delays)
        out.append(
            {
                "route_id": route_id,
                "source_depot_id": route["source_depot_id"],
                "destination_station_id": route["destination_station_id"],
                "sample_size": len(delays),
                "scheduled_transit_ticks": route["transit_ticks"],
                "avg_delay_hours": round(avg * TICK_HOURS, 2),
                "on_time_rate": round(sum(1 for d in delays if d <= 0) / len(delays), 2),
            }
        )
    return sorted(out, key=lambda r: r["avg_delay_hours"], reverse=True)


def crisis_events(events: list[dict] | None, now_tick: int) -> list[dict] | None:
    if events is None:
        return None
    out = []
    for e in events:
        row = {k: e[k] for k in ("id", "type", "status", "start_tick", "end_tick")}
        row["parameters"] = e.get("parameters") or {}
        if e["status"] == "ACTIVE":
            row["ends_in_hours"] = max(0.0, (e["end_tick"] - now_tick) * TICK_HOURS)
        elif e["status"] == "SCHEDULED":
            row["starts_in_hours"] = max(0.0, (e["start_tick"] - now_tick) * TICK_HOURS)
        out.append(row)
    order = {"ACTIVE": 0, "SCHEDULED": 1, "RESOLVED": 2}
    return sorted(out, key=lambda r: (order.get(r["status"], 3), -r["id"]))


BOTTLENECK_MIN_STATIONS = 2  # a single station waiting on capacity is just next-tick queuing, not a bottleneck


def system_alerts(
    stations: list[dict],
    alerts: list[dict],
    disruptions: list[dict],
    supply_arrivals: list[dict] | None,
    allocations: list[dict],
    degraded_reason: str | None,
    bottlenecks: dict[str, int] | None = None,
    depots: list[dict] | None = None,
) -> list[dict]:
    out = []

    def add(level: str, category: str, message: str, **extra):
        out.append({"level": level, "category": category, "message": message, **extra})

    if degraded_reason:
        add("warning", "system", f"Serving degraded data: {degraded_reason}")

    for s in stations:
        for fuel in FUEL_TYPES:
            if s["status"] == "OPEN" and s["inventory"].get(fuel, 0) <= 0:
                add("critical", "stockout", f"{s['id']} is out of {fuel} now")

    for d in depots or []:
        for fuel in FUEL_TYPES:
            if d["status"] in ("OPEN", "CONSTRAINED") and d["inventory"].get(fuel, 0) <= 0:
                add("critical", "supply", f"{d['id']} has no {fuel} left to dispatch")

    for a in alerts:
        rec, hours = a["recommended_allocation"], a["projected_stockout_hours"]
        where = f"{a['station_id']} {a['fuel_type']}"
        if rec and rec.get("arrives_before_stockout") is False:
            add("critical", "stockout", f"{where} runs dry in {hours:.1f}h, before any shipment can arrive")
        elif not rec and hours is not None and hours < IMMINENT_STOCKOUT_HOURS:
            add("critical", "stockout", f"{where} runs dry in {hours:.1f}h and nothing can ship this tick: {a['allocation_note']}")

    for d in disruptions:
        if d["type"] == "station_outage":
            add("critical", "disruption", f"{d['station_id']} is closed (outage)")
        elif d["type"] == "route_disruption":
            add("warning", "disruption", f"{d['route_id']} is disrupted")
        elif d["type"] == "depot_constraint":
            add("warning", "disruption", f"{d['depot_id']} is constrained")
        elif d["type"] == "anomalous_demand":
            add("warning", "demand", f"{d['station_id']} demand is {d['demand_multiplier']:.2f}x normal")
        elif d["type"] == "abnormal_inventory_change":
            add(
                "warning",
                "inventory",
                f"{d['station_id']} {d['fuel_type']} dropped {d['actual_drop_l']:.0f}L this tick, "
                f"vs {d['expected_drop_l']:.0f}L expected from demand alone",
            )

    for depot_id, count in (bottlenecks or {}).items():
        if count >= BOTTLENECK_MIN_STATIONS:
            add("warning", "bottleneck", f"{depot_id} dispatch capacity is the bottleneck for {count} shortages this tick")

    for sa in supply_arrivals or []:
        if sa["status"] == "DELAYED":
            add("warning", "supply", f"Supply delivery {sa['id']} to {sa['depot_id']} ({sa['fuel_type']}, {sa['quantity']:.0f}L) is delayed")

    for a in allocations:
        if a["status"] == "FAILED":
            add("warning", "shipment", f"Shipment #{a['id']} to {a['destination_station_id']} failed: {a['failure_reason'] or 'unknown'}")

    # Newest first; a fault repeats the same failure on every poll, so keep one line per message.
    cutoff = time.time() - RECENT_ACTIVITY_S
    seen = set()
    for e in recent_events():
        if e["ts"] < cutoff:
            break
        if e["event"] == "integration_failure":
            level, category, message = "warning", "integration", f"Simulator {e['key']} read failed ({e['code']}) — serving cached data"
        elif e["event"] == "recovery":
            level, category, message = "info", "integration", f"Recovered from: {e['previous_reason']}"
        elif e["event"] == "allocation.rejected":
            level, category, message = "warning", "shipment", f"Shipment to {e['station_id']} {e['fuel_type']} rejected: {e['code']}"
        else:
            continue
        if message not in seen:
            seen.add(message)
            add(level, category, message, ts=e["ts"])

    rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda a: rank[a["level"]])


def decision_history(allocations: list[dict], routes_by_id: dict) -> dict:
    shipments = []
    for a in sorted(allocations, key=lambda a: a["id"], reverse=True):
        context = decision_log.context_for(a["id"])
        shipments.append(
            {
                "id": a["id"],
                "created_tick": a["created_tick"],
                "station_id": a["destination_station_id"],
                "fuel_type": a["fuel_type"],
                "quantity": a["quantity"],
                "source_depot_id": a["source_depot_id"],
                "route_id": a["route_id"],
                "status": a["status"],
                "eta_tick": _eta_tick(a, routes_by_id),
                "arrived_tick": a["actual_arrival_tick"],
                "failure_reason": a["failure_reason"],
                "origin": "dashboard" if context else "outside this dashboard session",
                "context": context,
            }
        )
    return {"shipments": shipments, "rejected": decision_log.rejected_attempts()}
