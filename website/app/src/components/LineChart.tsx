import { useEffect, useMemo, useRef, useState } from 'react'

// Validated categorical order (dataviz reference palette; light/dark steps). Assigned by series
// index in the caller's fixed order, never cycled: series past 8 are not drawn and say so.
const LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
const DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
export const MAX_SERIES = LIGHT.length

export function seriesColor(index: number): string {
  const dark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  return (dark ? DARK : LIGHT)[index] ?? 'transparent'
}

export interface Series {
  id: string
  label: string
  points: { x: number; y: number }[]
  /** Horizontal target line (e.g. total levels). */
  target?: number | null
  /** Fixed categorical slot (defaults to the series position) so colors follow the run, not its rank. */
  color?: number
  /** Short end-of-line label (defaults to label). */
  short?: string
}

/** Step line chart (best-so-far curves) with crosshair tooltip, legend and end labels. */
export function LineChart({ series, xLabel, yLabel, height = 260, step = true, xDomain }: { series: Series[]; xLabel: string; yLabel: string; height?: number; step?: boolean; xDomain?: number }) {
  const ref = useRef<SVGSVGElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const [hoverX, setHoverX] = useState<number | null>(null)
  const [width, setWidth] = useState(760)
  useEffect(() => {
    const element = box.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(320, Math.round(entry.contentRect.width))))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const drawn = series.slice(0, MAX_SERIES)
  const pad = { left: 44, right: drawn.length <= 4 ? 110 : 16, top: 12, bottom: 34 }
  const { xMax, yMax } = useMemo(() => {
    const xs = drawn.flatMap((s) => s.points.map((p) => p.x))
    const ys = drawn.flatMap((s) => [...s.points.map((p) => p.y), s.target ?? 0])
    return { xMax: Math.max(1, xDomain ?? 0, ...xs), yMax: Math.max(1, ...ys) }
  }, [drawn, xDomain])
  const sx = (x: number) => pad.left + (x / xMax) * (width - pad.left - pad.right)
  const sy = (y: number) => pad.top + (1 - y / yMax) * (height - pad.top - pad.bottom)
  const yTicks = niceTicks(yMax)
  const xTicks = niceTicks(xMax)
  const path = (points: { x: number; y: number }[]) => {
    if (!points.length) return ''
    let d = `M${sx(points[0].x)},${sy(points[0].y)}`
    for (let i = 1; i < points.length; i++) {
      d += step ? `H${sx(points[i].x)}V${sy(points[i].y)}` : `L${sx(points[i].x)},${sy(points[i].y)}`
    }
    return d
  }
  const valueAt = (s: Series, x: number) => {
    let value: number | null = null
    for (const p of s.points) if (p.x <= x) value = p.y
    return value
  }
  const targets = [...new Set(drawn.map((s) => s.target).filter((t): t is number => typeof t === 'number' && t > 0))]

  const empty = !drawn.some((s) => s.points.length)
  return (
    <div className="flex flex-col gap-2">
      <div ref={box} className="relative">
        {empty ? <div className="flex h-32 items-center justify-center text-[12px] text-faint">No data points for these runs</div> : <>
        <svg
          ref={ref}
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          className="block"
          onMouseLeave={() => setHoverX(null)}
          onMouseMove={(event) => {
            const box = ref.current?.getBoundingClientRect()
            if (!box) return
            const px = ((event.clientX - box.left) / box.width) * width
            const x = Math.round(((px - pad.left) / (width - pad.left - pad.right)) * xMax)
            setHoverX(x < 0 || x > xMax ? null : x)
          }}
        >
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={pad.left} x2={width - pad.right} y1={sy(t)} y2={sy(t)} stroke="var(--line)" strokeWidth={1} />
              <text x={pad.left - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--faint)">{t}</text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={`x${t}`} x={sx(t)} y={height - pad.bottom + 14} textAnchor="middle" fontSize={11} fill="var(--faint)">{t}</text>
          ))}
          <text x={pad.left + (width - pad.left - pad.right) / 2} y={height - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">{xLabel}</text>
          <text x={10} y={pad.top + (height - pad.top - pad.bottom) / 2} textAnchor="middle" fontSize={11} fill="var(--muted)" transform={`rotate(-90 10 ${pad.top + (height - pad.top - pad.bottom) / 2})`}>{yLabel}</text>
          {targets.map((t) => (
            <line key={`t${t}`} x1={pad.left} x2={width - pad.right} y1={sy(t)} y2={sy(t)} stroke="var(--line-strong)" strokeDasharray="4 4" strokeWidth={1} />
          ))}
          {drawn.map((s, i) => (
            <g key={s.id}>
              <path d={path(s.points)} fill="none" stroke={seriesColor(s.color ?? i)} strokeWidth={2} strokeLinejoin="round" />
              {s.points.length <= 40 && s.points.map((p, j) => <circle key={j} cx={sx(p.x)} cy={sy(p.y)} r={3} fill={seriesColor(s.color ?? i)} stroke="var(--panel)" strokeWidth={2} />)}
              {drawn.length <= 4 && s.points.length > 0 && (
                <text x={sx(s.points.at(-1)!.x) + 6} y={sy(s.points.at(-1)!.y)} dominantBaseline="middle" fontSize={11} fill="var(--muted)">
                  {truncate(s.short ?? s.label, 18)}
                </text>
              )}
            </g>
          ))}
          {hoverX !== null && <line x1={sx(hoverX)} x2={sx(hoverX)} y1={pad.top} y2={height - pad.bottom} stroke="var(--muted)" strokeWidth={1} />}
        </svg>
        {hoverX !== null && (
          <div className="pointer-events-none absolute top-1 rounded-md border border-line bg-panel px-2 py-1 text-[11.5px] shadow-md" style={{ left: `${Math.min(70, (sx(hoverX) / width) * 100 + 2)}%` }}>
            <div className="mb-0.5 font-medium text-muted">{xLabel} {hoverX}</div>
            {drawn.map((s, i) => (
              <div key={s.id} className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: seriesColor(s.color ?? i) }} />
                <span className="max-w-56 truncate">{s.label}</span>
                <span className="ml-auto pl-3 font-mono tabular-nums">{valueAt(s, hoverX) ?? '—'}</span>
              </div>
            ))}
          </div>
        )}
        </>}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-muted">
        {drawn.map((s, i) => (
          <span key={s.id} className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-4" style={{ background: seriesColor(s.color ?? i) }} />{s.label}</span>
        ))}
        {targets.length > 0 && <span className="inline-flex items-center gap-1.5"><span className="inline-block w-4 border-t border-dashed border-line-strong" />total levels</span>}
        {series.length > MAX_SERIES && <span className="text-warn">{series.length - MAX_SERIES} more runs not drawn; see the table</span>}
      </div>
    </div>
  )
}

function niceTicks(max: number): number[] {
  const rough = max / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough || 1))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude * 10
  const ticks = []
  for (let t = 0; t <= max + 1e-9; t += step) ticks.push(Number(t.toFixed(6)))
  return ticks
}

const truncate = (text: string, n: number) => (text.length > n ? text.slice(0, n - 1) + '…' : text)
