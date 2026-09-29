import type { Alert } from "../api"
import { Button, Pill, colors, fmtH, fmtL, pct, radius, riskColor, space } from "./ui"

const CONFIDENCE_TONE = { high: "green", medium: "amber", low: "red" } as const

interface Props {
  alert: Alert
  applying: boolean
  onApply: () => void
}

export function AlertCard({ alert: a, applying, onApply }: Props) {
  const rec = a.recommended_allocation
  return (
    <div style={{ background: colors.surface2, borderRadius: radius.md, padding: space[4] }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: space[2] }}>
        <strong style={{ fontSize: 13 }}>
          {a.priority != null && <span style={{ color: colors.muted, fontWeight: 400 }}>#{a.priority} </span>}
          {a.station_id} · {a.fuel_type}
        </strong>
        <span style={{ fontSize: 12, fontWeight: 600, color: riskColor(a.stockout_probability) }}>{pct(a.stockout_probability)} risk</span>
      </div>
      <div style={{ fontSize: 12, color: colors.muted, marginTop: space[2] }}>
        {a.projected_stockout_hours != null ? `stockout in ${fmtH(a.projected_stockout_hours)} · ` : ""}
        stock {fmtL(a.current_inventory_l)}
        {a.inbound_l ? ` · ${fmtL(a.inbound_l)} on the way` : ""}
        {a.expected_demand_l > 0 ? ` · 24h demand ${fmtL(a.expected_demand_l)}` : ""}
      </div>

      {(a.signals?.length || a.confidence) && (
        <details style={{ marginTop: space[2] }}>
          <summary style={{ fontSize: 12, color: colors.blue, cursor: "pointer" }}>Why at risk</summary>
          <div style={{ fontSize: 12, color: colors.text, marginTop: space[2] }}>
            {a.signals && a.signals.length > 0 && <ul style={{ margin: `0 0 ${space[1]}`, paddingLeft: 18 }}>{a.signals.map((s) => <li key={s}>{s}</li>)}</ul>}
            {a.confidence && (
              <div>
                <Pill tone={CONFIDENCE_TONE[a.confidence]}>{a.confidence} confidence</Pill>{" "}
                <span style={{ color: colors.muted }}>{a.confidence_note}</span>
              </div>
            )}
          </div>
        </details>
      )}

      {rec ? (
        <div style={{ marginTop: space[3] }}>
          <div style={{ fontSize: 12 }}>
            Recommend <strong>{fmtL(rec.quantity)}</strong> from {rec.source_depot_id}
            {rec.arrival_hours != null ? `, arrives in ${fmtH(rec.arrival_hours)}` : ` (${rec.transit_ticks} ticks transit)`}
          </div>
          {rec.arrives_before_stockout === false && (
            <div style={{ fontSize: 12, color: colors.redText, marginTop: space[1] }}>Arrives after the projected stockout — fastest option available.</div>
          )}
          {a.impact && (
            <div style={{ fontSize: 12, marginTop: space[2], color: colors.greenText }}>
              Expected: risk {pct(a.impact.risk_before)} → {pct(a.impact.risk_after)} · stockout {fmtH(a.impact.hours_to_stockout_before)} →{" "}
              {fmtH(a.impact.hours_to_stockout_after)} · {fmtL(a.impact.unmet_avoided_l)} unmet demand avoided
            </div>
          )}
          {rec.alternatives && rec.alternatives.length > 0 && (
            <details style={{ marginTop: space[2] }}>
              <summary style={{ fontSize: 12, color: colors.blue, cursor: "pointer" }}>{rec.alternatives.length} other option(s) considered</summary>
              <ul style={{ margin: `${space[2]} 0 0`, paddingLeft: 18, fontSize: 12, color: colors.muted }}>
                {rec.alternatives.map((alt) => (
                  <li key={alt.route_id}>
                    {fmtL(alt.quantity)} from {alt.source_depot_id} via {alt.route_id}, arrives in {fmtH(alt.arrival_hours)} — not chosen: {alt.not_chosen_because}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div style={{ marginTop: space[3] }}>
            <Button variant="primary" disabled={applying} onClick={onApply}>
              {applying ? "Approving…" : "Approve shipment"}
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: colors.redText, marginTop: space[2] }}>No shipment this tick: {a.allocation_note ?? "no feasible route right now"}</div>
      )}
    </div>
  )
}
