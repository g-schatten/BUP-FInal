import type { DashboardResponse } from "../api"
import { Card, Empty, Pill, colors, fmtH, fmtL, table, td, th } from "../components/ui"

interface Props {
  regional: DashboardResponse["regional_demand"]
  incoming: DashboardResponse["incoming"]
  reliability: DashboardResponse["transport_reliability"]
}

export function SupplyDemandView({ regional, incoming, reliability }: Props) {
  const regions = [...new Set(regional.map((r) => r.region_id))]
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card title="Regional fuel demand">
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>Region · fuel</th>
              <th style={th}>Demand now</th>
              <th style={th}>Demand next 24h</th>
              <th style={th}>Station stock</th>
              <th style={th}>On the way</th>
              <th style={th}>Coverage</th>
              <th style={th}>Projected unmet 24h</th>
              <th style={th}>Depot stock</th>
            </tr>
          </thead>
          <tbody>
            {regions.flatMap((rid) =>
              regional
                .filter((r) => r.region_id === rid)
                .map((r, i) => (
                  <tr key={`${r.region_id}-${r.fuel_type}`}>
                    <td style={td}>
                      {i === 0 && (
                        <div style={{ fontWeight: 600 }}>
                          {r.region_name}
                          <span style={{ color: colors.muted, fontWeight: 400, fontSize: 12 }}> · demand factor {r.demand_factor}</span>
                          {r.peak_demand_multiplier > 1 && <> <Pill tone="amber">spike {r.peak_demand_multiplier}x</Pill></>}
                        </div>
                      )}
                      {r.fuel_type}
                    </td>
                    <td style={td}>{r.demand_per_hour_now_l != null ? `${fmtL(r.demand_per_hour_now_l)}/h` : "—"}</td>
                    <td style={td}>{fmtL(r.demand_24h_l)}</td>
                    <td style={td}>{fmtL(r.station_stock_l)}</td>
                    <td style={td}>{r.inbound_l ? fmtL(r.inbound_l) : "—"}</td>
                    <td style={{ ...td, color: r.coverage_hours != null && r.coverage_hours < 12 ? colors.redText : undefined }}>
                      {r.coverage_hours != null ? fmtH(r.coverage_hours) : "—"}
                    </td>
                    <td style={td}>{r.projected_unmet_24h_l ? fmtL(r.projected_unmet_24h_l) : "—"}</td>
                    <td style={td}>{fmtL(r.depot_stock_l)}</td>
                  </tr>
                )),
            )}
          </tbody>
        </table>
        <div style={{ fontSize: 12, color: colors.muted, marginTop: 8 }}>
          Coverage = hours the region's station stock plus fuel already on the way lasts at the average forecast rate for the next 24h.
        </div>
      </Card>

      <Card title="Incoming supply to depots">
        {!incoming ? (
          <Empty>Unavailable in degraded mode.</Empty>
        ) : incoming.depot_arrivals === null ? (
          <Empty>Supply schedule unavailable right now.</Empty>
        ) : incoming.depot_arrivals.length === 0 ? (
          <Empty>No more scheduled deliveries — the simulator's supply schedule is exhausted.</Empty>
        ) : (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>Delivery</th>
                <th style={th}>Depot</th>
                <th style={th}>Fuel</th>
                <th style={th}>Quantity</th>
                <th style={th}>Arrives in</th>
                <th style={th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {incoming.depot_arrivals.slice(0, 12).map((a) => (
                <tr key={a.id}>
                  <td style={td}>{a.id}</td>
                  <td style={td}>{a.depot_id}</td>
                  <td style={td}>{a.fuel_type}</td>
                  <td style={td}>{fmtL(a.quantity)}</td>
                  <td style={td}>
                    {fmtH(a.hours_until)} <span style={{ color: colors.muted, fontSize: 12 }}>(tick {a.planned_tick})</span>
                  </td>
                  <td style={td}>{a.status === "DELAYED" ? <Pill tone="amber">delayed</Pill> : <Pill tone="gray">scheduled</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Shipments on the way to stations">
        {!incoming ? (
          <Empty>Unavailable in degraded mode.</Empty>
        ) : incoming.shipments.length === 0 ? (
          <Empty>No shipments in transit.</Empty>
        ) : (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>To</th>
                <th style={th}>Fuel</th>
                <th style={th}>Quantity</th>
                <th style={th}>From · route</th>
                <th style={th}>Arrives in</th>
                <th style={th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {incoming.shipments.map((s) => (
                <tr key={s.id}>
                  <td style={td}>{s.id}</td>
                  <td style={td}>{s.station_id}</td>
                  <td style={td}>{s.fuel_type}</td>
                  <td style={td}>{fmtL(s.quantity)}</td>
                  <td style={td}>
                    {s.source_depot_id}
                    <div style={{ color: colors.muted, fontSize: 12 }}>{s.route_id}</div>
                  </td>
                  <td style={td}>
                    {fmtH(s.hours_until)} <span style={{ color: colors.muted, fontSize: 12 }}>(tick {s.eta_tick})</span>
                  </td>
                  <td style={td}>
                    <Pill tone={s.status === "IN_TRANSIT" ? "blue" : "gray"}>{s.status.toLowerCase().replace("_", " ")}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Route reliability" right={<span style={{ fontSize: 12, color: colors.muted }}>predicted delay vs. scheduled transit, from arrived shipments this run</span>}>
        {reliability.length === 0 ? (
          <Empty>No arrived shipments yet to learn from.</Empty>
        ) : (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>Route</th>
                <th style={th}>Scheduled transit</th>
                <th style={th}>Avg delay</th>
                <th style={th}>On-time rate</th>
                <th style={th}>Samples</th>
              </tr>
            </thead>
            <tbody>
              {reliability.map((r) => (
                <tr key={r.route_id}>
                  <td style={td}>
                    {r.source_depot_id} → {r.destination_station_id}
                    <div style={{ color: colors.muted, fontSize: 12 }}>{r.route_id}</div>
                  </td>
                  <td style={td}>{r.scheduled_transit_ticks} ticks</td>
                  <td style={{ ...td, color: r.avg_delay_hours > 0 ? colors.redText : colors.greenText }}>
                    {r.avg_delay_hours > 0 ? `+${fmtH(r.avg_delay_hours)}` : "on schedule"}
                  </td>
                  <td style={td}>{Math.round(r.on_time_rate * 100)}%</td>
                  <td style={td}>{r.sample_size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
