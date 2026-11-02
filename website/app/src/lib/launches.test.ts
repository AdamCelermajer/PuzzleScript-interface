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
      run({ id: 'f/new', batch: 'f', spec_source: 'run_spec', framework: 'baseline', variant: 'Baseline', harness: 'claude-code', model: 'claude-haiku-5-5', modified: 50 }),
      run({ id: 'f/old', batch: 'f', spec_source: 'legacy', harness: 'codex', model: 'gpt-5.5', modified: 10 }),
      run({ id: 'output/workbench/20261015T012502-x-abcdef12/run-0001', batch: 'output/workbench/20261015T012502-x-abcdef12', spec_source: 'run_spec',
        kind: 'avo', framework: 'avo', variant: 'AVO', harness: 'opencode', model: 'openrouter/qwen/qwen3.8-27b', max_wall_seconds: 0,
        options: { max_evaluations: 5, research_moves: 4, solver_moves: 6, world_model_mode: 'final-only' } }),
    ].map(normalizeRun)
    const job = { id: 'output/workbench/20261015T012502-x-abcdef12', created_at: '2026-10-15T00:25:02Z' } as CatalogJob
    const launches = groupLaunches(views, new Map([[job.id, job]]))
    // A shared output folder is not a launch: its runs stay separate rows.
    expect(launches.map((l) => [l.id, l.archive, l.runs.length])).toEqual([
      ['output/workbench/20261015T012502-x-abcdef12', false, 1],
      ['f/new', false, 1],
      ['f/old', true, 1],
    ])
    const campaign = launches[0]
    expect(campaign).toMatchObject({ label: 'x', variants: ['AVO'], harnesses: ['opencode'],
      budget: 'max evaluations 5 · research moves 4 · solver moves 6 · world model mode final-only · unlimited wall' })
    expect(campaign.job).toBe(job)
  })
})

describe('launch groups', () => {
  it('groups a <batch>/run-NNNN matrix folder even without job.json', () => {
    const views = ['run-0001/campaign', 'run-0002/campaign'].map((r) => normalizeRun(run({ id: `output/avo-six/${r}`, batch: 'output/avo-six', kind: 'avo' })))
    const launches = groupLaunches(views, new Map())
    expect(launches.map((l) => [l.id, l.runs.length, l.archive])).toEqual([['output/avo-six', 2, true]])
  })
})

describe('results matrix header', () => {
  it('groups consecutive columns by harness', () => {
    const columns = [['codex', 'a'], ['codex', 'b'], ['opencode', 'c'], ['codex', 'd']].map(([harness, model]) => ({ harness, model, label: model, runs: 1 }))
    expect(harnessGroups(columns)).toEqual([{ harness: 'codex', span: 2 }, { harness: 'opencode', span: 1 }, { harness: 'codex', span: 1 }])
  })
})

describe('user archive', () => {
  it('moves an archived run of a launch into its own archive group', () => {
    const batch = 'output/workbench/20261020T104612-x-abcdef12'
    const views = [
      run({ id: `${batch}/run-0001`, batch, spec_source: 'run_spec', framework: 'baseline', archived: true }),
      run({ id: `${batch}/run-0002`, batch, spec_source: 'run_spec', framework: 'baseline' }),
    ].map(normalizeRun)
    const launches = groupLaunches(views, new Map())
    const ids = (archive: boolean) => launches.filter((l) => l.archive === archive).flatMap((l) => l.runs.map((r) => r.id.slice(-8)))
    expect([ids(true), ids(false)]).toEqual([['run-0001'], ['run-0002']])
  })
})
