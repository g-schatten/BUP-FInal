"""Passthrough to the simulator's /admin/* — self-test + demo control only.
Bypasses fault injection by design; never part of the graded decision path.
"""

from fastapi import APIRouter

from app import simulator_client as sc

router = APIRouter(prefix="/api/admin")


@router.post("/run")
async def run():
    return await sc.admin_run()


@router.post("/pause")
async def pause():
    return await sc.admin_pause()


@router.post("/step")
async def step(n: int = 1):
    result = None
    for _ in range(max(1, n)):
        result = await sc.admin_step()
    return result


@router.post("/reset")
async def reset():
    return await sc.admin_reset()


@router.post("/events")
async def inject_event(type: str, start_tick: int, duration_ticks: int):
    return await sc.admin_inject_event(type, start_tick, duration_ticks)


@router.post("/faults")
async def inject_fault(type: str, duration_seconds: int):
    return await sc.admin_inject_fault(type, duration_seconds)


@router.post("/faults/clear")
async def clear_faults():
    return await sc.admin_clear_faults()


@router.get("/audit")
async def audit(limit: int = 200):
    return await sc.admin_audit(limit)
