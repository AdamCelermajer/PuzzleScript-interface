import type { CatalogRun } from '../api/types'

/**
 * Two independent facts per run (docs/architecture/workbench.md):
 *  - process status: what the batch worker heartbeat / Docker / artifacts say about the process;
 *  - outcome: what the solver/player recorded (solved, levels, fitness).
 * They are never merged: a "finished" process can be unsolved, a "stopped" run can have solved.
 */
export type ProcessTone = 'running' | 'queued' | 'paused' | 'finished' | 'failed' | 'stopped' | 'unconfirmed' | 'attention'

export interface ProcessStatus {
  tone: ProcessTone
  label: string
  /** True only when a fresh worker heartbeat or Docker confirms the process. */
  live: boolean
  detail: string
}

const LIVE_SOURCES = ['Batch worker heartbeat', 'Docker reports']

export function processStatus(run: Pick<CatalogRun, 'status' | 'status_source' | 'needs_assistance' | 'container'>): ProcessStatus {
  const status = run.status || 'unknown'
  const detail = run.status_source || ''
  const confirmed = Boolean(run.container) || LIVE_SOURCES.some((s) => detail.startsWith(s))
  if (run.needs_assistance) return { tone: 'attention', label: 'needs assistance', live: false, detail }
  switch (status) {
    case 'running':
    case 'starting':
      return { tone: 'running', label: status, live: confirmed, detail }
    case 'stopping':
      return { tone: 'running', label: 'stopping', live: confirmed, detail }
    case 'queued':
      return { tone: 'queued', label: 'queued', live: confirmed, detail }
    case 'paused':
      return { tone: 'paused', label: 'paused', live: false, detail }
    case 'completed':
      return { tone: 'finished', label: 'finished', live: false, detail }
    case 'failed':
      return { tone: 'failed', label: 'failed', live: false, detail }
    // "cancelled" is a manual stop by Adam (usually to save money): neutral, not an error.
    case 'cancelled':
    case 'stopped':
      return { tone: 'stopped', label: 'stopped', live: false, detail }
    case 'unconfirmed':
      return { tone: 'unconfirmed', label: 'unconfirmed', live: false, detail: detail || 'No current process confirmation' }
    default:
      return { tone: 'unconfirmed', label: status, live: false, detail }
  }
}

export const ACTIVE_STATUSES = new Set(['queued', 'starting', 'running', 'stopping'])

export function isActive(run: Pick<CatalogRun, 'status'>): boolean {
  return ACTIVE_STATUSES.has(run.status)
}

export type OutcomeTone = 'solved' | 'partial' | 'unsolved' | 'pending' | 'none'

export interface Outcome {
  tone: OutcomeTone
  label: string
  /** Levels (baseline) or fresh fitness (campaign) and the total, when known. */
  score: number | null
  total: number | null
}

const numeric = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const levelCount = (value: unknown) => (numeric(value) && value > 0 ? value : null)

/** Total levels known for a campaign: fresh evaluation, then research, then the initial observation. */
export function campaignLevels(run: CatalogRun): number | null {
  for (const e of run.result_inputs?.evaluations ?? []) {
    const total = levelCount(e.score?.environment_task?.score?.win_levels) ?? levelCount(e.score?.win_levels) ?? levelCount(e.score?.research_score?.win_levels)
    if (total) return total
  }
  const initial = (run.result_inputs?.config as { initial_observation?: { progress?: { win_levels?: unknown } } } | undefined)?.initial_observation?.progress?.win_levels
  return levelCount(initial)
}

export function outcome(run: CatalogRun): Outcome {
  const campaign = run.kind === 'avo'
  const score = campaign ? run.best_fitness ?? null : run.levels ?? null
  const total = campaign ? campaignLevels(run) : levelCount(run.recorded_win_levels)
  if (run.solved) return { tone: 'solved', label: 'solved', score, total }
  if (!numeric(score)) {
    if (isActive(run)) return { tone: 'pending', label: campaign ? 'not evaluated yet' : 'no result yet', score: null, total }
    return { tone: 'none', label: campaign ? 'not evaluated' : 'no result', score: null, total }
  }
  if (isActive(run)) return { tone: 'pending', label: 'not solved yet', score, total }
  return { tone: score > 0 ? 'partial' : 'unsolved', label: 'not solved', score, total }
}

export function scoreText(o: Pick<Outcome, 'score' | 'total'>): string {
  const score = numeric(o.score) ? String(Number(o.score.toFixed(3))) : '—'
  return `${score} / ${o.total ?? '—'}`
}
