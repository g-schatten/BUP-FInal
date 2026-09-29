import asyncio
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from app import decision_log, metrics, state_cache, views
from app import simulator_client as sc
from app.auth import auth_required, require_operator
from app.intelligence import allocate, detect, fallback, forecast
from app.logging_utils import log_event
from app.simulator_client import SimulatorError

router = APIRouter(prefix="/api")

FUEL_TYPES = ["DIESEL", "PETROL", "OCTANE"]
FuelType = Literal["DIESEL", "PETROL", "OCTANE"]
HISTORY_TICKS = 32  # 8h per fuel for calibration
INBOUND_STATUSES = ("PENDING", "IN_TRANSIT")
OUTAGE_CODES = ("FAULT_INJECTED", "UNREACHABLE")


async def _optional(coro):
    """Inputs that only refine the picture (history, events, supply arrivals): a fault
    degrades that part instead of dropping us to the rule-based fallback."""
    try:
        return await coro
    except SimulatorError as e:
        return e


def _impact(before: dict, after: dict) -> dict:
    return {
        "hours_to_stockout_before": before["hours_to_stockout"],
        "hours_to_stockout_after": after["hours_to_stockout"],
        "risk_before": forecast.stockout_probability(before["hours_to_stockout"]),
        "risk_after": forecast.stockout_probability(after["hours_to_stockout"]),
        "unmet_24h_before_l": round(before["unmet_over_horizon_l"], 1),
        "unmet_24h_after_l": round(after["unmet_over_horizon_l"], 1),
        "unmet_avoided_l": round(before["unmet_over_horizon_l"] - after["unmet_over_horizon_l"], 1),
    }


async def _build_state() -> dict:
    """One pass over the simulator → coordinated plan + every operator view.
    Shared by /alerts, /predict, /dashboard and /allocations/apply."""
    # In parallel: during a fault each read retries with backoff, and in series that adds up to seconds.
    stations, depots, routes, regions = await asyncio.gather(
        state_cache.get_stations(), state_cache.get_depots(), state_cache.get_routes(), state_cache.get_regions()
    )
    depots_by_id = {d["id"]: d for d in depots}
    routes_by_id = {r["id"]: r for r in routes}
    region_factor = {r["id"]: r["demand_factor"] for r in regions}
    disruptions = detect.detect_disruptions(stations, routes, depots)
    _, cache_reason = state_cache.is_degraded()

    base = {"stations": stations, "depots": depots, "regions": regions, "disruptions": disruptions}

    try:
        instance, allocations = await asyncio.gather(sc.get_instance(), sc.get_allocations())
    except SimulatorError as e:
        # Can't place "now" in time or see what's already shipped: fall back to the dumb
        # rule-based policy instead of a 500 (Section 11 "fallback allocation policy").
        fb = fallback.fallback_alerts(stations, depots_by_id, routes)
        fb.sort(key=lambda a: a["stockout_probability"], reverse=True)
        reason = f"planner: {e.code}"
        return {
            **base,
            "mode": "fallback",
            "tick": None,
            "sim_time": None,
            "alerts": fb,
            "forecasts": {},
            "budgets": {},
            "bottlenecks": {},
            "totals": None,
            "events": None,
            "supply_arrivals": None,
            "allocations": [],
            "routes_by_id": routes_by_id,
            "degraded_reason": reason,
        }

    events, supply_arrivals, *histories = await asyncio.gather(
        _optional(sc.get_events()),
        _optional(sc.get_supply_arrivals()),
        *[_optional(sc.get_demand_history(s["id"], limit=HISTORY_TICKS * len(FUEL_TYPES))) for s in stations],
    )
    partial_reasons = []
    if isinstance(events, SimulatorError):
        partial_reasons.append(f"events: {events.code}")
        events = None
    if isinstance(supply_arrivals, SimulatorError):
        partial_reasons.append(f"supply arrivals: {supply_arrivals.code}")
        supply_arrivals = None
    if any(isinstance(h, SimulatorError) for h in histories):
        partial_reasons.append("calibration history unavailable")

    now_tick = instance["tick"]
    now_time = datetime.fromisoformat(instance["sim_time"])

    inbound: dict[tuple[str, str], dict[int, float]] = {}
    dispatch_used: dict[str, float] = {}
    for a in allocations:
        if a["status"] not in INBOUND_STATUSES:
            continue
        if a["status"] == "PENDING":
            dispatch_used[a["source_depot_id"]] = dispatch_used.get(a["source_depot_id"], 0.0) + a["quantity"]
        route = routes_by_id.get(a["route_id"])
        arrival = a["expected_arrival_tick"] or (a["created_tick"] + (route["transit_ticks"] if route else 0))
        per_tick = inbound.setdefault((a["destination_station_id"], a["fuel_type"]), {})
        per_tick[max(arrival, now_tick + 1)] = per_tick.get(max(arrival, now_tick + 1), 0.0) + a["quantity"]

    forecasts, inputs, needs = {}, {}, []
    for station, history in zip(stations, histories):
        rows = None if isinstance(history, SimulatorError) else history
        for fuel in FUEL_TYPES:
            key = (station["id"], fuel)
            args = (
                station,
                fuel,
                region_factor.get(station["region_id"], 1.0),
                now_tick,
                now_time,
                [r for r in rows if r["fuel_type"] == fuel] if rows is not None else None,
                events,
            )
            inputs[key] = args
            fc = forecast.forecast(*args, inbound.get(key, {}))
            inventory = station["inventory"].get(fuel, 0)
            fc["current_inventory_l"] = inventory
            fc["stockout_probability"] = forecast.stockout_probability(fc["hours_to_stockout"])
            forecasts[key] = fc
            if fc["hours_to_stockout"] is not None:
                needs.append(
                    {
                        "station_id": station["id"],
                        "fuel_type": fuel,
                        "hours_to_stockout": fc["hours_to_stockout"],
                        # plan against the liters that would actually go unserved, not raw demand
                        "shortage_l": fc["unmet_over_horizon_l"],
                        "headroom_l": max(0.0, station["capacity"].get(fuel, 0) - inventory - sum(inbound.get(key, {}).values())),
                    }
                )

    disruptions.extend(detect.inventory_anomalies(stations, state_cache.previous("stations"), forecasts))
    plan, budgets, bottlenecks = allocate.plan_allocations(needs, depots_by_id, routes, dispatch_used)

    alerts = []
    for need in needs:
        key = (need["station_id"], need["fuel_type"])
        fc, slot = forecasts[key], plan[key]
        rec = slot["recommendation"]
        impact = None
        if rec:
            with_shipment = dict(inbound.get(key, {}))
            arrival = now_tick + rec["transit_ticks"]
            with_shipment[arrival] = with_shipment.get(arrival, 0.0) + rec["quantity"]
            impact = _impact(fc, forecast.forecast(*inputs[key], with_shipment))
        alerts.append(
            {
                "station_id": need["station_id"],
                "fuel_type": need["fuel_type"],
                "priority": slot["priority"],
                "projected_stockout_hours": fc["hours_to_stockout"],
                "current_inventory_l": fc["current_inventory_l"],
                "inbound_l": round(fc["inbound_l"], 1),
                "expected_demand_l": round(fc["demand_over_horizon_l"], 1),
                "projected_unmet_l": round(fc["unmet_over_horizon_l"], 1),
                "stockout_probability": fc["stockout_probability"],
                "signals": fc["signals"],
                "confidence": fc["confidence"],
                "confidence_note": fc["confidence_note"],
                "recommended_allocation": rec,
                "allocation_note": slot["note"],
                "impact": impact,
            }
        )
    alerts.sort(key=lambda a: a["priority"])

    unmet_before = sum(f["unmet_over_horizon_l"] for f in forecasts.values())
    avoided = sum(a["impact"]["unmet_avoided_l"] for a in alerts if a["impact"])
    at_risk_after = sum(
        1 for a in alerts if not a["impact"] or a["impact"]["hours_to_stockout_after"] is not None
    )
    totals = {
        "demand_24h_l": round(sum(f["demand_over_horizon_l"] for f in forecasts.values()), 1),
        "unmet_24h_before_l": round(unmet_before, 1),
        "unmet_24h_after_l": round(unmet_before - avoided, 1),
        "unmet_avoided_l": round(avoided, 1),
        "service_level_before": 1 - unmet_before / max(1.0, sum(f["demand_over_horizon_l"] for f in forecasts.values())),
        "service_level_after": 1 - (unmet_before - avoided) / max(1.0, sum(f["demand_over_horizon_l"] for f in forecasts.values())),
        "at_risk_before": len(alerts),
        "at_risk_after": at_risk_after,
        "shipments_planned": sum(1 for a in alerts if a["recommended_allocation"]),
        "liters_planned": round(sum(a["recommended_allocation"]["quantity"] for a in alerts if a["recommended_allocation"]), 1),
        "unserved": sum(1 for a in alerts if not a["recommended_allocation"]),
    }

    reasons = ([cache_reason] if cache_reason else []) + partial_reasons
    return {
        **base,
        "mode": "planner",
        "tick": now_tick,
        "sim_time": instance["sim_time"],
        "alerts": alerts,
        "forecasts": forecasts,
        "budgets": budgets,
        "bottlenecks": bottlenecks,
        "totals": totals,
        "events": events,
        "supply_arrivals": supply_arrivals,
        "allocations": allocations,
        "routes_by_id": routes_by_id,
        "degraded_reason": "; ".join(reasons) or None,
    }


@router.get("/alerts")
async def alerts():
    state = await _build_state()
    metrics.set_gauge("alerts_active", len(state["alerts"]))
    return {
        "alerts": state["alerts"],
        "disruptions": state["disruptions"],
        "degraded_mode": state["degraded_reason"] is not None,
        "degraded_reason": state["degraded_reason"],
    }


@router.get("/dashboard")
async def dashboard():
    """Everything the operator screen shows, from one simulator pass."""
    s = await _build_state()
    metrics.set_gauge("alerts_active", len(s["alerts"]))
    depot_names = {d["id"]: d["name"] for d in s["depots"]}
    return {
        "mode": s["mode"],
        "tick": s["tick"],
        "sim_time": s["sim_time"],
        "degraded_mode": s["degraded_reason"] is not None,
        "degraded_reason": s["degraded_reason"],
        "auth_required": auth_required(),
        "stations": s["stations"],
        "depots": s["depots"],
        "alerts": s["alerts"],
        "plan": {
            "totals": s["totals"],
            "budgets": [{"depot_id": d, "depot_name": depot_names.get(d, d), **b} for d, b in s["budgets"].items()],
        },
        "regional_demand": views.regional_demand(s["stations"], s["depots"], s["regions"], s["forecasts"]),
        "incoming": views.incoming_supply(s["supply_arrivals"], s["allocations"], s["routes_by_id"], s["tick"] or 0)
        if s["mode"] == "planner"
        else None,
        "disruptions": {"detected": s["disruptions"], "events": views.crisis_events(s["events"], s["tick"] or 0)},
        "system_alerts": views.system_alerts(
            s["stations"], s["alerts"], s["disruptions"], s["supply_arrivals"], s["allocations"], s["degraded_reason"], s["bottlenecks"], s["depots"]
        ),
        "history": views.decision_history(s["allocations"], s["routes_by_id"]) if s["mode"] == "planner" else None,
        "transport_reliability": views.transport_delays(s["allocations"], s["routes_by_id"]) if s["mode"] == "planner" else [],
    }


@router.get("/predict/{station_id}")
async def predict(station_id: str):
    state = await _build_state()
    if not state["forecasts"]:
        raise HTTPException(503, f"forecast unavailable ({state['degraded_reason']})")
    out = {fuel: fc for (sid, fuel), fc in state["forecasts"].items() if sid == station_id}
    if not out:
        raise HTTPException(404, f"unknown station_id {station_id}")
    return out


@router.post("/allocations/apply", dependencies=[Depends(require_operator)])
async def apply_allocation(station_id: str, fuel_type: FuelType):
    """Submit this station x fuel's slot in the coordinated plan, recomputed fresh (the
    world may have moved since the operator looked). Its slot already accounts for
    capacity reserved by more urgent stations, applied or not."""
    state = await _build_state()
    if not any(s["id"] == station_id for s in state["stations"]):
        raise HTTPException(404, f"unknown station_id {station_id}")
    entry = next((a for a in state["alerts"] if a["station_id"] == station_id and a["fuel_type"] == fuel_type), None)
    if not entry:
        raise HTTPException(409, "no projected shortage for this station and fuel right now")
    recommendation = entry["recommended_allocation"]
    if not recommendation:
        raise HTTPException(409, f"no feasible allocation: {entry.get('allocation_note') or 'no route available'}")

    idempotency_key = f"{station_id}-{fuel_type}-{uuid.uuid4()}"
    try:
        result = await sc.post_allocation(
            idempotency_key,
            recommendation["source_depot_id"],
            recommendation["destination_station_id"],
            recommendation["route_id"],
            fuel_type,
            recommendation["quantity"],
        )
    except SimulatorError as e:
        # Only an unreachable/faulted simulator is "degraded"; a 409 is the simulator
        # enforcing a business rule and the system itself is fine.
        outage = e.code in OUTAGE_CODES
        log_event("allocation.rejected", station_id=station_id, fuel_type=fuel_type, code=e.code, message=e.message)
        metrics.inc("allocations_rejected_total")
        decision_log.record_rejected(
            {
                "station_id": station_id,
                "fuel_type": fuel_type,
                "quantity": recommendation["quantity"],
                "source_depot_id": recommendation["source_depot_id"],
                "route_id": recommendation["route_id"],
                "code": e.code,
                "message": e.message,
                "outage": outage,
            }
        )
        return {
            "recommendation": recommendation,
            "allocation": {"accepted": False, "code": e.code, "reason": e.message, "degraded_mode": outage},
            "impact": entry.get("impact"),
        }

    state_cache.invalidate("depots", "stations")
    decision_log.record_applied(
        result["id"],
        {
            "policy": state["mode"],
            "priority": entry.get("priority"),
            "risk_at_approval": entry["stockout_probability"],
            "hours_to_stockout_at_approval": entry["projected_stockout_hours"],
            "impact": entry.get("impact"),
            "sim_tick": state["tick"],
        },
    )
    log_event(
        "allocation.applied",
        station_id=station_id,
        fuel_type=fuel_type,
        quantity=recommendation["quantity"],
        source_depot_id=recommendation["source_depot_id"],
        route_id=recommendation["route_id"],
        allocation_id=result.get("id"),
    )
    metrics.inc("allocations_applied_total")
    return {"recommendation": recommendation, "allocation": {**result, "accepted": True}, "impact": entry.get("impact")}
