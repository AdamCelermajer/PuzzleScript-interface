import { describe, expect, it } from 'vitest'
import type { CatalogRun } from '../api/types'
import { outcome, processStatus, scoreText } from './status'

const run = (over: Partial<CatalogRun>): CatalogRun => ({ id: 'output/x', kind: 'codex', status: 'completed', ...over })

describe('processStatus', () => {
  it('renders a manual stop (cancelled) as neutral "stopped", not failed', () => {
    const s = processStatus({ status: 'cancelled', status_source: 'Saved batch record' })
    expect(s).toMatchObject({ tone: 'stopped', label: 'stopped', live: false })
  })

  it('confirms liveness only from a fresh heartbeat or Docker', () => {
    expect(processStatus({ status: 'running', status_source: 'Batch worker heartbeat' }).live).toBe(true)
    expect(processStatus({ status: 'running', status_source: 'Docker reports the campaign container running' }).live).toBe(true)
    expect(processStatus({ status: 'running', status_source: 'Saved batch record' }).live).toBe(false)
  })

  it('keeps unconfirmed archives out of running', () => {
    expect(processStatus({ status: 'unconfirmed' }).tone).toBe('unconfirmed')
  })

  it('flags needs-assistance runs regardless of status', () => {
    expect(processStatus({ status: 'failed', needs_assistance: true }).tone).toBe('attention')
  })

  it('maps completed to finished and failed to failed', () => {
    expect(processStatus({ status: 'completed' }).label).toBe('finished')
    expect(processStatus({ status: 'failed' }).tone).toBe('failed')
  })
})

describe('outcome', () => {
  it('keeps solver success separate from process status', () => {
    const o = outcome(run({ status: 'cancelled', solved: true, levels: 4, recorded_win_levels: 4 }))
    expect(o.tone).toBe('solved')
    expect(processStatus({ status: 'cancelled' }).tone).toBe('stopped')
  })

  it('uses levels / recorded win levels for direct play', () => {
    const o = outcome(run({ levels: 1, recorded_win_levels: 4 }))
    expect(o).toMatchObject({ tone: 'partial', score: 1, total: 4 })
    expect(scoreText(o)).toBe('1 / 4')
  })

  it('uses best fresh fitness and the evaluated level count for campaigns', () => {
    const o = outcome(run({
      kind: 'avo', best_fitness: 0, evaluated: 1,
      result_inputs: { config: {}, finalized: true, evaluations: [{ candidate_id: 'x_0001', fitness: 0, success: false, environment_steps: 0, finish_reason: null,
        score: { win_levels: null, environment_task: { score: { win_levels: 4 } }, research_score: { win_levels: 4 }, research_environment_actions: 11, search_session_elapsed_seconds: 10 } }] },
    }))
    expect(o).toMatchObject({ tone: 'unsolved', score: 0, total: 4 })
  })

  it('says pending (not unsolved) while the run is active', () => {
    expect(outcome(run({ status: 'running', levels: 0 })).tone).toBe('pending')
    expect(outcome(run({ kind: 'avo', status: 'queued' })).label).toBe('not evaluated yet')
  })
})
