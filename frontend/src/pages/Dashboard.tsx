import { useCallback, useEffect, useState } from "react"
import { api, getToken, setToken, type Alert, type DashboardResponse, type HealthResponse } from "../api"
import { AlertCard } from "../components/AlertCard"
import { Card, Empty, colors, fmtL, pct } from "../components/ui"
import { DisruptionsView, SystemAlertList } from "../views/DisruptionsView"
import { HistoryView } from "../views/HistoryView"
import { NetworkView } from "../views/NetworkView"
import { PlanView } from "../views/PlanView"
import { SupplyDemandView } from "../views/SupplyDemandView"

const POLL_MS = 6000

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "plan", label: "Allocation plan" },
  { id: "supply", label: "Supply & demand" },
  { id: "alerts", label: "Disruptions & alerts" },
  { id: "history", label: "Decision history" },
] as const
type TabId = (typeof TABS)[number]["id"]

function tabFromHash(): TabId {
  const h = window.location.hash.replace("#", "")
  return (TABS.find((t) => t.id === h)?.id ?? "overview") as TabId
}

interface Notice {
  tone: "success" | "error" | "warning"
  text: string
}

const NOTICE_STYLE = {
  success: { background: colors.greenBg, color: colors.greenText },
  error: { background: colors.redBg, color: colors.redText },
  warning: { background: colors.amberBg, color: colors.amberText },
}

export function Dashboard() {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>(tabFromHash)
  const [applying, setApplying] = useState<string | null>(null)
  const [approvingAll, setApprovingAll] = useState(false)
  const [notices, setNotices] = useState<Notice[]>([])
  const [token, setTokenState] = useState(getToken)

  const refresh = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api.dashboard(), api.health()])
      setData(d)
      setHealth(h)
      setLoadError(null)
    } catch (e) {
      setLoadError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  // Returns a notice rather than setting state, so "Approve all" can report every result together.
  async function submit(a: Alert): Promise<Notice> {
    const where = `${a.station_id} ${a.fuel_type}`
    try {
      const res = await api.applyAllocation(a.station_id, a.fuel_type)
      const alloc = res.allocation
      if (alloc.accepted) {
        const impact = res.impact ? ` Expected risk ${pct(res.impact.risk_before)} → ${pct(res.impact.risk_after)}.` : ""
        return {
          tone: "success",
          text: `Shipment #${alloc.id} created: ${fmtL(res.recommendation.quantity)} from ${res.recommendation.source_depot_id} to ${where}.${impact}`,
        }
      }
      return alloc.degraded_mode
        ? { tone: "warning", text: `${where}: simulator unavailable (${alloc.code}) — shipment not sent, try again shortly.` }
        : { tone: "error", text: `${where}: rejected by the simulator — ${alloc.code}: ${alloc.reason}` }
    } catch (e) {
      return { tone: "error", text: `${where}: ${(e as Error).message}` }
    }
  }

  async function apply(a: Alert) {
    setApplying(`${a.station_id}-${a.fuel_type}`)
    const notice = await submit(a)
    setNotices([notice])
    setApplying(null)
    await refresh()
  }

  async function approveAll() {
    if (!data) return
    setApprovingAll(true)
    const results: Notice[] = []
    // Sequential, most urgent first: each apply recomputes the plan with the previous shipment counted.
    for (const a of data.alerts.filter((x) => x.recommended_allocation)) results.push(await submit(a))
    setNotices(results)
    setApprovingAll(false)
    await refresh()
  }

  function saveToken(value: string) {
    setTokenState(value)
    setToken(value)
  }

  const degraded = health?.status !== "healthy" || !!data?.degraded_mode
  const serious = data?.system_alerts.filter((a) => a.level !== "info").length ?? 0
  const anyCritical = data?.system_alerts.some((a) => a.level === "critical") ?? false
  const simTime = data?.sim_time ? new Date(data.sim_time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "20px 24px", maxWidth: 1280, margin: "0 auto", color: colors.text }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>Fuel Supply Operations</h1>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {data?.auth_required && (
            <input
              type="password"
              placeholder="Operator token"
              value={token}
              onChange={(e) => saveToken(e.target.value)}
              style={{ fontSize: 12, padding: "4px 8px", border: `1px solid ${colors.border}`, borderRadius: 6, width: 140 }}
            />
          )}
          <span
            style={{
              padding: "4px 10px",
              borderRadius: 12,
              fontSize: 13,
              background: degraded ? colors.amberBg : colors.greenBg,
              color: degraded ? colors.amberText : colors.greenText,
            }}
          >
            {degraded ? `DEGRADED MODE${data?.degraded_reason ? ` (${data.degraded_reason})` : ""}` : "system healthy"}
            {data?.tick != null && ` · tick ${data.tick}`}
            {simTime && ` · ${simTime}`}
          </span>
        </div>
      </header>

      <nav style={{ display: "flex", gap: 4, marginTop: 16, borderBottom: `1px solid ${colors.border}`, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <a
            key={t.id}
            href={`#${t.id}`}
            style={{
              padding: "8px 12px",
              fontSize: 14,
              textDecoration: "none",
              color: tab === t.id ? colors.blue : colors.muted,
              borderBottom: `2px solid ${tab === t.id ? colors.blue : "transparent"}`,
              marginBottom: -1,
            }}
          >
            {t.label}
            {t.id === "alerts" && serious > 0 && (
              <span style={{ marginLeft: 6, background: anyCritical ? colors.red : colors.amber, color: "#fff", borderRadius: 9, fontSize: 11, padding: "0 6px" }}>
                {serious}
              </span>
            )}
            {t.id === "plan" && data?.plan.totals && data.plan.totals.shipments_planned > 0 && (
              <span style={{ marginLeft: 6, background: colors.blue, color: "#fff", borderRadius: 9, fontSize: 11, padding: "0 6px" }}>
                {data.plan.totals.shipments_planned}
              </span>
            )}
          </a>
        ))}
      </nav>

      {loadError && <div style={{ ...NOTICE_STYLE.error, padding: 8, borderRadius: 6, marginTop: 12, fontSize: 13 }}>Can't load data: {loadError}</div>}
      {notices.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
          {notices.map((n, i) => (
            <div key={i} style={{ ...NOTICE_STYLE[n.tone], padding: "8px 10px", borderRadius: 6, fontSize: 13, display: "flex", justifyContent: "space-between" }}>
              <span>{n.text}</span>
              {i === 0 && (
                <button onClick={() => setNotices([])} style={{ border: "none", background: "transparent", cursor: "pointer", color: "inherit" }}>
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <main style={{ marginTop: 16 }}>
        {!data ? (
          <Empty>Loading…</Empty>
        ) : tab === "overview" ? (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", gap: 16 }}>
            <NetworkView stations={data.stations} depots={data.depots} />
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <Card title="System alerts">
                <SystemAlertList alerts={data.system_alerts} limit={4} />
              </Card>
              <Card title="Stockout alerts" right={<a href="#plan" style={{ fontSize: 12, color: colors.blue }}>full plan →</a>}>
                {data.alerts.length === 0 ? (
                  <Empty>No projected stockouts in the next 24h.</Empty>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {data.alerts.map((a) => (
                      <AlertCard
                        key={`${a.station_id}-${a.fuel_type}`}
                        alert={a}
                        applying={applying === `${a.station_id}-${a.fuel_type}` || approvingAll}
                        onApply={() => apply(a)}
                      />
                    ))}
                  </div>
                )}
              </Card>
            </div>
          </div>
        ) : tab === "plan" ? (
          <PlanView
            alerts={data.alerts}
            totals={data.plan.totals}
            budgets={data.plan.budgets}
            fallback={data.mode === "fallback"}
            applying={applying}
            approvingAll={approvingAll}
            onApply={apply}
            onApproveAll={approveAll}
          />
        ) : tab === "supply" ? (
          <SupplyDemandView regional={data.regional_demand} incoming={data.incoming} reliability={data.transport_reliability} />
        ) : tab === "alerts" ? (
          <DisruptionsView systemAlerts={data.system_alerts} disruptions={data.disruptions} />
        ) : (
          <HistoryView history={data.history} />
        )}
      </main>
    </div>
  )
}
