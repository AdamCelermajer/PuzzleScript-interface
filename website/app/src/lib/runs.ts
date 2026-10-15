import type { Catalog, CatalogJob, CatalogRun, Mode } from '../api/types'
import { outcome, processStatus, type Outcome, type ProcessStatus } from './status'

export const MODES: Mode[] = ['baseline', 'baseline-plus', 'campaign']
export const MODE_LABEL: Record<string, string> = { baseline: 'Baseline', 'baseline-plus': 'Baseline+', campaign: 'Campaign' }

/** A catalog row with one normalized identity, regardless of run_spec.json vs legacy config. */
export interface RunView {
  raw: CatalogRun
  id: string
  kind: 'avo' | 'codex'
  mode: Mode
  harness: string
  model: string
  optimizerModel: string | null
  effort: string
  game: string
  batch: string
  /** Launch time (ms) when known, else last activity. */
  started: number
  activity: number
  legacy: boolean
  process: ProcessStatus
  outcome: Outcome
  progress: { used: number | null; budget: number | null; unit: 'actions' | 'evaluations' }
  worldModel: string | null
}

/** `20261015T012502-label-abcd` → epoch ms (local time, as the launcher wrote it). */
export function batchTime(batch: string | undefined): number | null {
  const match = /(?:^|\/)(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)/.exec(batch ?? '')
  if (!match) return null
  const [, y, mo, d, h, mi, s, z] = match
  const parts = [Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s)] as const
  return z ? Date.UTC(...parts) : new Date(...parts).getTime()
}

export function normalizeMode(row: Pick<CatalogRun, 'mode' | 'kind' | 'condition'>): Mode {
  if (row.mode === 'baseline' || row.mode === 'baseline-plus' || row.mode === 'campaign') return row.mode
  if (row.kind === 'avo') return 'campaign'
  return String(row.condition ?? '').startsWith('baseline-plus') ? 'baseline-plus' : 'baseline'
}

export function normalizeRun(row: CatalogRun): RunView {
  const mode = normalizeMode(row)
  const campaign = row.kind === 'avo'
  const started = (row.started_at ? row.started_at * 1000 : null) ?? batchTime(row.id) ?? batchTime(row.batch) ?? row.modified ?? 0
  return {
    raw: row,
    id: row.id,
    kind: row.kind,
    mode,
    harness: row.harness || row.agent_backend || 'codex',
    model: row.model || '—',
    optimizerModel: campaign ? row.optimizer_model ?? null : null,
    effort: row.effort || (row.config as { reasoning_effort?: string } | undefined)?.reasoning_effort || '—',
    game: row.game_id || '—',
    batch: row.batch || '',
    started,
    activity: row.modified || 0,
    legacy: row.spec_source !== 'run_spec',
    process: processStatus(row),
    outcome: outcome(row),
    progress: campaign
      ? { used: row.evaluated ?? null, budget: row.budget ?? row.run_budget?.max_evaluations ?? null, unit: 'evaluations' }
      : { used: row.actions ?? null, budget: row.budget ?? row.run_budget?.max_steps ?? null, unit: 'actions' },
    worldModel: campaign ? row.world_model_mode ?? null : null,
  }
}

export interface RunFilters {
  mode: string
  harness: string
  model: string
  game: string
  status: string
  job: string
  q: string
}

export const EMPTY_FILTERS: RunFilters = { mode: '', harness: '', model: '', game: '', status: '', job: '', q: '' }

/** Status filter buckets: live = confirmed active process; others match the process tone. */
export function matchesFilters(run: RunView, f: RunFilters): boolean {
  if (f.mode && run.mode !== f.mode) return false
  if (f.harness && run.harness !== f.harness) return false
  if (f.model && run.model !== f.model) return false
  if (f.game && run.game !== f.game) return false
  if (f.job && run.batch !== f.job) return false
  if (f.status) {
    if (f.status === 'active') {
      if (!['running', 'queued'].includes(run.process.tone)) return false
    } else if (f.status === 'solved') {
      if (run.outcome.tone !== 'solved') return false
    } else if (run.process.tone !== f.status) return false
  }
  if (f.q) {
    const needle = f.q.toLowerCase()
    const hay = `${run.id} ${run.game} ${run.model} ${run.harness} ${run.mode} ${run.optimizerModel ?? ''}`.toLowerCase()
    if (!hay.includes(needle)) return false
  }
  return true
}

export function catalogViews(catalog: Catalog | undefined): RunView[] {
  if (!catalog) return []
  return catalog.runs.map(normalizeRun).sort((a, b) => {
    const live = Number(b.process.tone === 'running') - Number(a.process.tone === 'running')
    return live || b.started - a.started || b.activity - a.activity
  })
}

export function distinct(runs: RunView[], key: (r: RunView) => string): string[] {
  return [...new Set(runs.map(key).filter((v) => v && v !== '—'))].sort((a, b) => a.localeCompare(b))
}

export function jobLabel(job: Pick<CatalogJob, 'id'>): string {
  return job.id.split('/').at(-1) ?? job.id
}

/** Workbench-internal detail link (run ids contain slashes; they become the route splat). */
export const runHref = (id: string) => `/runs/${id.split('/').map(encodeURIComponent).join('/')}`
export const gameHref = (id: string) => `/benchmarks/${encodeURIComponent(id)}`
