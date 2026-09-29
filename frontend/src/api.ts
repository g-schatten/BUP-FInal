export type FuelType = "DIESEL" | "PETROL" | "OCTANE"

export interface Station {
  id: string
  name: string
  region_id: string
  status: string
  demand_profile: string
  demand_multiplier: number
  capacity: Record<FuelType, number>
  inventory: Record<FuelType, number>
}

export interface Depot {
  id: string
  name: string
  region_id: string
  status: string
  dispatch_capacity_per_tick: number
  capacity: Record<FuelType, number>
  inventory: Record<FuelType, number>
}

export interface Recommendation {
  route_id: string
  source_depot_id: string
  destination_station_id: string
  fuel_type: FuelType
  quantity: number
  transit_ticks: number
}

export interface Alert {
  station_id: string
  fuel_type: FuelType
  projected_stockout_hours: number
  current_inventory_l: number
  expected_demand_l: number
  stockout_probability: number
  recommended_allocation: Recommendation | null
}

export interface Disruption {
  type: string
  [key: string]: unknown
}

export interface AlertsResponse {
  alerts: Alert[]
  disruptions: Disruption[]
  degraded_mode?: boolean
  degraded_reason?: string | null
}

export interface HealthResponse {
  status: string
  components: Record<string, { status: string; [key: string]: unknown }>
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message || body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export interface DemandRow {
  station_id: string
  fuel_type: FuelType
  tick: number
  demand_liters: number
  served_liters: number
  unmet_liters: number
}

export const api = {
  stations: () => json<Station[]>("/api/stations"),
  depots: () => json<Depot[]>("/api/depots"),
  alerts: () => json<AlertsResponse>("/api/alerts"),
  health: () => json<HealthResponse>("/health"),
  demandHistory: (stationId: string, limit = 30) =>
    json<DemandRow[]>(`/api/demand-history/${encodeURIComponent(stationId)}?limit=${limit}`),
  applyAllocation: (stationId: string, fuelType: FuelType) =>
    json<{ recommendation: Recommendation; allocation: Record<string, unknown> }>(
      `/api/allocations/apply?station_id=${encodeURIComponent(stationId)}&fuel_type=${fuelType}`,
      { method: "POST" },
    ),
}
