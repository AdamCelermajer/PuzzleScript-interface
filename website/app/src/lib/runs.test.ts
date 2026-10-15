import { describe, expect, it } from 'vitest'
import type { CatalogRun } from '../api/types'
import { EMPTY_FILTERS, batchTime, matchesFilters, normalizeMode, normalizeRun, runHref } from './runs'

describe('normalizeMode', () => {
  it('prefers the run_spec mode', () => {
    expect(normalizeMode({ mode: 'baseline', kind: 'avo', condition: null })).toBe('baseline')
  })
  it('falls back to kind and the legacy condition', () => {
    expect(normalizeMode({ mode: null, kind: 'avo', condition: null })).toBe('campaign')
    expect(normalizeMode({ mode: null, kind: 'codex', condition: 'baseline-plus-plus' })).toBe('baseline-plus')
    expect(normalizeMode({ mode: undefined, kind: 'codex', condition: 'baseline' })).toBe('baseline')
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
    expect(view).toMatchObject({ mode: 'baseline-plus', harness: 'codex', legacy: true, game: 'ps_modality-v1' })
    expect(view.progress).toEqual({ used: 386, budget: 1000, unit: 'actions' })
    expect(view.process.tone).toBe('stopped')
  })

  it('reads the launch time from the batch folder name', () => {
    expect(normalizeRun(legacy).started).toBe(new Date(2026, 9, 15, 1, 25, 2).getTime())
    expect(batchTime('output/workbench/20260914T142104Z-x')).toBe(Date.UTC(2026, 8, 14, 14, 21, 4))
    expect(batchTime('output/codex_agent/foo')).toBeNull()
  })

  it('uses run_spec identity and campaign progress for new runs', () => {
    const view = normalizeRun({ id: 'a/campaign', kind: 'avo', status: 'running', status_source: 'Batch worker heartbeat', mode: 'campaign',
      harness: 'opencode', spec_source: 'run_spec', model: 'openrouter/qwen/qwen3.8-27b', evaluated: 2, run_budget: { max_evaluations: 8 } })
    expect(view).toMatchObject({ mode: 'campaign', harness: 'opencode', legacy: false })
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
