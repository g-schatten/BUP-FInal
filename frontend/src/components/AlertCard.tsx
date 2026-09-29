import type { Alert } from "../api"
import { Pill, colors, fmtH, fmtL, pct, riskColor } from "./ui"

const CONFIDENCE_TONE = { high: "green", medium: "amber", low: "red" } as const

interface Props {
  alert: Alert
  applying: boolean
  onApply: () => void
}

export function AlertCard({ alert: a, applying, onApply }: Props) {
  const rec = a.recommended_allocation
  return (
    <div style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ fontSize: 13 }}>
          {a.priority != null && <span style={{ color: colors.muted, fontWeight: 400 }}>#{a.priority} </span>}
          {a.station_id} · {a.fuel_type}
        </strong>
        <span style={{ fontSize: 12, color: riskColor(a.stockout_probability) }}>{pct(a.stockout_probability)} risk</span>
      </div>
      <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>
        {a.projected_stockout_hours != null ? `stockout in ${fmtH(a.projected_stockout_hours)} · ` : ""}
        stock {fmtL(a.current_inventory_l)}
        {a.inbound_l ? ` · ${fmtL(a.inbound_l)} on the way` : ""}
        {a.expected_demand_l > 0 ? ` · 24h demand ${fmtL(a.expected_demand_l)}` : ""}
      </div>

      {(a.signals?.length || a.confidence) && (
        <details style={{ marginTop: 4 }}>
          <summary style={{ fontSize: 12, color: colors.blue, cursor: "pointer" }}>Why at risk</summary>
          <div style={{ fontSize: 12, color: colors.text, marginTop: 4 }}>
            {a.signals && a.signals.length > 0 && <ul style={{ margin: "0 0 4px", paddingLeft: 18 }}>{a.signals.map((s) => <li key={s}>{s}</li>)}</ul>}
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
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 12 }}>
            Recommend <strong>{fmtL(rec.quantity)}</strong> from {rec.source_depot_id}
            {rec.arrival_hours != null ? `, arrives in ${fmtH(rec.arrival_hours)}` : ` (${rec.transit_ticks} ticks transit)`}
          </div>
          {rec.arrives_before_stockout === false && (
            <div style={{ fontSize: 12, color: colors.redText, marginTop: 2 }}>Arrives after the projected stockout — fastest option available.</div>
          )}
          {a.impact && (
            <div style={{ fontSize: 12, marginTop: 4, color: colors.greenText }}>
              Expected: risk {pct(a.impact.risk_before)} → {pct(a.impact.risk_after)} · stockout {fmtH(a.impact.hours_to_stockout_before)} →{" "}
              {fmtH(a.impact.hours_to_stockout_after)} · {fmtL(a.impact.unmet_avoided_l)} unmet demand avoided
            </div>
          )}
          {rec.alternatives && rec.alternatives.length > 0 && (
            <details style={{ marginTop: 4 }}>
              <summary style={{ fontSize: 12, color: colors.blue, cursor: "pointer" }}>{rec.alternatives.length} other option(s) considered</summary>
              <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12, color: colors.muted }}>
                {rec.alternatives.map((alt) => (
                  <li key={alt.route_id}>
                    {fmtL(alt.quantity)} from {alt.source_depot_id} via {alt.route_id}, arrives in {fmtH(alt.arrival_hours)} — not chosen: {alt.not_chosen_because}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <button disabled={applying} onClick={onApply} style={{ marginTop: 6, padding: "4px 10px", fontSize: 12, cursor: "pointer" }}>
            {applying ? "Approving…" : "Approve shipment"}
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: colors.redText, marginTop: 6 }}>No shipment this tick: {a.allocation_note ?? "no feasible route right now"}</div>
      )}
    </div>
  )
}
