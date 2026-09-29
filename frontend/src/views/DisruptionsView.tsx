import type { DashboardResponse, Disruption, SystemAlert } from "../api"
import { Card, Empty, Pill, colors, fmtH, table, td, th } from "../components/ui"

const LEVEL_TONE = { critical: "red", warning: "amber", info: "blue" } as const

function describeDisruption(d: Disruption): string {
  switch (d.type) {
    case "station_outage":
      return `${d.station_id} is closed`
    case "anomalous_demand":
      return `${d.station_id} demand at ${d.demand_multiplier}x normal`
    case "route_disruption":
      return `${d.route_id} blocked (${d.source_depot_id} → ${d.destination_station_id})`
    case "depot_constraint":
      return `${d.depot_id} constrained`
    default:
      return d.type
  }
}

function describeTargets(params: Record<string, unknown>): string {
  const parts: string[] = []
  for (const key of ["station_ids", "region_ids", "route_ids", "depot_ids", "fuel_types"]) {
    const v = params[key]
    if (Array.isArray(v) && v.length) parts.push(v.join(", "))
  }
  if (params.multiplier != null) parts.push(`×${params.multiplier}`)
  if (params.factor != null) parts.push(`×${params.factor}`)
  if (params.delay_ticks != null) parts.push(`+${params.delay_ticks} ticks`)
  return parts.join(" · ") || "all"
}

export function SystemAlertList({ alerts, limit }: { alerts: SystemAlert[]; limit?: number }) {
  const shown = limit ? alerts.slice(0, limit) : alerts
  if (shown.length === 0) return <Empty>No system alerts.</Empty>
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {shown.map((a, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 13 }}>
          <Pill tone={LEVEL_TONE[a.level]}>{a.level}</Pill>
          <span style={{ color: colors.muted, fontSize: 12, minWidth: 80 }}>{a.category}</span>
          <span>{a.message}</span>
          {a.ts && <span style={{ color: colors.muted, fontSize: 12, marginLeft: "auto" }}>{new Date(a.ts * 1000).toLocaleTimeString()}</span>}
        </div>
      ))}
      {limit && alerts.length > limit && <div style={{ fontSize: 12, color: colors.muted }}>+{alerts.length - limit} more on the Disruptions & alerts tab</div>}
    </div>
  )
}

export function DisruptionsView({ systemAlerts, disruptions }: { systemAlerts: SystemAlert[]; disruptions: DashboardResponse["disruptions"] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <Card title="System alerts">
        <SystemAlertList alerts={systemAlerts} />
      </Card>

      <Card title="Disruptions detected now" right={<span style={{ fontSize: 12, color: colors.muted }}>from live station / route / depot state</span>}>
        {disruptions.detected.length === 0 ? (
          <Empty>No disruptions detected.</Empty>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {disruptions.detected.map((d, i) => (
              <div key={i} style={{ fontSize: 13, display: "flex", gap: 8 }}>
                <Pill tone={d.type === "station_outage" ? "red" : "amber"}>{d.type.replace("_", " ")}</Pill>
                {describeDisruption(d)}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Crisis events" right={<span style={{ fontSize: 12, color: colors.muted }}>simulator event feed</span>}>
        {disruptions.events === null ? (
          <Empty>Event feed unavailable right now.</Empty>
        ) : disruptions.events.length === 0 ? (
          <Empty>No crisis events so far.</Empty>
        ) : (
          <table style={table} className="app-table">
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>Type</th>
                <th style={th}>Targets</th>
                <th style={th}>Ticks</th>
                <th style={th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {disruptions.events.map((e) => (
                <tr key={e.id}>
                  <td style={td}>{e.id}</td>
                  <td style={td}>{e.type.replace("_", " ")}</td>
                  <td style={td}>{describeTargets(e.parameters)}</td>
                  <td style={td}>
                    {e.start_tick}–{e.end_tick}
                  </td>
                  <td style={td}>
                    {e.status === "ACTIVE" ? (
                      <Pill tone="red">active · ends in {fmtH(e.ends_in_hours)}</Pill>
                    ) : e.status === "SCHEDULED" ? (
                      <Pill tone="amber">starts in {fmtH(e.starts_in_hours)}</Pill>
                    ) : (
                      <Pill tone="gray">resolved</Pill>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
