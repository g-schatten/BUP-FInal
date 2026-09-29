"""Constrained allocation recommender: greedy, fastest-feasible-route heuristic.

Deliberately not an LP solver — respects every simulator-side constraint
(route.max_shipment, depot.dispatch_capacity_per_tick, station capacity
headroom, depot/route/station status) so a recommendation the operator
approves actually gets accepted (201), not bounced with a 409.
"""


def recommend_allocation(station: dict, depots_by_id: dict, routes: list[dict], fuel_type: str, shortage_l: float) -> dict | None:
    if shortage_l <= 0:
        return None
    feasible = []
    for route in routes:
        if route["destination_station_id"] != station["id"] or route["status"] != "AVAILABLE":
            continue
        depot = depots_by_id.get(route["source_depot_id"])
        if not depot or depot["status"] not in ("OPEN", "CONSTRAINED"):
            continue
        available = depot["inventory"].get(fuel_type, 0)
        headroom = station["capacity"].get(fuel_type, 0) - station["inventory"].get(fuel_type, 0)
        quantity = min(shortage_l, route["max_shipment"], available, depot["dispatch_capacity_per_tick"], headroom)
        if quantity <= 0:
            continue
        feasible.append(
            {
                "transit_ticks": route["transit_ticks"],
                "route_id": route["id"],
                "source_depot_id": depot["id"],
                "destination_station_id": station["id"],
                "fuel_type": fuel_type,
                "quantity": round(quantity, 1),
            }
        )
    if not feasible:
        return None
    feasible.sort(key=lambda r: r["transit_ticks"])
    return feasible[0]


def naive_baseline_allocation(station: dict, depots_by_id: dict, routes: list[dict], fuel_type: str, shortage_l: float) -> dict | None:
    """First available route regardless of transit time — used only to show
    the heuristic recommender's improvement, not a real fallback policy."""
    for route in routes:
        if route["destination_station_id"] != station["id"] or route["status"] != "AVAILABLE":
            continue
        depot = depots_by_id.get(route["source_depot_id"])
        if not depot:
            continue
        quantity = min(shortage_l, route["max_shipment"], depot["inventory"].get(fuel_type, 0))
        if quantity > 0:
            return {"route_id": route["id"], "transit_ticks": route["transit_ticks"], "quantity": round(quantity, 1)}
    return None
