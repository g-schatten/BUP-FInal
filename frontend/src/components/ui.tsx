import type { CSSProperties, ReactNode } from "react"

// Values are CSS var() refs (defined in index.css, light + prefers-color-scheme: dark) so
// every consumer using this object is theme-aware for free — no per-component dark mode code.
export const colors = {
  bg: "var(--bg)",
  cardBg: "var(--card-bg)",
  text: "var(--text)",
  muted: "var(--muted)",
  border: "var(--border)",
  subtle: "var(--card-bg)",
  red: "var(--red)",
  redBg: "var(--red-bg)",
  redText: "var(--red-text)",
  amber: "var(--amber)",
  amberBg: "var(--amber-bg)",
  amberText: "var(--amber-text)",
  green: "var(--green)",
  greenBg: "var(--green-bg)",
  greenText: "var(--green-text)",
  blue: "var(--blue)",
  blueBg: "var(--blue-bg)",
}

export const table: CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13 }
export const th: CSSProperties = { textAlign: "left", color: colors.muted, fontWeight: 500, padding: "6px 6px", borderBottom: `1px solid ${colors.border}` }
export const td: CSSProperties = { padding: "7px 6px", borderTop: `1px solid ${colors.border}`, verticalAlign: "top" }

export function fmtL(liters: number | null | undefined): string {
  if (liters == null) return "—"
  if (Math.abs(liters) >= 1000) return `${(liters / 1000).toFixed(1)}k L`
  return `${liters.toFixed(0)} L`
}

export function fmtH(hours: number | null | undefined, nullText = "> 24h"): string {
  if (hours == null) return nullText
  return `${hours.toFixed(1)}h`
}

export function pct(x: number | null | undefined): string {
  return x == null ? "—" : `${(x * 100).toFixed(0)}%`
}

// fill ratio → color: low stock red, middle amber, healthy green
export function fillColor(ratio: number): string {
  if (ratio < 0.2) return colors.red
  if (ratio < 0.5) return colors.amber
  return colors.green
}

export function riskColor(risk: number): string {
  if (risk > 0.8) return colors.red
  if (risk > 0.5) return colors.amber
  return colors.green
}

export function Card({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: 16, background: colors.cardBg }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <h2 style={{ fontSize: 15, margin: 0, color: colors.text }}>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

export function Pill({ tone, children }: { tone: "red" | "amber" | "green" | "gray" | "blue"; children: ReactNode }) {
  const map = {
    red: [colors.redBg, colors.redText],
    amber: [colors.amberBg, colors.amberText],
    green: [colors.greenBg, colors.greenText],
    gray: [colors.border, colors.text],
    blue: [colors.blueBg, colors.blue],
  } as const
  const [bg, fg] = map[tone]
  return <span style={{ background: bg, color: fg, padding: "1px 8px", borderRadius: 10, fontSize: 12, whiteSpace: "nowrap" }}>{children}</span>
}

export function FillBar({ value, max, width = 80 }: { value: number; max: number; width?: number }) {
  const ratio = max > 0 ? value / max : 0
  return (
    <div style={{ background: colors.border, borderRadius: 4, height: 10, width, overflow: "hidden" }} title={`${value.toFixed(0)} / ${max.toFixed(0)} L`}>
      <div style={{ background: fillColor(ratio), width: `${Math.min(100, ratio * 100)}%`, height: "100%" }} />
    </div>
  )
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div style={{ border: `1px solid ${colors.border}`, borderRadius: 8, padding: "10px 12px", minWidth: 150, flex: 1 }}>
      <div style={{ fontSize: 12, color: colors.muted }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, color: colors.text, marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div style={{ color: colors.muted, fontSize: 13, padding: "6px 0" }}>{children}</div>
}
