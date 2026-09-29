import type { Alert, DepotBudget, FuelType, PlanTotals } from "../api"
import { Button, Card, Empty, Pill, Stat, colors, fmtH, fmtL, pct, riskColor, table, td, th } from "../components/ui"

const FUELS: FuelType[] = ["DIESEL", "PETROL", "OCTANE"]

interface Props {
  alerts: Alert[]
  totals: PlanTotals | null
  budgets: DepotBudget[]
  fallback: boolean
  applying: string | null
  approvingAll: boolean
  onApply: (a: Alert) => void
  onApproveAll: () => void
}

function DispatchBar({ b }: { b: DepotBudget }) {
  const seg = (value: number, color: string, label: string) =>
    value > 0 ? <div title={`${label}: ${value.toFixed(0)} L`} style={{ width: `${(value / b.dispatch_capacity) * 100}%`, background: color, height: "100%" }} /> : null
  return (
    <div>
      <div style={{ display: "flex", height: 14, borderRadius: 4, overflow: "hidden", background: colors.border }}>
        {seg(b.dispatch_pending, colors.muted, "already sent this tick")}
        {seg(b.dispatch_planned, colors.blue, "planned")}
      </div>
      <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>
        {fmtL(b.dispatch_pending)} already sent · {fmtL(b.dispatch_planned)} planned · {fmtL(b.dispatch_left)} left of {fmtL(b.dispatch_capacity)} this tick
      </div>
    </div>
  )
}

export function PlanView({ alerts, totals, budgets, fallback, applying, approvingAll, onApply, onApproveAll }: Props) {
  const planned = alerts.filter((a) => a.recommended_allocation)
  const unserved = alerts.filter((a) => !a.recommended_allocation)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <Card title="How it decides">
        <div style={{ fontSize: 13, color: colors.text, lineHeight: 1.5 }}>
          Every projected shortage is planned together against each depot's fuel on hand and its dispatch capacity for this tick. Stations are ranked by how
          soon they run dry; the most urgent claims capacity first, and each shipment is subtracted before the next is planned — so every row below is
          feasible alongside the rows above it, whatever order you approve them in. Route choice prefers a route that lands before the stockout.
          {fallback && (
            <div style={{ marginTop: 8, color: colors.amberText }}>
              Degraded mode: the planner can't run right now, so these are rule-based fallback recommendations (no forecast, no coordination).
            </div>
          )}
        </div>
      </Card>

      {totals && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Stat label="Planned this tick" value={`${totals.shipments_planned} shipments`} sub={`${fmtL(totals.liters_planned)} total`} />
          <Stat label="Unmet demand, next 24h" value={`${fmtL(totals.unmet_24h_before_l)} → ${fmtL(totals.unmet_24h_after_l)}`} sub={`${fmtL(totals.unmet_avoided_l)} avoided by this plan`} />
          <Stat label="Projected service level, 24h" value={`${pct(totals.service_level_before)} → ${pct(totals.service_level_after)}`} sub="served ÷ demand" />
          <Stat label="Waiting for capacity" value={totals.unserved} sub="shortages with no shipment this tick" />
        </div>
      )}

      {budgets.length > 0 && (
        <Card title="Depot budgets this tick">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
            {budgets.map((b) => (
              <div key={b.depot_id}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{b.depot_name}</div>
                <DispatchBar b={b} />
                <table style={{ ...table, marginTop: 8 }}>
                  <thead>
                    <tr>
                      <th style={th}>Fuel</th>
                      <th style={th}>Stock now</th>
                      <th style={th}>Planned out</th>
                      <th style={th}>After plan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {FUELS.filter((f) => b.stock[f]).map((f) => (
                      <tr key={f}>
                        <td style={td}>{f}</td>
                        <td style={td}>{fmtL(b.stock[f].now)}</td>
                        <td style={td}>{b.stock[f].planned > 0 ? fmtL(b.stock[f].planned) : "—"}</td>
                        <td style={td}>{fmtL(b.stock[f].after)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card
        title="Recommended allocations"
        right={
          planned.length > 0 && (
            <Button variant="primary" onClick={onApproveAll} disabled={approvingAll || applying !== null}>
              {approvingAll ? "Approving…" : `Approve all ${planned.length}`}
            </Button>
          )
        }
      >
        {planned.length === 0 ? (
          <Empty>Nothing to ship this tick.</Empty>
        ) : (
          <table style={table} className="app-table">
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>Station · fuel</th>
                <th style={th}>{fallback ? "Stock (no forecast)" : "Runs dry in"}</th>
                <th style={th}>Ship</th>
                <th style={th}>From · route</th>
                <th style={th}>Arrives in</th>
                <th style={th}>Expected impact</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {planned.map((a) => {
                const rec = a.recommended_allocation!
                const key = `${a.station_id}-${a.fuel_type}`
                return (
                  <tr key={key}>
                    <td style={td}>{a.priority ?? "—"}</td>
                    <td style={td}>
                      {a.station_id}
                      <div style={{ color: colors.muted, fontSize: 12 }}>{a.fuel_type}</div>
                    </td>
                    <td style={{ ...td, color: riskColor(a.stockout_probability) }}>
                      {fallback ? `${fmtL(a.current_inventory_l)} left` : fmtH(a.projected_stockout_hours)}
                    </td>
                    <td style={td}>
                      <strong>{fmtL(rec.quantity)}</strong>
                    </td>
                    <td style={td}>
                      {rec.source_depot_id}
                      <div style={{ color: colors.muted, fontSize: 12 }}>{rec.route_id}</div>
                    </td>
                    <td style={td}>
                      {rec.arrival_hours != null ? fmtH(rec.arrival_hours) : `${rec.transit_ticks} ticks`}{" "}
                      {rec.arrives_before_stockout === false ? <Pill tone="red">late</Pill> : rec.arrives_before_stockout ? <Pill tone="green">in time</Pill> : null}
                    </td>
                    <td style={td}>
                      {a.impact ? (
                        <>
                          risk {pct(a.impact.risk_before)} → <strong>{pct(a.impact.risk_after)}</strong>
                          <div style={{ color: colors.muted, fontSize: 12 }}>
                            dry in {fmtH(a.impact.hours_to_stockout_before)} → {fmtH(a.impact.hours_to_stockout_after)} · {fmtL(a.impact.unmet_avoided_l)} saved
                          </div>
                        </>
                      ) : (
                        "—"
                      )}
                      {((a.signals && a.signals.length > 0) || (rec.alternatives && rec.alternatives.length > 0)) && (
                        <details style={{ marginTop: 2 }}>
                          <summary style={{ fontSize: 12, color: colors.blue, cursor: "pointer" }}>inspect</summary>
                          <div style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>
                            {a.confidence && (
                              <div>
                                <Pill tone={a.confidence === "high" ? "green" : a.confidence === "medium" ? "amber" : "red"}>{a.confidence} confidence</Pill>
                              </div>
                            )}
                            {a.signals?.map((s) => <div key={s}>• {s}</div>)}
                            {rec.alternatives?.map((alt) => (
                              <div key={alt.route_id}>
                                alt: {fmtL(alt.quantity)} via {alt.route_id} — {alt.not_chosen_because}
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                    </td>
                    <td style={td}>
                      <Button disabled={applying !== null || approvingAll} onClick={() => onApply(a)}>
                        {applying === key ? "…" : "Approve"}
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>

      {unserved.length > 0 && (
        <Card title="Shortages waiting for capacity">
          <table style={table} className="app-table">
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>Station · fuel</th>
                <th style={th}>Runs dry in</th>
                <th style={th}>Unmet next 24h</th>
                <th style={th}>Why nothing ships this tick</th>
              </tr>
            </thead>
            <tbody>
              {unserved.map((a) => (
                <tr key={`${a.station_id}-${a.fuel_type}`}>
                  <td style={td}>{a.priority ?? "—"}</td>
                  <td style={td}>
                    {a.station_id} · {a.fuel_type}
                  </td>
                  <td style={{ ...td, color: riskColor(a.stockout_probability) }}>{fmtH(a.projected_stockout_hours)}</td>
                  <td style={td}>{fmtL(a.projected_unmet_l)}</td>
                  <td style={{ ...td, color: colors.muted }}>{a.allocation_note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
