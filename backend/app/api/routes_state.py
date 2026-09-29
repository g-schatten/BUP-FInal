from fastapi import APIRouter

from app import simulator_client as sc
from app import state_cache

router = APIRouter(prefix="/api")


@router.get("/stations")
async def stations():
    return await state_cache.get_stations()


@router.get("/depots")
async def depots():
    return await state_cache.get_depots()


@router.get("/demand-history/{station_id}")
async def demand_history(station_id: str, limit: int = 200):
    return await sc.get_demand_history(station_id, limit)


@router.get("/events")
async def events():
    return await sc.get_events()
