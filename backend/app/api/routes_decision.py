import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from app import simulator_client as sc
from app import state_cache
from app.intelligence import allocate, detect, fallback, forecast
from app import metrics
from app.logging_utils import log_event
from app.simulator_client import SimulatorError

router = APIRouter(prefix="/api")

FUEL_TYPES = ["DIESEL", "PETROL", "OCTANE"]
SHORTAGE_HORIZON_HOURS = 24.0


async def _station_or_404(station_id: str) -> dict:
    stations = await state_cache.get_stations()
    station = next((s for s in stations if s["id"] == station_id), None)
    if not station:
        raise HTTPException(404, f"unknown station_id {station_id}")
    return station


async def _predict_fuel(station_id: str, fuel_type: str) -> dict:
    history = await sc.get_demand_history(station_id=station_id, limit=50)
    hist_fuel = [h for h in history if h["fuel_type"] == fuel_type]
    demand_per_tick = forecast.smoothed_demand_per_tick(hist_fuel)
    return {"demand_per_tick_l": round(demand_per_tick, 2)}


@router.get("/predict/{station_id}")
async def predict(station_id: str):
    station = await _station_or_404(station_id)
    out = {}
    for fuel in FUEL_TYPES:
        pred = await _predict_fuel(station_id, fuel)
        inv = station["inventory"].get(fuel, 0)
        hrs = forecast.hours_to_stockout(inv, pred["demand_per_tick_l"])
        out[fuel] = {
            **pred,
            "current_inventory_l": inv,
            "hours_to_stockout": hrs,
            "stockout_probability": forecast.stockout_probability(hrs, SHORTAGE_HORIZON_HOURS),
        }
    return out


@router.get("/alerts")
async def alerts():
    stations = await state_cache.get_stations()
    depots = await state_cache.get_depots()
    routes = await state_cache.get_routes()
    depots_by_id = {d["id"]: d for d in depots}

    disruptions = detect.detect_disruptions(stations, routes, depots)
    cache_degraded, cache_reason = state_cache.is_degraded()

    try:
        # Load test found this fan-out was the latency bottleneck (~2.3s avg sequential
        # across 4 stations x 3 fuels = 12 calls). Parallelizing keeps each call's own
        # latency but runs them concurrently — 12 is still safely under the simulator's
        # 15-connection pool ceiling (see README "Load testing").
        pairs = [(station, fuel) for station in stations for fuel in FUEL_TYPES]
        preds = await asyncio.gather(*[_predict_fuel(station["id"], fuel) for station, fuel in pairs])

        out = []
        for (station, fuel), pred in zip(pairs, preds):
            inv = station["inventory"].get(fuel, 0)
            hrs = forecast.hours_to_stockout(inv, pred["demand_per_tick_l"])
            prob = forecast.stockout_probability(hrs, SHORTAGE_HORIZON_HOURS)
            if prob <= 0:
                continue
            ticks_in_horizon = SHORTAGE_HORIZON_HOURS * 60 / forecast.TICK_MINUTES
            projected_demand = pred["demand_per_tick_l"] * ticks_in_horizon
            shortage_l = max(0.0, projected_demand - inv)
            recommendation = allocate.recommend_allocation(station, depots_by_id, routes, fuel, shortage_l)
            out.append(
                {
                    "station_id": station["id"],
                    "fuel_type": fuel,
                    "projected_stockout_hours": hrs,
                    "current_inventory_l": inv,
                    "expected_demand_l": round(projected_demand, 1),
                    "stockout_probability": prob,
                    "recommended_allocation": recommendation,
                }
            )
        out.sort(key=lambda a: a["stockout_probability"], reverse=True)
        metrics.set_gauge("alerts_active", len(out))
        return {"alerts": out, "disruptions": disruptions, "degraded_mode": cache_degraded, "degraded_reason": cache_reason}
    except SimulatorError as e:
        # demand-history is uncached (Phase 1.3 stretch item, not built) — a fault mid-loop
        # lands here. Fall back to the dumb rule-based policy instead of a 500.
        fb = fallback.fallback_alerts(stations, depots_by_id, routes)
        fb.sort(key=lambda a: a["stockout_probability"], reverse=True)
        return {"alerts": fb, "disruptions": disruptions, "degraded_mode": True, "degraded_reason": f"predict: {e.code}"}


@router.post("/allocations/apply")
async def apply_allocation(station_id: str, fuel_type: str):
    """Recompute the recommendation fresh (state may have moved) and submit it."""
    station = await _station_or_404(station_id)
    depots = await state_cache.get_depots()
    routes = await state_cache.get_routes()
    depots_by_id = {d["id"]: d for d in depots}

    try:
        pred = await _predict_fuel(station_id, fuel_type)
        hrs = forecast.hours_to_stockout(station["inventory"].get(fuel_type, 0), pred["demand_per_tick_l"])
        ticks_in_horizon = SHORTAGE_HORIZON_HOURS * 60 / forecast.TICK_MINUTES
        shortage_l = max(0.0, pred["demand_per_tick_l"] * ticks_in_horizon - station["inventory"].get(fuel_type, 0))
        recommendation = allocate.recommend_allocation(station, depots_by_id, routes, fuel_type, shortage_l)
    except SimulatorError:
        # demand-history unavailable — fall back to the dumb rule-based recommendation.
        fb = next(
            (a for a in fallback.fallback_alerts([station], depots_by_id, routes) if a["fuel_type"] == fuel_type),
            None,
        )
        recommendation = fb["recommended_allocation"] if fb else None
        hrs = None

    if not recommendation:
        raise HTTPException(409, "no feasible allocation for current state")

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
        # Client already retried once with backoff (simulator_client._request). Still faulted:
        # surface it as a handled, structured failure — not a crash — so the operator can retry.
        log_event("allocation.rejected", station_id=station_id, fuel_type=fuel_type, code=e.code)
        metrics.inc("allocations_rejected_total")
        return {
            "recommendation": recommendation,
            "allocation": {"accepted": False, "reason": f"{e.code}: {e.message}", "degraded_mode": True},
            "projected_stockout_hours": hrs,
        }
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
    return {"recommendation": recommendation, "allocation": result, "projected_stockout_hours": hrs}
