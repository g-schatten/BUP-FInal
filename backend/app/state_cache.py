"""Short-TTL cache over simulator reads, with degraded-mode fallback.

When the simulator is RUNNING it can advance several ticks per wall-clock second,
so the TTL is short. Two distinct
failure modes, both handled by serving the last known-good value instead of
propagating an error:
- X-Simulator-Stale: true (simulator says its own answer isn't trustworthy)
- SimulatorError, e.g. 503 FAULT_INJECTED (simulator is actively unreachable)

`is_degraded()` lets /health and the UI show when we're serving cached data
instead of live — this is the "keep it working" resilience story, not a
silent failure.
"""

import time

from app import metrics
from app import simulator_client as sc
from app.logging_utils import log_event
from app.simulator_client import SimulatorError

_TTL_S = 3.0
_cache: dict[str, tuple[float, list[dict]]] = {}
_previous: dict[str, list[dict]] = {}  # value the cache held just before its last real update
_degraded_reason: str | None = None


def is_degraded() -> tuple[bool, str | None]:
    return _degraded_reason is not None, _degraded_reason


def previous(key: str) -> list[dict] | None:
    """Snapshot from one poll ago — for change-detection (e.g. abnormal inventory drop).
    None until the second successful fetch."""
    return _previous.get(key)


async def _get(key: str, fetch) -> list[dict]:
    global _degraded_reason
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < _TTL_S:
        return cached[1]

    try:
        data, stale = await fetch()
    except SimulatorError as e:
        if cached is not None:
            reason = f"{key}: {e.code}"
            if _degraded_reason != reason:
                log_event("integration_failure", key=key, code=e.code, message=e.message)
                metrics.inc("integration_failures_total")
            _degraded_reason = reason
            return cached[1]
        raise

    if stale and cached is not None:
        _degraded_reason = f"{key}: stale"
        return cached[1]

    if _degraded_reason is not None:
        log_event("recovery", previous_reason=_degraded_reason)
    _degraded_reason = None
    if cached is not None:
        _previous[key] = cached[1]
    _cache[key] = (now, data)
    return data


async def get_stations() -> list[dict]:
    return await _get("stations", sc.get_stations_with_staleness)


async def get_depots() -> list[dict]:
    return await _get("depots", sc.get_depots_with_staleness)


async def get_routes() -> list[dict]:
    return await _get("routes", sc.get_routes_with_staleness)


async def get_regions() -> list[dict]:
    return await _get("regions", sc.get_regions_with_staleness)


def invalidate(*keys: str):
    """Force a refetch after we change the world (e.g. a shipment just took depot stock),
    so the next plan doesn't reuse up-to-3s-old inventory. Expires rather than deletes,
    so the old value is still there as a fallback if that refetch hits a fault."""
    for key in keys:
        if key in _cache:
            _cache[key] = (float("-inf"), _cache[key][1])
