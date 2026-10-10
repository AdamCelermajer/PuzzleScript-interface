import test from 'node:test'
import assert from 'node:assert/strict'
import { activeLaunches, activityAge, liveProgress, phaseLabel } from '../../website/src/active-runs.mjs'

const row = (id, batch, status) => ({ id, batch, status, kind: 'avo', game_id: 'game' })
const job = (id, status, runs, created_at = '2026-09-14T12:00:00Z') => ({ id, status, runs, created_at, comparison: true })

test('activity age accepts server-calibrated time instead of depending on the browser clock', () => {
  const activity = Date.parse('2026-09-22T07:50:00Z')
  assert.equal(activityAge(activity, activity + 12_000), '12s ago')
  assert.equal(activityAge(activity, activity + 2 * 60 * 60_000), '2h ago')
})

test('live launches lead with newest active work and retain finished and failed partners', () => {
  const old = [row('old-a', 'old', 'completed')]
  const recent = [row('a', 'recent', 'running'), row('b', 'recent', 'failed'), row('c', 'recent', 'completed')]
  const earlier = [row('d', 'earlier', 'queued')]
  const catalog = { runs: [...old, ...earlier, ...recent], jobs: [job('old', 'completed', old), job('earlier', 'running', earlier), job('recent', 'running', recent, '2026-09-14T13:00:00Z')] }
  const groups = activeLaunches(catalog)
  assert.deepEqual(groups.map(g => g.id), ['recent', 'earlier'])
  assert.deepEqual(groups[0].runs.map(r => r.id), ['a', 'b', 'c'])
  assert.equal(groups[0].runs[0].comparison, true)
})

test('queued rows need no artifacts and an empty starting launch stays visible', () => {
  const queued = row('queued', 'q', 'queued')
  const groups = activeLaunches({ runs: [queued], jobs: [job('q', 'running', [queued]), job('starting', 'starting', [])] })
  assert.equal(groups.length, 2)
  assert.equal(groups.find(g => g.id === 'q').runs[0].config, undefined)
  assert.equal(phaseLabel(queued), 'Waiting for a parallel slot')
})

test('stale workers appear as attention without claiming archived processes are running', () => {
  const stale = row('stale-run', 'stale', 'unconfirmed')
  const groups = activeLaunches({ runs: [stale, row('archive', 'archive-batch', 'unconfirmed')], jobs: [job('stale', 'unconfirmed', [{ ...stale, status: 'running' }])] })
  assert.equal(groups.length, 1)
  assert.equal(groups[0].attention, true)
  assert.equal(groups[0].runs[0].status, 'unconfirmed')
  assert.equal(phaseLabel(stale), 'Worker heartbeat unavailable')
})

test('live launch dates take priority over attention status and newer evidence', () => {
  const stale = row('s', 'new', 'unconfirmed'), live = { ...row('l', 'old', 'running'), modified: Date.parse('2026-09-16') }
  const groups = activeLaunches({ runs: [live, stale], jobs: [job('old', 'running', [live]), job('new', 'unconfirmed', [{ ...stale, status: 'running' }], '2026-09-14T13:00:00Z')] })
  assert.deepEqual(groups.map(g => g.id), ['new', 'old'])
  assert.equal(groups[0].attention, true)
})

test('no active work produces an empty view; standalone activity does not bring along archive siblings', () => {
  const finished = row('finished', 'archive', 'completed')
  assert.deepEqual(activeLaunches({ runs: [finished], jobs: [] }), [])
  const groups = activeLaunches({ runs: [finished, row('live', 'archive', 'running')], jobs: [] })
  assert.deepEqual(groups[0].runs.map(r => r.id), ['live'])
})

test('paused or stopped resumable batches remain on the Runs page', () => {
  const stopped = row('saved', 'stopped', 'cancelled')
  const groups = activeLaunches({ runs: [stopped], jobs: [{ ...job('stopped', 'cancelled', [stopped]), can_resume: true }] })
  assert.equal(groups.length, 1)
  assert.equal(groups[0].recoverable, true)
  assert.equal(phaseLabel(stopped), 'Stopped; saved for recovery')
})

test('backend failures stay visible as needs assistance without offering resume', () => {
  const failed = { ...row('broken', 'job', 'failed'), needs_assistance: true }
  const groups = activeLaunches({ runs: [failed], jobs: [{ ...job('job', 'failed', [failed]),
    needs_assistance: true, can_resume: false }] })
  assert.equal(groups.length, 1)
  assert.equal(groups[0].recoverable, true)
  assert.equal(phaseLabel(failed), 'Failed · needs assistance')
})

test('dismissed unfinished batches leave Runs without removing their catalog records', () => {
  const stopped = row('saved', 'stopped', 'cancelled')
  const catalog = { runs: [stopped], jobs: [{ ...job('stopped', 'cancelled', [stopped]), can_resume: true,
    dismissed_from_runs_at: '2026-09-23T20:00:00Z' }] }
  assert.deepEqual(activeLaunches(catalog), [])
  assert.equal(catalog.runs.length, 1)
})

test('live fitness uses the best fresh evaluation and never substitutes research progress', () => {
  const run = row('live', 'job', 'running')
  const snapshot = { hypotheses_evaluated: 3, max_hypotheses: 10, win_levels: 4,
    research: { levels: 4, actions: 80 }, current: 'x_0004', phase: 'research',
    candidates: [{ evaluated: true, fitness: 1 }, { evaluated: true, fitness: 2 }, { evaluated: true, fitness: 0 }, { evaluated: false, fitness: 4 }] }
  const progress = liveProgress(run, snapshot, { optimizer_effort: 'xhigh' }, 99)
  assert.equal(progress.best_fitness, 2)
  assert.equal(progress.solved, false)
  assert.equal(progress.evaluated, 3)
  assert.equal(progress.win_levels, 4)
  assert.equal(progress.optimizer_effort, 'xhigh')
  const newerCatalog = liveProgress({ ...run, best_fitness: 3, evaluated: 4 }, snapshot)
  assert.equal(newerCatalog.best_fitness, 3)
  assert.equal(newerCatalog.evaluated, 4)
  assert.equal(liveProgress(run, { research: { levels: 4 } }, {}, 4).best_fitness, null)
  assert.equal(liveProgress(run, null, {}, 4).currentGameTotal, true)
  assert.equal(liveProgress(run, { candidates: [{ evaluated: true, fitness: 4, success: true }] }).solved, true)
})
