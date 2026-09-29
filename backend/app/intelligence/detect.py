"""Disruption detection from live simulator state.

Uses status flips and demand_multiplier deviation rather than mirroring
/v1/events labels directly — this is what "detection" means operationally:
noticing the state changed, not re-displaying the simulator's own event feed.
"""

DEMAND_SPIKE_THRESHOLD = 1.15
INVENTORY_DROP_RATIO = 2.0  # actual drop vs forecast's expected-this-tick demand
INVENTORY_DROP_MIN_L = 200  # floor so tiny/noisy drops don't fire


def detect_disruptions(stations: list[dict], routes: list[dict], depots: list[dict]) -> list[dict]:
    signals = []
    for s in stations:
        if s["status"] != "OPEN":
            signals.append({"type": "station_outage", "station_id": s["id"]})
        if s["demand_multiplier"] >= DEMAND_SPIKE_THRESHOLD:
            signals.append({"type": "anomalous_demand", "station_id": s["id"], "demand_multiplier": s["demand_multiplier"]})
    for r in routes:
        if r["status"] != "AVAILABLE":
            signals.append({"type": "route_disruption", "route_id": r["id"], "source_depot_id": r["source_depot_id"], "destination_station_id": r["destination_station_id"]})
    for d in depots:
        if d["status"] != "OPEN":
            signals.append({"type": "depot_constraint", "depot_id": d["id"]})
    return signals


def inventory_anomalies(stations: list[dict], previous_stations: list[dict] | None, forecasts: dict) -> list[dict]:
    """Flags a station+fuel whose stock fell further this tick than its own forecast
    expected — a drop the demand model can't explain (vs. anomalous_demand above, which
    only reads the simulator's own multiplier). None until we've seen two polls."""
    if not previous_stations:
        return []
    prev_by_id = {s["id"]: s for s in previous_stations}
    signals = []
    for s in stations:
        prev = prev_by_id.get(s["id"])
        if not prev:
            continue
        for fuel, level in s["inventory"].items():
            fc = forecasts.get((s["id"], fuel))
            if not fc:
                continue
            actual_drop = prev["inventory"].get(fuel, level) - level
            expected_drop = fc["demand_now_l"]
            if actual_drop >= max(INVENTORY_DROP_MIN_L, INVENTORY_DROP_RATIO * max(expected_drop, 1.0)):
                signals.append(
                    {
                        "type": "abnormal_inventory_change",
                        "station_id": s["id"],
                        "fuel_type": fuel,
                        "actual_drop_l": round(actual_drop, 1),
                        "expected_drop_l": round(expected_drop, 1),
                    }
                )
    return signals
