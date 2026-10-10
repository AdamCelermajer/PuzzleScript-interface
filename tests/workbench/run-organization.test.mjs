import test from 'node:test'
import assert from 'node:assert/strict'
import { catalogRuns, comparisonRuns, visibleRuns, loadVisibility, saveVisibility, runDate, resultGroups, pairsByDate } from '../../website/src/run-organization.mjs'

const catalog = {
  jobs: [
    { id: 'first', comparison: true, status: 'failed', runs: [{ id: 'a', pair_id: 'pair-1' }, { id: 'b', pair_id: 'pair-1' }] },
    { id: 'second', comparison: true, runs: [{ id: 'c', pair_id: 'pair-1', resumed_from: 'b' }] },
  ],
  runs: [
    { id: 'a', batch: 'first', status: 'finished', best_fitness: 0 },
    { id: 'b', batch: 'first', status: 'failed', best_fitness: null },
    { id: 'c', batch: 'second', status: 'running', best_fitness: 0.5 },
  ],
}
const prefs = { showFailed: false, hidden: [] }

test('failed launch does not hide its successful zero-fitness child', () => {
  const rows = visibleRuns(catalogRuns(catalog), prefs)
  assert.deepEqual(rows.map(r => r.id), ['a', 'c'])
  assert.equal(rows[0].best_fitness, 0)
})

test('every attempt remains available, including originals before recovery', () => {
  assert.deepEqual(visibleRuns(catalogRuns(catalog), { ...prefs, showFailed: true }).map(r => r.id), ['a', 'b', 'c'])
})

test('cross-launch comparisons retain colliding pair IDs and missing versus zero scores', () => {
  const report = (id, runs) => ({ id, config: { optimizer_model: 'astra' }, pairs: [{ id: 'pair-1', game_id: 'game', model: 'luna', runs }] })
  const rows = comparisonRuns(catalog, [
    report('first', { 'final-only': { id: 'a', best_fitness: 0 }, 'between-hypotheses': { id: 'b', best_fitness: null } }),
    report('second', { 'between-hypotheses': { id: 'c', best_fitness: 0.5 } }),
  ])
  assert.deepEqual(rows.map(r => [r.id, r.batch, r.best_fitness]), [['a', 'first', 0], ['b', 'first', null], ['c', 'second', 0.5]])
  assert.equal(rows[2].status, 'running')
})

test('hide a run or whole launch reversibly without mutating the catalog', () => {
  assert.deepEqual(visibleRuns(catalog.runs, { ...prefs, hidden: ['first'] }).map(r => r.id), ['c'])
  assert.deepEqual(visibleRuns(catalog.runs, { ...prefs, hidden: ['c'] }).map(r => r.id), ['a'])
  assert.deepEqual(visibleRuns(catalog.runs, { showFailed: true, hidden: ['first'] }, true).map(r => r.id), ['a', 'b', 'c'])
  assert.equal(catalog.runs.length, 3)
})

test('visibility survives reload and malformed browser data falls back safely', () => {
  let raw
  const storage = { getItem: () => raw, setItem: (_key, value) => { raw = value } }
  assert.deepEqual(loadVisibility(storage), prefs)
  saveVisibility({ showFailed: true, hidden: ['first'] }, storage)
  assert.deepEqual(loadVisibility(storage), { showFailed: true, hidden: ['first'] })
  raw = '{invalid'
  assert.deepEqual(loadVisibility(storage), prefs)
})

test('date ordering uses launch time before changing evidence and compares timezones correctly', () => {
  const created_at = '2026-09-14T17:22:00+03:00'
  assert.equal(runDate({ created_at, modified: Date.parse('2026-09-15') }), Date.parse('2026-09-14T14:22:00Z'))
  assert.equal(runDate({ created_at: 'invalid', started_at: 100, modified: 900000 }), 100000)
  assert.equal(runDate({ modified: 1234 }), 1234)
  assert.equal(runDate({}), 0)
})

test('results order launches newest first across games and runner types, keeping pairs intact', () => {
  const rows = [
    { id: 'old-b', batch: 'old', comparison: true, pair_id: 'pair-1', game_id: 'aaa', created_at: '2026-09-14T12:00:00Z' },
    { id: 'new-a', batch: 'new', comparison: true, pair_id: 'pair-1', game_id: 'zzz', created_at: '2026-09-14T14:00:00Z' },
    { id: 'direct', batch: 'direct', kind: 'codex', created_at: '2026-09-14T18:00:00+03:00' },
    { id: 'old-a', batch: 'old', comparison: true, pair_id: 'pair-1', game_id: 'aaa', created_at: '2026-09-14T12:00:00Z' },
    { id: 'new-b', batch: 'new', comparison: true, pair_id: 'pair-1', game_id: 'zzz', created_at: '2026-09-14T14:00:00Z' },
    { id: 'unknown' },
  ]
  const groups = resultGroups(rows)
  assert.deepEqual(groups.map(g => g.id), ['direct', 'new', 'old', 'unknown'])
  assert.deepEqual(groups[1].runs.map(r => r.id), ['new-a', 'new-b'])
  assert.deepEqual(pairsByDate(rows).map(pair => pair.map(r => r.id)), [['direct'], ['new-a', 'new-b'], ['old-a', 'old-b'], ['unknown']])
  assert.equal(rows[0].id, 'old-b')
})
