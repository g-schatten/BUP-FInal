"""Demand forecasting + stockout projection.

Simple on purpose: exponential smoothing over recent demand-history ticks,
projected against current inventory. No ML training step, no persisted model —
appropriate for a fixed, deterministic simulated world on a hackathon clock.
"""

TICK_MINUTES = 15
ALPHA = 0.3  # smoothing factor: higher = more weight on recent ticks


def smoothed_demand_per_tick(history: list[dict]) -> float:
    """history: demand-history rows for one station+fuel, oldest-first or not —
    we sort by tick to be safe. Returns liters/tick."""
    if not history:
        return 0.0
    rows = sorted(history, key=lambda r: r["tick"])
    level = rows[0]["demand_liters"]
    for row in rows[1:]:
        level = ALPHA * row["demand_liters"] + (1 - ALPHA) * level
    return level


def hours_to_stockout(current_inventory_l: float, demand_per_tick: float) -> float | None:
    if demand_per_tick <= 0:
        return None
    ticks_left = current_inventory_l / demand_per_tick
    return ticks_left * TICK_MINUTES / 60


def stockout_probability(hours_left: float | None, horizon_hours: float = 24.0) -> float:
    """Heuristic, not a fitted model: probability rises as projected stockout
    approaches the planning horizon. 0 if stockout isn't projected within it."""
    if hours_left is None:
        return 0.0
    if hours_left >= horizon_hours:
        return 0.0
    return round(min(1.0, (horizon_hours - hours_left) / horizon_hours), 3)
