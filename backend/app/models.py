from pydantic import BaseModel

FuelType = str  # "DIESEL" | "PETROL" | "OCTANE" — enum per simulator contract


class Station(BaseModel):
    id: str
    name: str
    region_id: str
    status: str  # OPEN | OUTAGE
    demand_profile: str
    demand_multiplier: float
    capacity: dict[FuelType, float]
    inventory: dict[FuelType, float]


class Depot(BaseModel):
    id: str
    name: str
    region_id: str
    status: str  # OPEN | CONSTRAINED
    dispatch_capacity_per_tick: float
    capacity: dict[FuelType, float]
    inventory: dict[FuelType, float]


class Alert(BaseModel):
    station_id: str
    fuel_type: FuelType
    projected_stockout_hours: float
    current_inventory_l: float
    expected_demand_l: float
    recommended_allocation_l: float
    expected_stockout_risk_reduction_pct: float


class AllocationRecommendRequest(BaseModel):
    station_id: str
    fuel_type: FuelType


class AllocationResult(BaseModel):
    accepted: bool
    reason: str | None = None
    degraded_mode: bool = False
