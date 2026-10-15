import { describe, expect, it } from 'vitest'
import type { CatalogJob, CatalogRun } from '../api/types'
import { groupLaunches, launchLabel, normalizeRun } from './runs'
import { harnessGroups } from '../views/Results'

const run = (over: Partial<CatalogRun>): CatalogRun => ({ id: 'x', kind: 'codex', status: 'completed', has_result: true, ...over })

describe('launch grouping', () => {
  it('labels workbench batches without timestamp and hash', () => {
    expect(launchLabel('output/workbench/20261015T012502-nano-modality-baseline-plus-714e64')).toBe('nano-modality-baseline-plus')
    expect(launchLabel('studies/codex_agent/output')).toBe('codex_agent/output')
    expect(launchLabel('output/workbench/20260924T010548-df1831ea')).toMatch(/^Launch · /)
  })

  it('keeps new and archive runs of one folder in separate launches, newest first', () => {
    const views = [
      run({ id: 'f/new', batch: 'f', spec_source: 'run_spec', mode: 'baseline-plus', harness: 'claude-code', model: 'claude-haiku-5-5', modified: 50 }),
      run({ id: 'f/old', batch: 'f', spec_source: 'legacy', harness: 'codex', model: 'gpt-5.5', modified: 10 }),
      run({ id: 'output/workbench/20261015T012502-x-abcdef12/run-0001', batch: 'output/workbench/20261015T012502-x-abcdef12', spec_source: 'run_spec',
        kind: 'avo', mode: 'campaign', harness: 'opencode', model: 'openrouter/qwen/qwen3.8-27b', run_budget: { max_wall_seconds: 0, max_evaluations: 5, research_moves: 4, solver_moves: 6 } }),
    ].map(normalizeRun)
    const job = { id: 'output/workbench/20261015T012502-x-abcdef12', created_at: '2026-10-15T00:25:02Z' } as CatalogJob
    const launches = groupLaunches(views, new Map([[job.id, job]]))
    expect(launches.map((l) => [l.id, l.archive, l.runs.length])).toEqual([
      ['output/workbench/20261015T012502-x-abcdef12', false, 1],
      ['f', false, 1],
      ['f', true, 1],
    ])
    const campaign = launches[0]
    expect(campaign).toMatchObject({ label: 'x', modes: ['campaign'], harnesses: ['opencode'], budget: '5 evals · 4/6 moves · unlimited wall' })
    expect(campaign.job).toBe(job)
  })
})

describe('results matrix header', () => {
  it('groups consecutive columns by harness', () => {
    const columns = [['codex', 'a'], ['codex', 'b'], ['opencode', 'c'], ['codex', 'd']].map(([harness, model]) => ({ harness, model, label: model, runs: 1 }))
    expect(harnessGroups(columns)).toEqual([{ harness: 'codex', span: 2 }, { harness: 'opencode', span: 1 }, { harness: 'codex', span: 1 }])
  })
})
