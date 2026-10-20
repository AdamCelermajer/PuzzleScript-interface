import type { Catalog, CatalogJob, CatalogRun, FrameworkOptions } from '../api/types'
import { outcome, processStatus, type Outcome, type ProcessStatus } from './status'

/** A catalog row with one normalized identity, regardless of run_spec.json vs legacy config. */
export interface RunView {
  raw: CatalogRun
  id: string
  kind: 'avo' | 'codex'
  /** Registry id (frameworks/registry.py), e.g. `baseline`, `avo`. */
  framework: string
  /** Framework plus options as shown to people, e.g. `Baseline+`. */
  variant: string
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
  /** Archived by the user; shown with the archive like legacy runs. */
  archived: boolean
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

/** The catalog names every run's framework; rows from before the frameworks package fall back to kind/condition. */
export function runIdentity(row: Pick<CatalogRun, 'framework' | 'variant' | 'kind' | 'condition'>): { framework: string; variant: string } {
  if (row.framework) return { framework: row.framework, variant: row.variant || row.framework }
  if (row.kind === 'avo') return { framework: 'avo', variant: 'AVO' }
  return { framework: 'baseline', variant: String(row.condition ?? '').startsWith('baseline-plus') ? 'Baseline+' : 'Baseline' }
}

/** `max steps 200 · notes · 4h wall` from a framework's options. */
export function optionsText(options: FrameworkOptions | null | undefined, maxWallSeconds?: number | null): string {
  const parts = Object.entries(options ?? {}).flatMap(([name, value]) => {
    const label = name.replaceAll('_', ' ')
    if (typeof value === 'boolean') return value ? [label] : []
    return [`${label} ${value}`]
  })
  const wall = maxWallSeconds === 0 ? 'unlimited wall' : maxWallSeconds ? `${Math.round((maxWallSeconds / 3600) * 10) / 10}h wall` : ''
  return [...parts, wall].filter(Boolean).join(' · ')
}

export function normalizeRun(row: CatalogRun): RunView {
  const { framework, variant } = runIdentity(row)
  const campaign = row.kind === 'avo'
  const started = (row.started_at ? row.started_at * 1000 : null) ?? batchTime(row.id) ?? batchTime(row.batch) ?? row.modified ?? 0
  return {
    raw: row,
    id: row.id,
    kind: row.kind,
    framework,
    variant,
    harness: row.harness || row.agent_backend || 'codex',
    model: row.model || '—',
    optimizerModel: row.optimizer_model ?? null,
    effort: row.effort || (row.config as { reasoning_effort?: string } | undefined)?.reasoning_effort || '—',
    game: row.game_id || '—',
    batch: row.batch || '',
    started,
    activity: row.modified || 0,
    legacy: row.spec_source !== 'run_spec',
    archived: row.archived === true,
    process: processStatus(row),
    outcome: outcome(row),
    progress: campaign
      ? { used: row.evaluated ?? null, budget: row.budget ?? numberOption(row.options, 'max_evaluations'), unit: 'evaluations' }
      : { used: row.actions ?? null, budget: row.budget ?? numberOption(row.options, 'max_steps'), unit: 'actions' },
    worldModel: campaign ? row.world_model_mode ?? null : null,
  }
}

const numberOption = (options: FrameworkOptions | null | undefined, name: string) =>
  typeof options?.[name] === 'number' ? (options[name] as number) : null

export interface RunFilters {
  variant: string
  harness: string
  model: string
  game: string
  status: string
  job: string
  q: string
}

export const EMPTY_FILTERS: RunFilters = { variant: '', harness: '', model: '', game: '', status: '', job: '', q: '' }

/** Status filter buckets: live = confirmed active process; others match the process tone. */
export function matchesFilters(run: RunView, f: RunFilters): boolean {
  if (f.variant && run.variant !== f.variant) return false
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
    const hay = `${run.id} ${run.game} ${run.model} ${run.harness} ${run.variant} ${run.optimizerModel ?? ''}`.toLowerCase()
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

/** `openrouter/qwen/qwen3.8-27b` → name `qwen3.8-27b`, provider `openrouter/qwen`; bare ids keep the name. */
export function modelParts(model: string): { name: string; provider: string } {
  const parts = model.split('/')
  if (parts.length < 2) return { name: model, provider: '' }
  return { name: parts.at(-1)!, provider: parts.slice(0, -1).join('/') }
}

export function jobLabel(job: Pick<CatalogJob, 'id'>): string {
  return job.id.split('/').at(-1) ?? job.id
}

/** Workbench-internal detail link (run ids contain slashes; they become the route splat). */
export const runHref = (id: string) => `/runs/${id.split('/').map(encodeURIComponent).join('/')}`
export const gameHref = (id: string) => `/benchmarks/${encodeURIComponent(canonicalGameId(id))}`

/** One launch (workbench batch or legacy output folder) with its runs and a spec summary. */
export interface Launch {
  id: string
  label: string
  started: number
  archive: boolean
  job?: CatalogJob
  runs: RunView[]
  variants: string[]
  harnesses: string[]
  models: string[]
  budget: string
}

/** `output/workbench/20261015T012502-nano-modality-714e64` → `nano-modality`. */
export function launchLabel(batch: string): string {
  const parts = batch.split('/').filter(Boolean)
  const name = (['output', 'campaign'].includes(parts.at(-1) ?? '') ? parts.slice(-2).join('/') : parts.at(-1)) ?? batch
  const stripped = name.replace(/^\d{8}T\d{6}Z?-?/, '').replace(/-?[0-9a-f]{8}$/, '').replace(/-?[0-9a-f]{6}$/, '')
  const time = batchTime(name)
  return stripped || (time ? `Launch · ${new Date(time).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : name)
}

function budgetSummary(run: RunView): string {
  return run.raw.options ? optionsText(run.raw.options, run.raw.max_wall_seconds) : ''
}

/**
 * Group runs by launch, newest first. A launch is archive when every run either has no
 * run_spec.json (recorded before the harness revamp) or was archived by the user.
 */
export function groupLaunches(runs: RunView[], jobs: Map<string, CatalogJob>): Launch[] {
  const groups = new Map<string, RunView[]>()
  for (const run of runs) {
    // Only real launches group runs: a workbench batch (job.json) or a `<batch>/run-NNNN` matrix folder.
    // Shared output folders (e.g. output/codex_agent) are not launches; their runs stay separate.
    const launch = run.batch && (jobs.has(run.batch) || new RegExp(`^${escapeRegExp(run.batch)}/run-\\d+`).test(run.id))
    const key = `${launch ? run.batch : run.id}|${run.legacy || run.archived ? 'a' : 'n'}`
    groups.set(key, [...(groups.get(key) ?? []), run])
  }
  const launches: Launch[] = []
  for (const [key, members] of groups) {
    const id = key.split('|')[0]
    const job = jobs.get(id)
    const ordered = [...members].sort((a, b) => a.id.localeCompare(b.id))
    const created = job?.created_at ? Date.parse(job.created_at) : NaN
    launches.push({
      id,
      label: launchLabel(id),
      started: Number.isFinite(created) ? created : Math.max(...members.map((r) => r.started || r.activity || 0)),
      archive: members.every((r) => r.legacy || r.archived),
      job,
      runs: ordered,
      variants: [...new Set(ordered.map((r) => r.variant))],
      harnesses: [...new Set(members.map((r) => r.harness))],
      models: [...new Set(members.map((r) => r.model).filter((m) => m && m !== '—'))],
      budget: budgetSummary(ordered[0]),
    })
  }
  return launches.sort((a, b) => b.started - a.started)
}

/** `modality`, `ps_modality` and `ps_modality-v1` all name `ps_modality-v1` (mirrors workbench/catalog.py). */
export function canonicalGameId(id: string): string {
  let game = id.trim()
  if (!game.startsWith('ps_')) game = `ps_${game}`
  if (!/-v\d+$/.test(game)) game += '-v1'
  return game
}

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
