"""Disruption detection from live simulator state.

Uses status flips and demand_multiplier deviation rather than mirroring
/v1/events labels directly — this is what "detection" means operationally:
noticing the state changed, not re-displaying the simulator's own event feed.
"""

DEMAND_SPIKE_THRESHOLD = 1.15


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
