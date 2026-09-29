import { useEffect, useState } from "react"
import { api, type Alert, type Depot, type FuelType, type HealthResponse, type Station } from "../api"
import { Sparkline } from "../components/Sparkline"

const FUELS: FuelType[] = ["DIESEL", "PETROL", "OCTANE"]
const POLL_MS = 6000

function pctColor(pct: number): string {
  if (pct < 0.2) return "#dc2626"
  if (pct < 0.5) return "#d97706"
  return "#16a34a"
}

function InventoryBar({ inventory, capacity }: { inventory: number; capacity: number }) {
  const pct = capacity > 0 ? inventory / capacity : 0
  return (
    <div style={{ background: "#e5e7eb", borderRadius: 4, height: 10, width: 80, overflow: "hidden" }}>
      <div style={{ background: pctColor(pct), width: `${Math.min(100, pct * 100)}%`, height: "100%" }} />
    </div>
  )
}

export function Dashboard() {
  const [stations, setStations] = useState<Station[]>([])
  const [depots, setDepots] = useState<Depot[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<FuelType, number[]>>({ DIESEL: [], PETROL: [], OCTANE: [] })
  const [applying, setApplying] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [degradedReason, setDegradedReason] = useState<string | null>(null)

  async function refresh() {
    try {
      const [s, d, a, h] = await Promise.all([api.stations(), api.depots(), api.alerts(), api.health()])
      setStations(s)
      setDepots(d)
      setAlerts(a.alerts)
      setDegradedReason(a.degraded_mode ? a.degraded_reason ?? "unknown" : null)
      setHealth(h)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    api.demandHistory(selected, 30).then((rows) => {
      if (cancelled) return
      const byFuel: Record<FuelType, number[]> = { DIESEL: [], PETROL: [], OCTANE: [] }
      for (const fuel of FUELS) {
        byFuel[fuel] = rows.filter((r) => r.fuel_type === fuel).map((r) => r.demand_liters)
      }
      setHistory(byFuel)
    })
    return () => {
      cancelled = true
    }
  }, [selected])

  async function apply(stationId: string, fuelType: FuelType) {
    setApplying(`${stationId}-${fuelType}`)
    try {
      await api.applyAllocation(stationId, fuelType)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setApplying(null)
    }
  }

  const degraded = health?.status !== "healthy" || degradedReason !== null

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 24, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: 22 }}>Fuel Supply Operations</h1>
        <span
          style={{
            padding: "4px 10px",
            borderRadius: 12,
            fontSize: 13,
            background: degraded ? "#fef3c7" : "#dcfce7",
            color: degraded ? "#92400e" : "#166534",
          }}
        >
          {degraded ? `DEGRADED MODE${degradedReason ? ` (${degradedReason})` : ""}` : "system healthy"} · sim tick{" "}
          {String((health?.components.fuel_simulator?.simulation as { tick?: number } | undefined)?.tick ?? "-")}
        </span>
      </div>

      {error && <div style={{ background: "#fee2e2", color: "#991b1b", padding: 8, borderRadius: 6, marginTop: 12 }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 24, marginTop: 20 }}>
        <div>
          <h2 style={{ fontSize: 16 }}>Stations</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#6b7280" }}>
                <th>Station</th>
                <th>Status</th>
                {FUELS.map((f) => (
                  <th key={f}>{f}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stations.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => setSelected(s.id)}
                  style={{ cursor: "pointer", background: selected === s.id ? "#eff6ff" : undefined, borderTop: "1px solid #f0f0f0" }}
                >
                  <td style={{ padding: "6px 4px" }}>{s.name}</td>
                  <td>{s.status}</td>
                  {FUELS.map((f) => (
                    <td key={f} style={{ padding: "6px 4px" }}>
                      <InventoryBar inventory={s.inventory[f] ?? 0} capacity={s.capacity[f] ?? 1} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          {selected && (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ fontSize: 14 }}>{selected} — recent demand</h3>
              <div style={{ display: "flex", gap: 16 }}>
                {FUELS.map((f) => (
                  <div key={f}>
                    <div style={{ fontSize: 12, color: "#6b7280" }}>{f}</div>
                    <Sparkline values={history[f]} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <h2 style={{ fontSize: 16, marginTop: 24 }}>Depots</h2>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#6b7280" }}>
                <th>Depot</th>
                <th>Status</th>
                {FUELS.map((f) => (
                  <th key={f}>{f}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {depots.map((d) => (
                <tr key={d.id} style={{ borderTop: "1px solid #f0f0f0" }}>
                  <td style={{ padding: "6px 4px" }}>{d.name}</td>
                  <td>{d.status}</td>
                  {FUELS.map((f) => (
                    <td key={f} style={{ padding: "6px 4px" }}>
                      <InventoryBar inventory={d.inventory[f] ?? 0} capacity={d.capacity[f] ?? 1} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h2 style={{ fontSize: 16 }}>Alerts</h2>
          {alerts.length === 0 && <div style={{ color: "#6b7280", fontSize: 13 }}>No active shortage risk.</div>}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {alerts.map((a) => {
              const key = `${a.station_id}-${a.fuel_type}`
              return (
                <div key={key} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong style={{ fontSize: 13 }}>
                      {a.station_id} · {a.fuel_type}
                    </strong>
                    <span style={{ fontSize: 12, color: pctColor(1 - a.stockout_probability) }}>
                      {(a.stockout_probability * 100).toFixed(0)}% risk
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "#4b5563", marginTop: 4 }}>
                    {a.projected_stockout_hours != null ? `stockout in ${a.projected_stockout_hours.toFixed(1)}h · ` : ""}
                    inventory {a.current_inventory_l.toFixed(0)}L
                    {a.expected_demand_l > 0 ? ` · expected demand ${a.expected_demand_l.toFixed(0)}L` : ""}
                  </div>
                  {a.recommended_allocation ? (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 12 }}>
                        Recommend: {a.recommended_allocation.quantity.toFixed(0)}L from {a.recommended_allocation.source_depot_id} (
                        {a.recommended_allocation.transit_ticks} ticks transit)
                      </div>
                      <button
                        disabled={applying === key}
                        onClick={() => apply(a.station_id, a.fuel_type)}
                        style={{ marginTop: 6, padding: "4px 10px", fontSize: 12, cursor: "pointer" }}
                      >
                        {applying === key ? "Applying…" : "Apply allocation"}
                      </button>
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#991b1b", marginTop: 6 }}>No feasible route right now.</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
