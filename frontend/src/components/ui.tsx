import type { CSSProperties, ReactNode } from "react"

// Values are CSS var() refs (defined in index.css, light + prefers-color-scheme: dark) so
// every consumer using this object is theme-aware for free — no per-component dark mode code.
export const colors = {
  bg: "var(--bg)",
  cardBg: "var(--surface-1)",
  surface2: "var(--surface-2)",
  text: "var(--text)",
  muted: "var(--muted)",
  border: "var(--border)",
  subtle: "var(--surface-1)",
  shadow: "var(--shadow)",
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
  accent: "var(--accent)",
  accentFg: "var(--accent-fg)",
}

// 4px scale: sp2/sp3 for tight in-group gaps, sp5/sp6 for gaps between unrelated sections.
export const space = { 1: "var(--sp-1)", 2: "var(--sp-2)", 3: "var(--sp-3)", 4: "var(--sp-4)", 5: "var(--sp-5)", 6: "var(--sp-6)", 7: "var(--sp-7)", 8: "var(--sp-8)" }
export const radius = { sm: "var(--radius-sm)", md: "var(--radius-md)", lg: "var(--radius-lg)" }

export const table: CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13 }
export const th: CSSProperties = {
  textAlign: "left",
  color: colors.muted,
  fontWeight: 500,
  fontSize: 11,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  padding: `${space[3]} ${space[3]}`,
  borderBottom: `1px solid ${colors.border}`,
}
export const td: CSSProperties = { padding: `${space[3]} ${space[3]}`, borderTop: `1px solid ${colors.border}`, verticalAlign: "top" }

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
    <section style={{ borderRadius: radius.lg, padding: space[5], background: colors.cardBg, boxShadow: colors.shadow, border: `1px solid ${colors.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: space[4], gap: space[3] }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: colors.text }}>{title}</h2>
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
    gray: [colors.surface2, colors.muted],
    blue: [colors.blueBg, colors.blue],
  } as const
  const [bg, fg] = map[tone]
  return (
    <span style={{ background: bg, color: fg, padding: "2px 9px", borderRadius: 999, fontSize: 12, fontWeight: 500, whiteSpace: "nowrap", display: "inline-block" }}>
      {children}
    </span>
  )
}

export function FillBar({ value, max, width = 80 }: { value: number; max: number; width?: number }) {
  const ratio = max > 0 ? value / max : 0
  return (
    <div style={{ background: colors.surface2, borderRadius: radius.sm, height: 8, width, overflow: "hidden" }} title={`${value.toFixed(0)} / ${max.toFixed(0)} L`}>
      <div style={{ background: fillColor(ratio), width: `${Math.min(100, ratio * 100)}%`, height: "100%", transition: "width var(--ease)" }} />
    </div>
  )
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div style={{ borderRadius: radius.lg, padding: space[4], minWidth: 160, flex: 1, background: colors.cardBg, boxShadow: colors.shadow, border: `1px solid ${colors.border}` }}>
      <div style={{ fontSize: 12, color: colors.muted }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 650, color: colors.text, marginTop: space[1], letterSpacing: "-0.01em" }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: colors.muted, marginTop: space[1] }}>{sub}</div>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div style={{ color: colors.muted, fontSize: 13, padding: `${space[2]} 0` }}>{children}</div>
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "default",
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: "default" | "primary"
}) {
  const primary = variant === "primary"
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: `${space[2]} ${space[4]}`,
        fontSize: 13,
        fontWeight: 500,
        borderRadius: radius.md,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.55 : 1,
        border: primary ? "none" : `1px solid ${colors.border}`,
        background: primary ? colors.accent : colors.cardBg,
        color: primary ? colors.accentFg : colors.text,
        boxShadow: primary ? "none" : colors.shadow,
      }}
    >
      {children}
    </button>
  )
}
