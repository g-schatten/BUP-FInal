import { useEffect, useState } from "react"
import { api, type Depot, type FuelType, type Station } from "../api"
import { Sparkline } from "../components/Sparkline"
import { Card, FillBar, colors, table, td, th } from "../components/ui"

const FUELS: FuelType[] = ["DIESEL", "PETROL", "OCTANE"]

export function NetworkView({ stations, depots }: { stations: Station[]; depots: Depot[] }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [history, setHistory] = useState<Record<FuelType, number[]>>({ DIESEL: [], PETROL: [], OCTANE: [] })

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    api
      .demandHistory(selected, 90)
      .then((rows) => {
        if (cancelled) return
        const byFuel: Record<FuelType, number[]> = { DIESEL: [], PETROL: [], OCTANE: [] }
        for (const fuel of FUELS) byFuel[fuel] = rows.filter((r) => r.fuel_type === fuel).map((r) => r.demand_liters).reverse()
        setHistory(byFuel)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [selected])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card title="Stations" right={<span style={{ fontSize: 12, color: colors.muted }}>click a row for recent demand</span>}>
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Station</th>
              <th style={th}>Status</th>
              {FUELS.map((f) => (
                <th key={f} style={th}>
                  {f}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stations.map((s) => (
              <tr key={s.id} onClick={() => setSelected(s.id)} style={{ cursor: "pointer", background: selected === s.id ? colors.blueBg : undefined }}>
                <td style={td}>
                  {s.name}
                  {s.demand_multiplier !== 1 && <span style={{ color: colors.amberText, fontSize: 12 }}> · demand {s.demand_multiplier}x</span>}
                </td>
                <td style={td}>{s.status}</td>
                {FUELS.map((f) => (
                  <td key={f} style={td}>
                    <FillBar value={s.inventory[f] ?? 0} max={s.capacity[f] ?? 1} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {selected && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 13, marginBottom: 6 }}>{selected} — demand per tick, last ~7.5h</div>
            <div style={{ display: "flex", gap: 20 }}>
              {FUELS.map((f) => (
                <div key={f}>
                  <div style={{ fontSize: 12, color: colors.muted }}>{f}</div>
                  <Sparkline values={history[f]} />
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card title="Depots">
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Depot</th>
              <th style={th}>Status</th>
              {FUELS.map((f) => (
                <th key={f} style={th}>
                  {f}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {depots.map((d) => (
              <tr key={d.id}>
                <td style={td}>{d.name}</td>
                <td style={td}>{d.status}</td>
                {FUELS.map((f) => (
                  <td key={f} style={td}>
                    <FillBar value={d.inventory[f] ?? 0} max={d.capacity[f] ?? 1} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
