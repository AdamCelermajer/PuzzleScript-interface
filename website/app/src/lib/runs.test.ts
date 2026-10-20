import { describe, expect, it } from 'vitest'
import type { CatalogRun } from '../api/types'
import { EMPTY_FILTERS, batchTime, matchesFilters, normalizeRun, optionsText, runHref, runIdentity } from './runs'

describe('runIdentity', () => {
  it('prefers the catalog framework and variant', () => {
    expect(runIdentity({ framework: 'baseline', variant: 'Baseline+', kind: 'avo', condition: null })).toEqual({ framework: 'baseline', variant: 'Baseline+' })
  })
  it('falls back to kind and the legacy condition', () => {
    expect(runIdentity({ framework: null, kind: 'avo', condition: null })).toEqual({ framework: 'avo', variant: 'AVO' })
    expect(runIdentity({ kind: 'codex', condition: 'baseline-plus-plus' }).variant).toBe('Baseline+')
    expect(runIdentity({ kind: 'codex', condition: 'baseline' }).variant).toBe('Baseline')
  })
  it('describes options generically', () => {
    expect(optionsText({ max_steps: 200, notes: true }, 0)).toBe('max steps 200 · notes · unlimited wall')
    expect(optionsText({ notes: false }, 5400)).toBe('1.5h wall')
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
    expect(view).toMatchObject({ framework: 'baseline', variant: 'Baseline+', harness: 'codex', legacy: true, game: 'ps_modality-v1' })
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

  it('keeps slashes in run links as route segments', () => {
    expect(runHref('output/a b/campaign')).toBe('/runs/output/a%20b/campaign')
  })
})
