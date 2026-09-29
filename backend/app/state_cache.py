"""Short-TTL cache over simulator reads, with degraded-mode fallback.

The simulator ticks every 15 sim-minutes at 8 ticks/sec wall-clock by default —
state changes fast in wall-clock time, so the TTL is short. Two distinct
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
_degraded_reason: str | None = None


def is_degraded() -> tuple[bool, str | None]:
    return _degraded_reason is not None, _degraded_reason


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
    _cache[key] = (now, data)
    return data


async def get_stations() -> list[dict]:
    return await _get("stations", sc.get_stations_with_staleness)


async def get_depots() -> list[dict]:
    return await _get("depots", sc.get_depots_with_staleness)


async def get_routes() -> list[dict]:
    return await _get("routes", sc.get_routes_with_staleness)
