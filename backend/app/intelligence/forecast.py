"""Demand forecasting + stockout projection.

The simulator's demand model is published (integration guide §8.5-8.6), and we
checked it against a full simulated day of observed history: per tick, demand is

    daily_profile_liters / 96 x hour-of-day factor x region demand_factor x station multiplier

plus ~10% noise. We project that tick by tick across the horizon (so a forecast
made at night doesn't assume daytime demand all day), counting shipments already
on their way. A calibration ratio learned from recent observed demand scales the
model, so if the organizers change a profile mid-event the forecast corrects
itself instead of staying silently wrong.
"""

from datetime import datetime, timedelta

TICK_MINUTES = 15
TICKS_PER_DAY = 24 * 60 // TICK_MINUTES
HORIZON_TICKS = TICKS_PER_DAY
HORIZON_HOURS = HORIZON_TICKS * TICK_MINUTES / 60

CALIBRATION_ALPHA = 0.3
CALIBRATION_BOUNDS = (0.5, 2.0)
MIN_CALIBRATION_ROWS = 4
DEFAULT_SPIKE_MULTIPLIER = 1.5

DAILY_LITERS = {
    "urban_high": {"DIESEL": 8500, "PETROL": 10500, "OCTANE": 5600},
    "industrial": {"DIESEL": 14000, "PETROL": 4500, "OCTANE": 2200},
    "highway": {"DIESEL": 10500, "PETROL": 11000, "OCTANE": 6200},
    "regional": {"DIESEL": 7200, "PETROL": 7600, "OCTANE": 3600},
}

# (busy factor, off-peak factor, busy hour windows — both ends inclusive, verified against observed data)
_HOUR_FACTORS = {
    "urban_high": (1.45, 0.70, [(7, 9), (16, 20)]),
    "industrial": (1.55, 0.45, [(6, 17)]),
    "highway": (1.35, 0.75, [(6, 9), (16, 20)]),
    "regional": (1.25, 0.65, [(7, 20)]),
}


def hour_factor(profile: str, hour: int) -> float:
    busy, off_peak, windows = _HOUR_FACTORS[profile]
    return busy if any(lo <= hour <= hi for lo, hi in windows) else off_peak


def spike_multiplier(events: list[dict], station_id: str, region_id: str, tick: int) -> float:
    """Product of every demand_spike active at `tick` that targets this station.
    Empty station_ids/region_ids filters mean "applies to all", per the guide."""
    m = 1.0
    for e in events:
        if e["type"] != "demand_spike" or not (e["start_tick"] <= tick < e["end_tick"]):
            continue
        params = e.get("parameters") or {}
        if params.get("station_ids") and station_id not in params["station_ids"]:
            continue
        if params.get("region_ids") and region_id not in params["region_ids"]:
            continue
        m *= params.get("multiplier", DEFAULT_SPIKE_MULTIPLIER)
    return m


def smoothed_demand_per_tick(history: list[dict]) -> float:
    """Flat exponential-smoothed rate — only for a demand profile we don't have a model for."""
    if not history:
        return 0.0
    rows = sorted(history, key=lambda r: r["tick"])
    level = rows[0]["demand_liters"]
    for row in rows[1:]:
        level = CALIBRATION_ALPHA * row["demand_liters"] + (1 - CALIBRATION_ALPHA) * level
    return level


def _calibration(history: list[dict], model_rate) -> tuple[float, int]:
    rows = sorted(history, key=lambda r: r["tick"])
    level = None
    used = 0
    for row in rows:
        expected = model_rate(row["tick"], datetime.fromisoformat(row["sim_time"]).hour)
        if expected <= 0:
            continue
        ratio = row["demand_liters"] / expected
        level = ratio if level is None else CALIBRATION_ALPHA * ratio + (1 - CALIBRATION_ALPHA) * level
        used += 1
    if level is None or used < MIN_CALIBRATION_ROWS:
        return 1.0, used
    lo, hi = CALIBRATION_BOUNDS
    return min(hi, max(lo, level)), used


def forecast(
    station: dict,
    fuel_type: str,
    region_factor: float,
    now_tick: int,
    now_time: datetime,
    history: list[dict] | None,
    events: list[dict] | None,
    inbound_by_tick: dict[int, float],
) -> dict:
    """Project one station x fuel across the horizon.

    history: demand-history rows for this station+fuel, or None if unavailable.
    events: /v1/events, or None if unavailable (then the live multiplier is held flat).
    inbound_by_tick: liters arriving at this station for this fuel, keyed by absolute tick.
    """
    profile = station["demand_profile"]
    live_multiplier = station["demand_multiplier"]
    signals = []
    if live_multiplier >= 1.05:
        signals.append(f"active demand spike ({live_multiplier:.2f}x normal)")

    if events is not None:
        # Rebuild the multiplier timeline from events (so a spike ending later is projected
        # to end), anchored to the live value in case the reconstruction misses something.
        now_spike = spike_multiplier(events, station["id"], station["region_id"], now_tick)
        drift = live_multiplier / now_spike if now_spike > 0 else 1.0

        def multiplier_at(tick: int) -> float:
            return spike_multiplier(events, station["id"], station["region_id"], tick) * drift
    else:

        def multiplier_at(tick: int) -> float:
            return live_multiplier

    if profile in DAILY_LITERS:
        f = hour_factor(profile, now_time.hour)
        if f >= 1.2:
            signals.append(f"peak hours for {profile.replace('_', ' ')} demand ({f:.2f}x)")
    if region_factor >= 1.05:
        signals.append(f"regional demand factor {region_factor:.2f}x")

    if profile in DAILY_LITERS:

        def model_rate(tick: int, hour: int) -> float:
            base = DAILY_LITERS[profile][fuel_type] / TICKS_PER_DAY
            return base * hour_factor(profile, hour) * region_factor * multiplier_at(tick)

        if history:
            calibration, cal_rows = _calibration(history, model_rate)
        else:
            calibration, cal_rows = 1.0, 0
        if abs(calibration - 1) >= 0.15:
            signals.append(f"observed demand running {calibration:.2f}x the model estimate")

        def rate(tick: int, hour: int) -> float:
            return model_rate(tick, hour) * calibration

        if history is None:
            confidence, confidence_note = "low", "no demand history available right now — forecast uses the live multiplier only"
        elif cal_rows < MIN_CALIBRATION_ROWS:
            confidence, confidence_note = "low", f"only {cal_rows} ticks of history — calibration held at 1.0x"
        elif cal_rows < MIN_CALIBRATION_ROWS * 2:
            confidence, confidence_note = "medium", f"calibrated from {cal_rows} ticks of history"
        else:
            confidence, confidence_note = "high", f"calibrated from {cal_rows} ticks of history"
    else:
        calibration = None
        flat = smoothed_demand_per_tick(history or [])
        confidence, confidence_note = "low", "no published demand model for this profile — using smoothed history only"

        def rate(tick: int, hour: int) -> float:
            return flat

    inventory = station["inventory"].get(fuel_type, 0)
    level = inventory
    demand_total = 0.0
    inbound_total = 0.0
    unmet_total = 0.0
    stockout_ticks = None
    for k in range(1, HORIZON_TICKS + 1):
        tick = now_tick + k
        arriving = inbound_by_tick.get(tick, 0.0)
        level += arriving
        inbound_total += arriving
        demand = rate(tick, (now_time + timedelta(minutes=TICK_MINUTES * k)).hour)
        demand_total += demand
        if stockout_ticks is None and demand > 0 and demand >= level:
            stockout_ticks = (k - 1) + level / demand
        # Unserved demand is lost, not back-ordered: the tank bottoms out at zero, so a
        # shipment landing after a stockout refills from empty rather than from a deficit.
        unmet_total += max(0.0, demand - level)
        level = max(0.0, level - demand)

    hours_to_stockout = stockout_ticks * TICK_MINUTES / 60 if stockout_ticks is not None else None
    return {
        "hours_to_stockout": hours_to_stockout,
        "demand_over_horizon_l": demand_total,
        "unmet_over_horizon_l": unmet_total,
        "inbound_l": inbound_total,
        "demand_now_l": rate(now_tick + 1, (now_time + timedelta(minutes=TICK_MINUTES)).hour),
        "calibration": calibration,
        "signals": signals,
        "confidence": confidence,
        "confidence_note": confidence_note,
    }


def stockout_probability(hours_left: float | None, horizon_hours: float = HORIZON_HOURS) -> float:
    """Heuristic risk score, not a fitted probability: rises linearly as projected
    stockout approaches. 0 if stockout isn't projected within the horizon."""
    if hours_left is None or hours_left >= horizon_hours:
        return 0.0
    return round(min(1.0, (horizon_hours - hours_left) / horizon_hours), 3)
