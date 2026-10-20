import { unitLabel, type RunView } from '../lib/runs'
import type { Outcome, ProcessStatus } from '../lib/status'
import { LevelPips, StatusDot } from './identity'

/** Process status: dot + word (process liveness is distinct from solver success). */
export function ProcessPill({ status }: { status: ProcessStatus }) {
  return <StatusDot status={status} />
}

/** Solver outcome: level pips (filled = solved levels), the headline of every run. */
export function OutcomeCell({ outcome, size = 'md' }: { outcome: Outcome; campaign?: boolean; size?: 'sm' | 'md' | 'lg' }) {
  if (outcome.score === null && !outcome.total) return <span className="text-[12px] text-faint">{outcome.label}</span>
  return <LevelPips levels={outcome.score} total={outcome.total} solved={outcome.tone === 'solved'} size={size} />
}

export function ProgressText({ run }: { run: RunView }) {
  const { used, budget, unit } = run.progress
  if (used === null && budget === null) return <span className="text-faint">–</span>
  return (
    <span className="whitespace-nowrap text-[12px] tabular-nums text-muted" title={run.progress.detail ?? unit}>
      {used ?? '–'}
      {budget ? <span className="text-faint">/{budget}</span> : ''} <span className="text-[11px] text-faint">{unitLabel(unit)}</span>{run.progress.detail ? <span className="text-[11px] text-faint"> · {run.progress.detail}</span> : null}
    </span>
  )
}

/** Thin progress bar for used/budget. */
export function ProgressBar({ used, budget, tone = 'run' }: { used: number | null; budget: number | null; tone?: 'run' | 'muted' }) {
  const ratio = used !== null && budget ? Math.min(1, used / budget) : 0
  return (
    <span className="relative inline-block h-1 w-full overflow-hidden rounded-full bg-[var(--pip-empty)]">
      <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${ratio * 100}%`, background: tone === 'run' ? 'var(--run)' : 'var(--faint)' }} />
    </span>
  )
}
