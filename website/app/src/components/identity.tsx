import { useState, type ReactNode } from 'react'
import type { ProcessStatus } from '../lib/status'
import { canonicalGameId } from '../lib/runs'
import { cx } from './ui'

// ---- harness identity: the only categorical color in the app (validated palette, labels always shown)

const HARNESS_VAR: Record<string, string> = {
  codex: 'var(--h-codex)',
  'claude-code': 'var(--h-claude-code)',
  opencode: 'var(--h-opencode)',
  'opencode-lean': 'var(--h-opencode)',
  antigravity: 'var(--h-antigravity)',
  bare: 'var(--h-bare)',
}

export const HARNESS_LABEL: Record<string, string> = {
  codex: 'Codex',
  'claude-code': 'Claude Code',
  opencode: 'OpenCode',
  'opencode-lean': 'OpenCode lean',
  antigravity: 'Antigravity',
  bare: 'Bare loop',
}

export const harnessColor = (harness: string | null | undefined) => HARNESS_VAR[harness ?? ''] ?? 'var(--h-legacy)'
export const harnessLabel = (harness: string | null | undefined) => HARNESS_LABEL[harness ?? ''] ?? (harness || 'unknown')

export function HarnessChip({ harness, legacy, className }: { harness: string | null | undefined; legacy?: boolean; className?: string }) {
  const color = legacy ? 'var(--h-legacy)' : harnessColor(harness)
  return (
    <span
      title={legacy ? `${harness} (recorded before the harness revamp)` : harness ?? ''}
      className={cx('inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-1.5 py-px text-[11.5px] font-medium whitespace-nowrap text-muted', className)}
    >
      <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: color }} />
      {harnessLabel(harness)}
      {legacy && <span className="text-faint">· legacy</span>}
    </span>
  )
}

// ---- level pips: the headline number of every run

/** ●●○○ for small level counts, a slim bar beyond 12 levels. Filled = levels solved. */
export function LevelPips({ levels, total, solved, size = 'md', showNumber = true }: {
  levels: number | null | undefined
  total: number | null | undefined
  solved?: boolean
  size?: 'sm' | 'md' | 'lg'
  showNumber?: boolean
}) {
  const known = typeof levels === 'number'
  const count = known ? Math.max(0, Math.round(levels)) : 0
  const max = total && total > 0 ? total : null
  const full = solved || (max !== null && count >= max)
  const fill = full ? 'var(--pip-solved)' : 'var(--pip)'
  const dot = size === 'lg' ? 10 : size === 'sm' ? 6 : 8
  const number = (
    <span className={cx('tabular-nums', size === 'lg' ? 'text-[15px] font-semibold' : 'text-[12.5px] font-semibold', !known && 'text-faint font-normal')}>
      {known ? count : '–'}
      <span className="font-normal text-faint">/{max ?? '?'}</span>
    </span>
  )
  if (!max && !known) return <span className="text-[12px] text-faint">–</span>
  if (!max) return showNumber ? number : <span className="text-faint">–</span>
  return (
    <span className="inline-flex items-center gap-2" title={known ? `${count} of ${max} levels${full ? ' · solved' : ''}` : `not evaluated · ${max} levels`}>
      {max <= 12 ? (
        <span className="inline-flex items-center" style={{ gap: size === 'lg' ? 4 : 3 }}>
          {Array.from({ length: max }, (_, i) => (
            <span
              key={i}
              className="inline-block rounded-full"
              style={{ width: dot, height: dot, background: i < count ? fill : 'transparent', boxShadow: i < count ? 'none' : 'inset 0 0 0 1.5px var(--pip-empty)' }}
            />
          ))}
        </span>
      ) : (
        <span className="relative inline-block h-1.5 overflow-hidden rounded-full" style={{ width: size === 'lg' ? 96 : 56, background: 'var(--pip-empty)' }}>
          <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.min(100, (count / max) * 100)}%`, background: fill }} />
        </span>
      )}
      {showNumber && number}
    </span>
  )
}

// ---- status: a dot and a word, never a loud pill

const DOT: Record<string, string> = {
  running: 'bg-run',
  queued: 'border border-faint bg-transparent',
  paused: 'bg-warn',
  finished: 'bg-faint',
  failed: 'bg-bad',
  stopped: 'bg-line-strong',
  unconfirmed: 'border border-dashed border-faint bg-transparent',
  attention: 'bg-warn',
}

export function StatusDot({ status, className }: { status: ProcessStatus; className?: string }) {
  const title = [status.detail, status.tone === 'running' ? (status.live ? 'confirmed live' : 'not confirmed by a fresh heartbeat or Docker') : ''].filter(Boolean).join(' · ')
  return (
    <span title={title} className={cx('inline-flex items-center gap-1.5 text-[12px] whitespace-nowrap', status.tone === 'failed' ? 'text-bad' : status.tone === 'running' ? 'text-fg' : 'text-muted', className)}>
      <span className={cx('inline-block h-2 w-2 shrink-0 rounded-full', DOT[status.tone] ?? 'bg-faint', status.tone === 'running' && status.live && 'pulse-dot')} />
      {status.label}
    </span>
  )
}

// ---- game thumbnails (first frame of level 1, cached server side)

export const thumbnailUrl = (gameId: string) => `/api/workbench/benchmarks/${encodeURIComponent(canonicalGameId(gameId))}/thumbnail.png`

export function GameThumb({ gameId, size = 32, className, rounded = 'rounded-md', aspect }: { gameId: string | null | undefined; size?: number; className?: string; rounded?: string; aspect?: string }) {
  const [failed, setFailed] = useState(false)
  const style = aspect ? { width: '100%', aspectRatio: aspect } : { width: size, height: size }
  if (!gameId || gameId === '—' || failed) {
    return (
      <span className={cx('grid shrink-0 place-items-center bg-[var(--thumb-bg)]', rounded, className)} style={style} aria-hidden>
        <span className="grid grid-cols-2 gap-[2px] opacity-40">
          <span className="h-1.5 w-1.5 bg-faint" /><span className="h-1.5 w-1.5" /><span className="h-1.5 w-1.5" /><span className="h-1.5 w-1.5 bg-faint" />
        </span>
      </span>
    )
  }
  return (
    <img
      src={thumbnailUrl(gameId)}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className={cx('pixelated shrink-0 bg-[var(--thumb-bg)] object-cover outline outline-1 -outline-offset-1 outline-[var(--line)]', rounded, className)}
      style={style}
    />
  )
}

// ---- small helpers

export function SectionLabel({ children, right, className }: { children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={cx('flex items-center justify-between gap-3', className)}>
      <span className="section-label">{children}</span>
      {right}
    </div>
  )
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      title={`${label}: ${text}`}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        navigator.clipboard?.writeText(text).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1200) })
      }}
      className="inline-grid h-5 w-5 shrink-0 place-items-center rounded text-faint hover:bg-hover hover:text-fg"
    >
      {done ? (
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 8.5 6.5 12 13 4.5" /></svg>
      ) : (
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" /><path d="M10.5 5V3.5A1.5 1.5 0 0 0 9 2H3.5A1.5 1.5 0 0 0 2 3.5V9a1.5 1.5 0 0 0 1.5 1.5H5" /></svg>
      )}
    </button>
  )
}

/** Monospace, truncated, secondary run id with a copy button. */
export function RunId({ id, className }: { id: string; className?: string }) {
  const short = id.replace(/\/campaign$/, '').split('/').slice(-2).join('/')
  return (
    <span className={cx('inline-flex min-w-0 items-center gap-0.5', className)}>
      <span className="truncate font-mono text-[11px] text-faint" title={id}>{short}</span>
      <CopyButton text={id} label="Copy run id" />
    </span>
  )
}

export function TierBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier) return null
  const bars = tier === 'easy' ? 1 : tier === 'medium' ? 2 : 3
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted" title={`${tier} tier`}>
      <span className="inline-flex items-end gap-[2px]">
        {[1, 2, 3].map((i) => <span key={i} className={cx('w-[3px] rounded-[1px]', i <= bars ? 'bg-muted' : 'bg-line-strong')} style={{ height: 3 + i * 2 }} />)}
      </span>
      {tier}
    </span>
  )
}
