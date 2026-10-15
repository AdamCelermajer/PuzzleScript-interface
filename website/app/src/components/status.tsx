import type { RunView } from '../lib/runs'
import { scoreText, type Outcome, type ProcessStatus } from '../lib/status'
import { Pill } from './ui'

export function ProcessPill({ status }: { status: ProcessStatus }) {
  const title = [status.detail, status.live ? 'Confirmed live' : status.tone === 'running' ? 'Not confirmed by a fresh heartbeat or Docker' : '']
    .filter(Boolean)
    .join(' · ')
  return (
    <Pill tone={status.tone} title={title} dot={status.tone === 'running' && status.live}>
      {status.label}
    </Pill>
  )
}

export function OutcomeCell({ outcome, campaign }: { outcome: Outcome; campaign: boolean }) {
  const hasScore = outcome.score !== null
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      {hasScore && (
        <span className="text-[12.5px] font-medium tabular-nums" title={campaign ? 'Best fresh-solver fitness / levels' : 'Levels completed / levels'}>
          {scoreText(outcome)}
        </span>
      )}
      {outcome.tone === 'solved' ? (
        <Pill tone="solved">solved</Pill>
      ) : !hasScore ? (
        <span className="text-[12px] text-faint">{outcome.label}</span>
      ) : null}
    </span>
  )
}

export function ProgressText({ run }: { run: RunView }) {
  const { used, budget, unit } = run.progress
  if (used === null && budget === null) return <span className="text-faint">—</span>
  return (
    <span className="whitespace-nowrap text-[12.5px] tabular-nums text-muted" title={unit}>
      {used ?? '—'}
      {budget ? ` / ${budget}` : ''} <span className="text-[11px] text-faint">{unit === 'actions' ? 'actions' : 'evals'}</span>
    </span>
  )
}
