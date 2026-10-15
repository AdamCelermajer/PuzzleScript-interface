import { useEffect, useRef } from 'react'
import { cx } from './ui'

// Palette for anonymous visible-cell IDs (same first 16 as the old run-detail page).
const COLORS = ['#111820', '#2962a8', '#d13e35', '#2f9d62', '#e2b53f', '#7e8790', '#c85aa1', '#ef8d32', '#56b9c9', '#754b33', '#d7dde1', '#8fb1db', '#ef938b', '#8bd0a7', '#f4d978', '#ffffff']
const colorFor = (id: number) => COLORS[id] ?? `hsl(${(id * 137.508) % 360} 55% 40%)`

/** Last 2-D layer of an ARC frame (frames are `[layer][row][col]` or `[row][col]`). */
export function toGrid(frame: unknown): number[][] | null {
  if (!Array.isArray(frame) || !frame.length) return null
  if (Array.isArray(frame[0]) && Array.isArray((frame[0] as unknown[])[0])) return frame[frame.length - 1] as number[][]
  if (Array.isArray(frame[0])) return frame as number[][]
  return null
}

/** Grid of cell IDs drawn as colored tiles with the ID printed; highlighted cells get an outline. */
export function GridCanvas({ grid, highlight, maxSize = 420, showIds = true, className }: {
  grid: number[][] | null | undefined
  highlight?: { row: number; col: number }[]
  maxSize?: number
  showIds?: boolean
  className?: string
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !grid?.length) return
    const rows = grid.length
    const cols = Math.max(...grid.map((r) => r.length))
    const cell = Math.max(6, Math.min(40, Math.floor(maxSize / Math.max(rows, cols))))
    canvas.width = cols * cell
    canvas.height = rows * cell
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.font = `${Math.max(8, Math.floor(cell / 3))}px monospace`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    grid.forEach((row, y) =>
      row.forEach((id, x) => {
        ctx.fillStyle = colorFor(id)
        ctx.fillRect(x * cell, y * cell, cell, cell)
        if (showIds && cell >= 16) {
          ctx.fillStyle = '#000a'
          ctx.fillRect(x * cell + 1, y * cell + cell / 2 - 7, cell - 2, 14)
          ctx.fillStyle = '#fff'
          ctx.fillText(String(id), x * cell + cell / 2, y * cell + cell / 2)
        }
      }),
    )
    ctx.lineWidth = 2
    ctx.strokeStyle = '#ff2fd6'
    for (const h of highlight ?? []) ctx.strokeRect(h.col * cell + 1, h.row * cell + 1, cell - 2, cell - 2)
  }, [grid, highlight, maxSize, showIds])
  if (!grid?.length) return <div className="flex h-40 items-center justify-center rounded-md bg-sunken text-[12px] text-faint">No grid recorded</div>
  return <canvas ref={ref} className={cx('pixelated max-w-full rounded-sm', className)} />
}

/** A rendered PNG frame scaled up without smoothing. */
export function PixelImage({ src, alt, className, onError }: { src: string; alt: string; className?: string; onError?: () => void }) {
  return <img src={src} alt={alt} onError={onError} className={cx('pixelated h-auto max-w-full rounded-sm bg-black', className)} style={{ minWidth: 240 }} />
}
