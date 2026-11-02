import { describe, expect, it } from 'vitest'
import type { CatalogJob, CatalogRun } from '../api/types'
import { EMPTY_FILTERS, batchTime, campaignScore, matchesFilters, normalizeRun, optionsText, runHref, runIdentity, runningNow } from './runs'

describe('runIdentity', () => {
  it('prefers the catalog framework and variant', () => {
    expect(runIdentity({ framework: 'baseline', variant: 'Baseline · agent', kind: 'avo', condition: null })).toEqual({ framework: 'baseline', variant: 'Baseline · agent' })
    expect(runIdentity({ framework: 'avo', variant: 'AVO · research score', kind: 'avo', condition: null }).variant).toBe('AVO · research score')
  })
  it('falls back to kind and the legacy condition', () => {
    expect(runIdentity({ framework: null, kind: 'avo', condition: null })).toEqual({ framework: 'avo', variant: 'AVO · solver score' })
    expect(runIdentity({ kind: 'codex', condition: 'baseline-plus-plus' }).variant).toBe('Baseline')
    expect(runIdentity({ kind: 'codex', condition: 'baseline' }).variant).toBe('Baseline · no notes (old)')
  })
  it('describes options generically', () => {
    expect(optionsText({ max_steps: 200, notes: true }, 0)).toBe('max steps 200 · notes · unlimited wall')
    expect(optionsText({ notes: false }, 5400)).toBe('1.5h wall')
  })
  it('names what scores an AVO campaign; archived campaigns were scored by their solver', () => {
    expect(campaignScore({ world_model_mode: 'final-only' })).toBe('research levels')
    expect(campaignScore({ solver_moves: 400, fitness: 'research' })).toBe('research levels')
    expect(campaignScore({ solver_moves: 400, fitness: 'solver' })).toBe('solver levels')
    expect(campaignScore({ solver_moves: 400 })).toBe('solver levels')
    expect(campaignScore(null)).toBe('solver levels')
  })
})

describe('normalizeRun', () => {
  const legacy: CatalogRun = {
    id: 'output/workbench/20261015T012502-label-abcd/run-0001', kind: 'codex', batch: 'output/workbench/20261015T012502-label-abcd',
    agent_backend: 'codex', model: 'gpt-5.5', status: 'cancelled', actions: 386, budget: 1000, condition: 'baseline-plus', game_id: 'ps_modality-v1',
    modified: 1, levels: 1, recorded_win_levels: 4,
  }

  it('normalizes a legacy row (no run_spec.json)', () => {
    const view = normalizeRun(legacy)
    expect(view).toMatchObject({ framework: 'baseline', variant: 'Baseline', harness: 'codex', legacy: true, game: 'ps_modality-v1' })
    expect(view.progress).toEqual({ used: 386, budget: 1000, unit: 'actions' })
    expect(view.process.tone).toBe('stopped')
  })

  it('reads the launch time from the batch folder name', () => {
    expect(normalizeRun(legacy).started).toBe(new Date(2026, 9, 15, 1, 25, 2).getTime())
    expect(batchTime('output/workbench/20260914T142104Z-x')).toBe(Date.UTC(2026, 8, 14, 14, 21, 4))
    expect(batchTime('output/codex_agent/foo')).toBeNull()
  })

  it('uses run_spec identity and campaign progress for new runs', () => {
    const view = normalizeRun({ id: 'a/campaign', kind: 'avo', status: 'running', status_source: 'Batch worker heartbeat', framework: 'avo',
      variant: 'AVO', harness: 'opencode', spec_source: 'run_spec', model: 'openrouter/qwen/qwen3.8-27b', evaluated: 2, options: { max_evaluations: 8 } })
    expect(view).toMatchObject({ framework: 'avo', variant: 'AVO', harness: 'opencode', legacy: false })
    expect(view.progress).toEqual({ used: 2, budget: 8, unit: 'evaluations' })
    expect(view.process.live).toBe(true)
  })

  it('filters by status bucket, job and free text', () => {
    const view = normalizeRun(legacy)
    expect(matchesFilters(view, { ...EMPTY_FILTERS, status: 'stopped' })).toBe(true)
    expect(matchesFilters(view, { ...EMPTY_FILTERS, status: 'failed' })).toBe(false)
    expect(matchesFilters(view, { ...EMPTY_FILTERS, job: legacy.batch! })).toBe(true)
    expect(matchesFilters(view, { ...EMPTY_FILTERS, q: 'MODALITY' })).toBe(true)
  })

  it('keeps every status under "any"; "active" keeps running and queued runs', () => {
    const stopped = normalizeRun(legacy)
    const queued = normalizeRun({ ...legacy, status: 'queued' })
    expect(matchesFilters(stopped, { ...EMPTY_FILTERS, status: 'any' })).toBe(true)
    expect(matchesFilters(stopped, { ...EMPTY_FILTERS, status: 'active' })).toBe(false)
    expect(matchesFilters(queued, { ...EMPTY_FILTERS, status: 'active' })).toBe(true)
  })

  it('keeps slashes in run links as route segments', () => {
    expect(runHref('output/a b/campaign')).toBe('/runs/output/a%20b/campaign')
  })
})

describe('runningNow', () => {
  const batch = 'output/workbench/20261021T144507-vast-fp8-baseline-avo-a08335e1'
  const run = (n: number, status: string, extra: Partial<CatalogRun> = {}) =>
    normalizeRun({ id: `${batch}/run-000${n}`, kind: 'codex', batch, status, status_source: 'Batch worker heartbeat', ...extra })
  const jobs = [{ id: batch, status: 'running' }, { id: 'output/workbench/old', status: 'completed' }] as CatalogJob[]

  it('splits a live batch into active and failed or stopped runs; finished runs are in neither', () => {
    const runs = [run(1, 'running'), run(2, 'queued'), run(3, 'failed'), run(4, 'cancelled'), run(5, 'completed'), run(6, 'stopping')]
    const now = runningNow(runs, jobs)
    expect(now.active.map((r) => r.id.at(-1))).toEqual(['1', '2', '6'])
    expect(now.ended.map((r) => r.id.at(-1))).toEqual(['3', '4'])
  })

  it('leaves out batches that are not live, but keeps a confirmed running run outside a batch', () => {
    const old = normalizeRun({ id: 'output/workbench/old/run-0001', kind: 'codex', batch: 'output/workbench/old', status: 'failed' })
    const loose = normalizeRun({ id: 'output/codex_agent/x', kind: 'codex', status: 'running', container: 'ps-agent-1' })
    const now = runningNow([old, loose], jobs)
    expect(now.active.map((r) => r.id)).toEqual(['output/codex_agent/x'])
    expect(now.ended).toEqual([])
  })
})
