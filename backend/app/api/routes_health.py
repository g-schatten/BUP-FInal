import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app import metrics, simulator_client, state_cache
from app.auth import auth_required

router = APIRouter()

_START = time.monotonic()


@router.get("/health")
async def health():
    checks = {}

    t0 = time.monotonic()
    try:
        sim = await simulator_client.get_health()
        checks["fuel_simulator"] = {
            "status": "healthy" if sim.get("status") == "ok" else "degraded",
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "simulation": sim.get("simulation"),
        }
    except Exception as e:
        checks["fuel_simulator"] = {"status": "unhealthy", "error": str(e)}

    checks["backend_api"] = {"status": "healthy", "uptime_s": round(time.monotonic() - _START, 1)}

    # /v1/health bypasses fault injection by design (it's the liveness probe), so it can
    # report "ok" while other /v1/* calls are actively faulted. This is the signal that
    # actually reflects whether OUR decision endpoints are serving live or fallback data.
    cache_degraded, cache_reason = state_cache.is_degraded()
    checks["decision_layer"] = {"status": "degraded" if cache_degraded else "healthy", "reason": cache_reason}

    overall = "healthy" if all(c.get("status") == "healthy" for c in checks.values()) else "degraded"
    return {"status": overall, "components": checks}


@router.get("/metrics")
async def metrics_endpoint():
    return PlainTextResponse(metrics.render_prometheus())


@router.get("/api/config")
async def config():
    return {"auth_required": auth_required()}
