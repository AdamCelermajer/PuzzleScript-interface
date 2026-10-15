import { describe, expect, it } from 'vitest'
import { failureText } from '../views/OptimalPath'

describe('optimal path failure text', () => {
  it('explains a whole-game time limit with the failing level', () => {
    expect(failureText({ run_id: 'r', status: 'failed', progress: { timeoutMs: 60_000 }, result: { status: 'time_limit', failedLevelNumber: 3, totalLevels: 5 } }))
      .toBe('The 60 second whole-game time limit expired on level 3 of 5.')
  })
  it('falls back to the run status and error', () => {
    expect(failureText({ run_id: 'r', status: 'failed', error: 'boom', result: null })).toBe('boom')
    expect(failureText({ run_id: 'r', status: 'cancelled' })).toBe('The search was stopped before it found a winning path.')
  })
})
