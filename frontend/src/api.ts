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

export interface Alternative {
  route_id: string
  source_depot_id: string
  quantity: number
  arrival_hours: number
  arrives_before_stockout: boolean
  not_chosen_because: string
}

export interface Recommendation {
  route_id: string
  source_depot_id: string
  destination_station_id: string
  fuel_type: FuelType
  quantity: number
  transit_ticks: number
  arrival_hours?: number
  arrives_before_stockout?: boolean
  alternatives?: Alternative[]
}

export interface Impact {
  hours_to_stockout_before: number | null
  hours_to_stockout_after: number | null
  risk_before: number
  risk_after: number
  unmet_24h_before_l: number
  unmet_24h_after_l: number
  unmet_avoided_l: number
}

export interface Alert {
  station_id: string
  fuel_type: FuelType
  priority?: number
  projected_stockout_hours: number | null
  current_inventory_l: number
  inbound_l?: number
  expected_demand_l: number
  projected_unmet_l?: number
  stockout_probability: number
  signals?: string[]
  confidence?: "high" | "medium" | "low"
  confidence_note?: string
  recommended_allocation: Recommendation | null
  allocation_note?: string | null
  impact?: Impact | null
}

export interface PlanTotals {
  demand_24h_l: number
  unmet_24h_before_l: number
  unmet_24h_after_l: number
  unmet_avoided_l: number
  service_level_before: number
  service_level_after: number
  at_risk_before: number
  at_risk_after: number
  shipments_planned: number
  liters_planned: number
  unserved: number
}

export interface DepotBudget {
  depot_id: string
  depot_name: string
  dispatch_capacity: number
  dispatch_pending: number
  dispatch_planned: number
  dispatch_left: number
  stock: Record<FuelType, { now: number; planned: number; after: number }>
}

export interface RegionalDemandRow {
  region_id: string
  region_name: string
  demand_factor: number
  fuel_type: FuelType
  demand_per_hour_now_l: number | null
  demand_24h_l: number | null
  station_stock_l: number
  inbound_l: number | null
  depot_stock_l: number
  projected_unmet_24h_l: number | null
  coverage_hours: number | null
  peak_demand_multiplier: number
}

export interface DepotArrival {
  id: string
  depot_id: string
  fuel_type: FuelType
  quantity: number
  planned_tick: number
  hours_until: number
  status: string
}

export interface InboundShipment {
  id: number
  station_id: string
  fuel_type: FuelType
  quantity: number
  source_depot_id: string
  route_id: string
  status: string
  eta_tick: number
  hours_until: number
}

export interface RouteReliability {
  route_id: string
  source_depot_id: string
  destination_station_id: string
  sample_size: number
  scheduled_transit_ticks: number
  avg_delay_hours: number
  on_time_rate: number
}

export interface Disruption {
  type: string
  [key: string]: unknown
}

export interface CrisisEvent {
  id: number
  type: string
  status: string
  start_tick: number
  end_tick: number
  parameters: Record<string, unknown>
  ends_in_hours?: number
  starts_in_hours?: number
}

export interface SystemAlert {
  level: "critical" | "warning" | "info"
  category: string
  message: string
  ts?: number
}

export interface DecisionContext {
  approved_at: number
  policy: string
  priority?: number
  risk_at_approval: number
  hours_to_stockout_at_approval: number | null
  impact?: Impact | null
  sim_tick: number | null
}

export interface HistoryShipment {
  id: number
  created_tick: number
  station_id: string
  fuel_type: FuelType
  quantity: number
  source_depot_id: string
  route_id: string
  status: string
  eta_tick: number
  arrived_tick: number | null
  failure_reason: string | null
  origin: string
  context: DecisionContext | null
}

export interface RejectedAttempt {
  attempted_at: number
  station_id: string
  fuel_type: FuelType
  quantity: number
  source_depot_id: string
  route_id: string
  code: string
  message: string
  outage: boolean
}

export interface DashboardResponse {
  mode: "planner" | "fallback"
  tick: number | null
  sim_time: string | null
  degraded_mode: boolean
  degraded_reason: string | null
  auth_required: boolean
  stations: Station[]
  depots: Depot[]
  alerts: Alert[]
  plan: { totals: PlanTotals | null; budgets: DepotBudget[] }
  regional_demand: RegionalDemandRow[]
  incoming: { depot_arrivals: DepotArrival[] | null; shipments: InboundShipment[] } | null
  disruptions: { detected: Disruption[]; events: CrisisEvent[] | null }
  system_alerts: SystemAlert[]
  history: { shipments: HistoryShipment[]; rejected: RejectedAttempt[] } | null
  transport_reliability: RouteReliability[]
}

export interface HealthResponse {
  status: string
  components: Record<string, { status: string; [key: string]: unknown }>
}

export interface DemandRow {
  station_id: string
  fuel_type: FuelType
  tick: number
  demand_liters: number
  served_liters: number
  unmet_liters: number
}

export interface ApplyResult {
  recommendation: Recommendation
  allocation:
    | ({ accepted: true; id: number; status: string } & Record<string, unknown>)
    | { accepted: false; code: string; reason: string; degraded_mode: boolean }
  impact?: Impact | null
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""
const TOKEN_KEY = "operator_token"

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ""
  } catch {
    return ""
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // private window / blocked storage: token just won't persist across reloads
  }
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = Array.isArray(body.detail) ? body.detail.map((d: { msg?: string }) => d.msg).join("; ") : body.detail
    throw new Error(body.message || detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  dashboard: () => json<DashboardResponse>("/api/dashboard"),
  health: () => json<HealthResponse>("/health"),
  demandHistory: (stationId: string, limit = 30) =>
    json<DemandRow[]>(`/api/demand-history/${encodeURIComponent(stationId)}?limit=${limit}`),
  applyAllocation: (stationId: string, fuelType: FuelType) =>
    json<ApplyResult>(`/api/allocations/apply?station_id=${encodeURIComponent(stationId)}&fuel_type=${fuelType}`, {
      method: "POST",
      headers: { "X-Operator-Token": getToken() },
    }),
}
