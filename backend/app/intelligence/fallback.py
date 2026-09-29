"""Rule-based fallback used only when live simulator data is unavailable
(demand-history fetch faulted, or the primary path errors for any reason).

Deliberately dumb: no forecasting, first-available route, fixed conservative
quantity. The point of this module is staying usable when the smart path
can't run — not staying smart. Section 11 "ML model unavailable -> fallback
allocation policy".
"""

FALLBACK_QUANTITY_L = 3000
LOW_INVENTORY_RATIO = 0.3
FUEL_TYPES = ["DIESEL", "PETROL", "OCTANE"]
USABLE_DEPOT_STATUSES = ("OPEN", "CONSTRAINED")


def fallback_alerts(stations: list[dict], depots_by_id: dict, routes: list[dict]) -> list[dict]:
    out = []
    for station in stations:
        for fuel in FUEL_TYPES:
            capacity = station["capacity"].get(fuel, 0)
            inventory = station["inventory"].get(fuel, 0)
            if capacity <= 0 or inventory / capacity >= LOW_INVENTORY_RATIO:
                continue

            route = next((r for r in routes if r["destination_station_id"] == station["id"] and r["status"] == "AVAILABLE"), None)
            recommendation = None
            if route:
                depot = depots_by_id.get(route["source_depot_id"])
                if depot and depot["status"] in USABLE_DEPOT_STATUSES and depot["inventory"].get(fuel, 0) > 0:
                    recommendation = {
                        "route_id": route["id"],
                        "source_depot_id": depot["id"],
                        "destination_station_id": station["id"],
                        "fuel_type": fuel,
                        "quantity": min(FALLBACK_QUANTITY_L, route["max_shipment"], depot["inventory"][fuel]),
                        "transit_ticks": route["transit_ticks"],
                    }

            out.append(
                {
                    "station_id": station["id"],
                    "fuel_type": fuel,
                    # no demand-rate data available in fallback mode, so no real hours-to-stockout —
                    # inventory/capacity ratio is the best signal we have left.
                    "projected_stockout_hours": None,
                    "current_inventory_l": inventory,
                    "expected_demand_l": 0,
                    "stockout_probability": round(max(0.0, 1 - inventory / capacity), 3),
                    "recommended_allocation": recommendation,
                }
            )
    return out
