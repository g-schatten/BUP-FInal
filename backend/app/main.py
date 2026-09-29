from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_admin, routes_decision, routes_health, routes_state
from app.simulator_client import SimulatorError

app = FastAPI(title="Fuel Supply Intelligence & Resilience Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SimulatorError)
async def simulator_error_handler(request: Request, exc: SimulatorError):
    status = 503 if exc.code in ("FAULT_INJECTED", "UNREACHABLE") else 502
    return JSONResponse(status_code=status, content={"code": exc.code, "message": exc.message})


app.include_router(routes_health.router)
app.include_router(routes_state.router)
app.include_router(routes_decision.router)
app.include_router(routes_admin.router)
