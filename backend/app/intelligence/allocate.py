"""Coordinated allocation planner: greedy, most-urgent-first.

Every shortage is planned together against one shared budget per depot: fuel on
hand (per fuel type) and dispatch capacity left this tick (shared across fuels,
net of shipments already PENDING this tick — in-transit ones don't count, verified
against the simulator). The most urgent station claims capacity first, and each
assignment is subtracted before the next is planned, so every recommendation on
screen stays feasible alongside the ones ranked above it.

Route choice weighs urgency against arrival time: prefer a route that lands before
the projected stockout (fastest first); if none can, take the fastest anyway and
flag it as arriving late.

Greedy rather than an LP: with 4 stations x 3 fuels x 6 routes it's a handful of
decisions, and each one's reasoning stays explainable to the operator.
"""

import math

TICK_MINUTES = 15
USABLE_DEPOT_STATUSES = ("OPEN", "CONSTRAINED")


def _floor1(x: float) -> float:
    # Round down, never up: rounding up could push past a limit (e.g. 5885.46 L of
    # stock -> 5885.5) and get the shipment rejected.
    return math.floor(x * 10) / 10


def _urgency(need: dict) -> tuple:
    hours = need["hours_to_stockout"]
    return (hours if hours is not None else math.inf, -need["shortage_l"])


def plan_allocations(needs: list[dict], depots_by_id: dict, routes: list[dict], dispatch_used: dict) -> tuple[dict, dict, dict]:
    """needs: [{station_id, fuel_type, hours_to_stockout, shortage_l, headroom_l}]
    dispatch_used: {depot_id: liters already PENDING from that depot this tick}
    Returns (plan, budgets, bottlenecks):
      plan       {(station_id, fuel_type): {"recommendation": dict | None, "note": str | None, "priority": int}}
      budgets    {depot_id: {dispatch_capacity, dispatch_pending, dispatch_planned, dispatch_left,
                             stock: {fuel: {"now", "planned", "after"}}}}
      bottlenecks {depot_id: count of shortages waiting only on that depot's dispatch capacity this tick}"""
    remaining_stock = {d: dict(dep["inventory"]) for d, dep in depots_by_id.items()}
    remaining_dispatch = {d: dep["dispatch_capacity_per_tick"] - dispatch_used.get(d, 0.0) for d, dep in depots_by_id.items()}
    bottlenecks: dict[str, int] = {}

    plan = {}
    for priority, need in enumerate(sorted(needs, key=_urgency), start=1):
        station_id, fuel = need["station_id"], need["fuel_type"]
        options, blocked, capacity_blocked_depots = [], set(), set()

        for route in routes:
            if route["destination_station_id"] != station_id:
                continue
            depot_id = route["source_depot_id"]
            depot = depots_by_id.get(depot_id)
            if route["status"] != "AVAILABLE":
                blocked.add(f"{route['id']} disrupted")
                continue
            if not depot or depot["status"] not in USABLE_DEPOT_STATUSES:
                blocked.add(f"{depot_id} closed")
                continue

            stock = remaining_stock[depot_id].get(fuel, 0.0)
            dispatch = remaining_dispatch[depot_id]
            quantity = _floor1(min(need["shortage_l"], route["max_shipment"], stock, dispatch, need["headroom_l"]))
            if quantity <= 0:
                if need["headroom_l"] <= 0:
                    blocked.add("station tank full once inbound fuel arrives")
                elif stock <= 0:
                    blocked.add(f"{depot_id} out of {fuel}")
                else:
                    blocked.add(f"{depot_id} dispatch capacity for this tick is already allocated (frees up next tick)")
                    capacity_blocked_depots.add(depot_id)
                continue

            arrival_hours = route["transit_ticks"] * TICK_MINUTES / 60
            hours = need["hours_to_stockout"]
            options.append(
                {
                    "route": route,
                    "quantity": quantity,
                    "arrival_hours": arrival_hours,
                    "in_time": hours is None or arrival_hours < hours,
                }
            )

        if not options:
            plan[(station_id, fuel)] = {
                "recommendation": None,
                "note": "; ".join(sorted(blocked)) or "no route to this station",
                "priority": priority,
            }
            for depot_id in capacity_blocked_depots:
                bottlenecks[depot_id] = bottlenecks.get(depot_id, 0) + 1
            continue

        best = min(options, key=lambda o: (not o["in_time"], o["route"]["transit_ticks"], -o["quantity"]))
        route, quantity = best["route"], best["quantity"]
        depot_id = route["source_depot_id"]
        remaining_stock[depot_id][fuel] = remaining_stock[depot_id].get(fuel, 0.0) - quantity
        remaining_dispatch[depot_id] -= quantity

        alternatives = []
        for o in options:
            if o is best:
                continue
            if not o["in_time"] and best["in_time"]:
                reason = "arrives after the projected stockout"
            elif o["route"]["transit_ticks"] > route["transit_ticks"]:
                reason = "slower route"
            elif o["quantity"] < quantity:
                reason = "less fuel available this way"
            else:
                reason = "not the best option"
            alternatives.append(
                {
                    "route_id": o["route"]["id"],
                    "source_depot_id": o["route"]["source_depot_id"],
                    "quantity": o["quantity"],
                    "arrival_hours": o["arrival_hours"],
                    "arrives_before_stockout": o["in_time"],
                    "not_chosen_because": reason,
                }
            )

        plan[(station_id, fuel)] = {
            "recommendation": {
                "route_id": route["id"],
                "source_depot_id": depot_id,
                "destination_station_id": station_id,
                "fuel_type": fuel,
                "quantity": quantity,
                "transit_ticks": route["transit_ticks"],
                "arrival_hours": best["arrival_hours"],
                "arrives_before_stockout": best["in_time"],
                "alternatives": alternatives,
            },
            "note": None if best["in_time"] else "fastest available route still lands after the projected stockout",
            "priority": priority,
        }

    budgets = {}
    for depot_id, depot in depots_by_id.items():
        capacity = depot["dispatch_capacity_per_tick"]
        pending = dispatch_used.get(depot_id, 0.0)
        budgets[depot_id] = {
            "dispatch_capacity": capacity,
            "dispatch_pending": pending,
            "dispatch_planned": capacity - pending - remaining_dispatch[depot_id],
            "dispatch_left": max(0.0, remaining_dispatch[depot_id]),
            "stock": {
                fuel: {"now": now, "planned": now - remaining_stock[depot_id].get(fuel, now), "after": remaining_stock[depot_id].get(fuel, now)}
                for fuel, now in depot["inventory"].items()
            },
        }
    return plan, budgets, bottlenecks
