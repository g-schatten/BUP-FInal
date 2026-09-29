"""Client for the real BUP Fuel Supply Simulator (asifmahmoud414/bup-fuel-supply-simulator:1.0.0).

Contract: problem/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf
- REST (/v1/*) is the source of truth; SSE (/v1/stream) is only a hint to re-GET.
- /v1/health and /admin/* bypass fault injection; every other /v1/* path can return
  503 {"error": {"code": "FAULT_INJECTED", ...}} while a fault is active.
- POST /v1/allocations is the only domain-mutating endpoint. idempotency_key makes
  retries safe: same key + same body replays the existing allocation (still 201).
"""

import asyncio
import os

import httpx

SIMULATOR_BASE_URL = os.environ.get("SIMULATOR_BASE_URL", "http://localhost:8000")

_RETRYABLE_STATUS = {503}
_MAX_RETRIES = 2

# Bulkhead: the simulator's own SQLAlchemy pool caps at 15 connections (5 + 10
# overflow) — a load test at 20 concurrent /api/alerts (each holding 1 connection
# at a time) saturated it and required restarting the simulator container to
# recover. This caps OUR total concurrent outbound requests regardless of how
# many callers we have, so we can never be the one to trigger that again.
_SIMULATOR_CONCURRENCY_LIMIT = asyncio.Semaphore(10)


class SimulatorError(Exception):
    """Raised for any non-2xx response. `code` is the machine-readable reason
    (FAULT_INJECTED, NOT_FOUND, INSUFFICIENT_INVENTORY, ...) so callers can
    decide fallback behavior without string-matching messages."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"{status_code} {code}: {message}")


def _extract_error(resp: httpx.Response) -> SimulatorError:
    try:
        body = resp.json()
    except Exception:
        return SimulatorError(resp.status_code, "UNKNOWN", resp.text[:200])
    # Fault injection: {"error": {"code": ..., "message": ...}}
    # Domain errors:    {"detail": {"code": ..., "message": ...}}
    # Pydantic 422:      {"detail": [...]}
    payload = body.get("error") or body.get("detail") or {}
    if isinstance(payload, dict):
        return SimulatorError(resp.status_code, payload.get("code", "UNKNOWN"), payload.get("message", str(body)))
    return SimulatorError(resp.status_code, "VALIDATION_ERROR", str(payload))


async def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    async with _SIMULATOR_CONCURRENCY_LIMIT:
        async with httpx.AsyncClient(base_url=SIMULATOR_BASE_URL, timeout=10.0) as client:
            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    resp = await client.request(method, path, params=params, json=json)
                except httpx.RequestError as e:
                    last_exc = e
                    continue
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    # idempotency_key (when present in json) makes this safe to retry as-is.
                    continue
                if resp.status_code >= 400:
                    raise _extract_error(resp)
                return resp.json()
            raise SimulatorError(503, "UNREACHABLE", str(last_exc) if last_exc else "simulator unreachable")


async def _request_with_staleness(path: str) -> tuple[dict, bool]:
    """Same as _request() but also surfaces X-Simulator-Stale for callers that cache."""
    async with _SIMULATOR_CONCURRENCY_LIMIT:
        async with httpx.AsyncClient(base_url=SIMULATOR_BASE_URL, timeout=10.0) as client:
            last_exc: Exception | None = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    resp = await client.get(path)
                except httpx.RequestError as e:
                    last_exc = e
                    continue
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    continue
                if resp.status_code >= 400:
                    raise _extract_error(resp)
                return resp.json(), resp.headers.get("X-Simulator-Stale") == "true"
            raise SimulatorError(503, "UNREACHABLE", str(last_exc) if last_exc else "simulator unreachable")


# ---- /v1/* public, read-only, subject to fault injection ----

async def get_health() -> dict:
    """Bypasses fault injection — use as the liveness probe, not get_stations()."""
    return await _request("GET", "/v1/health")


async def get_instance() -> dict:
    return await _request("GET", "/v1/instance")


async def get_regions() -> list[dict]:
    return await _request("GET", "/v1/regions")


async def get_depots() -> list[dict]:
    return await _request("GET", "/v1/depots")


async def get_depots_with_staleness() -> tuple[list[dict], bool]:
    return await _request_with_staleness("/v1/depots")


async def get_depot(depot_id: str) -> dict:
    return await _request("GET", f"/v1/depots/{depot_id}")


async def get_stations() -> list[dict]:
    return await _request("GET", "/v1/stations")


async def get_stations_with_staleness() -> tuple[list[dict], bool]:
    return await _request_with_staleness("/v1/stations")


async def get_station(station_id: str) -> dict:
    return await _request("GET", f"/v1/stations/{station_id}")


async def get_routes() -> list[dict]:
    return await _request("GET", "/v1/routes")


async def get_routes_with_staleness() -> tuple[list[dict], bool]:
    return await _request_with_staleness("/v1/routes")


async def get_supply_arrivals() -> list[dict]:
    return await _request("GET", "/v1/supply-arrivals")


async def get_events() -> list[dict]:
    return await _request("GET", "/v1/events")


async def get_demand_history(station_id: str | None = None, limit: int = 200) -> list[dict]:
    params: dict = {"limit": max(1, min(limit, 2000))}
    if station_id:
        params["station_id"] = station_id
    return await _request("GET", "/v1/demand-history", params=params)


async def get_metrics() -> dict:
    return await _request("GET", "/v1/metrics")


async def get_allocations() -> list[dict]:
    return await _request("GET", "/v1/allocations")


# ---- /v1/allocations — the only domain write ----

async def post_allocation(
    idempotency_key: str,
    source_depot_id: str,
    destination_station_id: str,
    route_id: str,
    fuel_type: str,
    quantity: float,
) -> dict:
    return await _request(
        "POST",
        "/v1/allocations",
        json={
            "idempotency_key": idempotency_key,
            "source_depot_id": source_depot_id,
            "destination_station_id": destination_station_id,
            "route_id": route_id,
            "fuel_type": fuel_type,
            "quantity": quantity,
        },
    )


async def cancel_allocation(allocation_id: int) -> dict:
    """Only valid while status == PENDING. Refunds depot inventory."""
    return await _request("POST", f"/v1/allocations/{allocation_id}/cancel")


# ---- /admin/* — bypasses fault injection; self-test + demo control only,
# never part of the graded decision path ----

async def admin_run() -> dict:
    return await _request("POST", "/admin/run")


async def admin_pause() -> dict:
    return await _request("POST", "/admin/pause")


async def admin_step() -> dict:
    return await _request("POST", "/admin/step")


async def admin_reset() -> dict:
    return await _request("POST", "/admin/reset")


async def admin_inject_event(event_type: str, start_tick: int, duration_ticks: int, parameters: dict | None = None) -> dict:
    return await _request(
        "POST",
        "/admin/events",
        json={"type": event_type, "start_tick": start_tick, "duration_ticks": duration_ticks, "parameters": parameters or {}},
    )


async def admin_inject_fault(fault_type: str, duration_seconds: int, parameters: dict | None = None) -> dict:
    return await _request(
        "POST",
        "/admin/faults",
        json={"type": fault_type, "duration_seconds": duration_seconds, "parameters": parameters or {}},
    )


async def admin_clear_faults() -> dict:
    return await _request("POST", "/admin/faults/clear")


async def admin_audit(limit: int = 200) -> list[dict]:
    return await _request("GET", "/admin/audit", params={"limit": max(1, min(limit, 1000))})
