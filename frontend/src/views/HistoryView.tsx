import type { DashboardResponse } from "../api"
import { Card, Empty, Pill, colors, fmtH, fmtL, pct, table, td, th } from "../components/ui"

const STATUS_TONE: Record<string, "blue" | "green" | "red" | "gray"> = {
  PENDING: "gray",
  IN_TRANSIT: "blue",
  ARRIVED: "green",
  FAILED: "red",
  CANCELLED: "gray",
}

export function HistoryView({ history }: { history: DashboardResponse["history"] }) {
  if (!history) return <Card title="Decision history"><Empty>Unavailable in degraded mode.</Empty></Card>
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <Card title="Shipments" right={<span style={{ fontSize: 12, color: colors.muted }}>simulator ledger + the context each was approved under</span>}>
        {history.shipments.length === 0 ? (
          <Empty>No shipments yet.</Empty>
        ) : (
          <table style={table} className="app-table">
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>Tick</th>
                <th style={th}>To · fuel</th>
                <th style={th}>Quantity</th>
                <th style={th}>From · route</th>
                <th style={th}>Status</th>
                <th style={th}>Approved when</th>
                <th style={th}>Expected impact</th>
              </tr>
            </thead>
            <tbody>
              {history.shipments.map((s) => (
                <tr key={s.id}>
                  <td style={td}>{s.id}</td>
                  <td style={td}>{s.created_tick}</td>
                  <td style={td}>
                    {s.station_id}
                    <div style={{ color: colors.muted, fontSize: 12 }}>{s.fuel_type}</div>
                  </td>
                  <td style={td}>{fmtL(s.quantity)}</td>
                  <td style={td}>
                    {s.source_depot_id}
                    <div style={{ color: colors.muted, fontSize: 12 }}>{s.route_id}</div>
                  </td>
                  <td style={td}>
                    <Pill tone={STATUS_TONE[s.status] ?? "gray"}>{s.status.toLowerCase().replace("_", " ")}</Pill>
                    <div style={{ color: colors.muted, fontSize: 12, marginTop: 2 }}>
                      {s.arrived_tick != null ? `arrived tick ${s.arrived_tick}` : s.status === "FAILED" ? s.failure_reason : `eta tick ${s.eta_tick}`}
                    </div>
                  </td>
                  <td style={td}>
                    {s.context ? (
                      <>
                        {pct(s.context.risk_at_approval)} risk, dry in {fmtH(s.context.hours_to_stockout_at_approval)}
                        <div style={{ color: colors.muted, fontSize: 12 }}>
                          {s.context.policy === "planner" ? `planner, priority #${s.context.priority}` : "fallback policy"}
                        </div>
                      </>
                    ) : (
                      <span style={{ color: colors.muted, fontSize: 12 }}>{s.origin}</span>
                    )}
                  </td>
                  <td style={td}>
                    {s.context?.impact ? (
                      <>
                        risk {pct(s.context.impact.risk_before)} → {pct(s.context.impact.risk_after)}
                        <div style={{ color: colors.muted, fontSize: 12 }}>{fmtL(s.context.impact.unmet_avoided_l)} unmet avoided</div>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Rejected attempts" right={<span style={{ fontSize: 12, color: colors.muted }}>never reached the ledger</span>}>
        {history.rejected.length === 0 ? (
          <Empty>No rejected attempts.</Empty>
        ) : (
          <table style={table} className="app-table">
            <thead>
              <tr>
                <th style={th}>When</th>
                <th style={th}>To · fuel</th>
                <th style={th}>Quantity</th>
                <th style={th}>From</th>
                <th style={th}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {history.rejected.map((r, i) => (
                <tr key={i}>
                  <td style={td}>{new Date(r.attempted_at * 1000).toLocaleTimeString()}</td>
                  <td style={td}>
                    {r.station_id} · {r.fuel_type}
                  </td>
                  <td style={td}>{fmtL(r.quantity)}</td>
                  <td style={td}>{r.source_depot_id}</td>
                  <td style={td}>
                    <Pill tone={r.outage ? "amber" : "red"}>{r.code}</Pill> <span style={{ fontSize: 12, color: colors.muted }}>{r.message}</span>
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
