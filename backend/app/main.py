import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import metrics
from app.api import routes_admin, routes_decision, routes_health, routes_state
from app.simulator_client import SimulatorError

app = FastAPI(title="Fuel Supply Intelligence & Resilience Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def application_metrics(request: Request, call_next):
    # Application-layer observability (Section 14): request rate, latency, error rate —
    # the domain counters in routes_decision.py cover the Intelligence layer, this covers
    # the HTTP layer itself, which nothing else was tracking.
    t0 = time.monotonic()
    response = await call_next(request)
    metrics.inc("http_requests_total")
    metrics.inc(f"http_requests_total{{status=\"{response.status_code}\"}}")
    if response.status_code >= 400:
        metrics.inc("http_errors_total")
    metrics.observe_latency("http_request_duration_seconds", time.monotonic() - t0)
    return response


@app.exception_handler(SimulatorError)
async def simulator_error_handler(request: Request, exc: SimulatorError):
    status = 503 if exc.code in ("FAULT_INJECTED", "UNREACHABLE") else 502
    return JSONResponse(status_code=status, content={"code": exc.code, "message": exc.message})


app.include_router(routes_health.router)
app.include_router(routes_state.router)
app.include_router(routes_decision.router)
app.include_router(routes_admin.router)
