import test from 'node:test'
import assert from 'node:assert/strict'
import { fitnessText, evaluationLevels, outcome, summarizeEvaluations, comparisonHref, pairRuns, resultsCatalog } from '../../website/src/run-results.mjs'

const evaluation = (candidate, fitness, success = false, total = 4) => ({
  candidate_id: candidate, fitness, success, environment_steps: 50,
  score: { environment_task: { score: { win_levels: total } }, research_score: { win_levels: 99 }, research_environment_actions: 10, search_session_elapsed_seconds: 60 },
})
test('fitness retains zero and distinguishes missing scores and level totals', () => {
  assert.equal(fitnessText(0, 4), '0 / 4')
  assert.equal(fitnessText(null, 4), '— / 4')
  assert.equal(fitnessText(0.5, null), '0.5 / —')
  assert.equal(fitnessText(NaN, 0), '— / —')
  assert.equal(evaluationLevels(evaluation('a', 0)), 4)
})
test('solved requires recorded success, independently from completion and score', () => {
  assert.equal(outcome({ status: 'finished', best_fitness: 4, win_levels: 4 }).label, 'Not solved')
  assert.equal(outcome({ status: 'failed', best_fitness: 4, solved: true }).label, 'Solved')
  assert.equal(outcome({ status: 'finished', best_fitness: null }).label, 'Not evaluated')
  assert.equal(outcome({ status: 'running', best_fitness: 0 }).label, 'Not solved yet')
})
test('fresh evaluations own fitness, historical totals and first success; ties retain earliest candidate', () => {
  const config = { player: { effort: 'xhigh', max_environment_steps: 500, max_wall_seconds: 7200 }, optimizer_effort: 'high', max_evaluations: 10, fresh_solver_max_environment_steps: 200 }
  const lineage = { evaluations: [evaluation('a', 0), evaluation('b', 4, true), evaluation('c', 4, true), { fitness: Infinity }, { fitness: true }] }
  const result = summarizeEvaluations(config, lineage, { status: 'finished' }, 20)
  assert.equal(result.best_candidate, 'b')
  assert.equal(result.best_fitness, 4)
  assert.equal(result.win_levels, 4)
  assert.equal(result.win_levels_source, 'recorded')
  assert.equal(result.first_success_evaluation, 2)
  assert.equal(result.research_actions, 30)
  assert.equal(result.evaluated, 3)
  assert.equal(result.comparison_config.max_hours, 2)
  assert.deepEqual(result.history.map(p => p.fitness), [0, 4, 4])
})
test('no evaluation is not a zero result and current game totals are identified as fallback', () => {
  const result = summarizeEvaluations({}, { evaluations: [] }, {}, 6)
  assert.equal(result.best_fitness, null)
  assert.equal(result.solved, false)
  assert.equal(result.research_actions, null)
  assert.equal(result.win_levels_source, 'current-game')
  const partial = summarizeEvaluations({}, { evaluations: [evaluation('a', 0), { fitness: 1 }] })
  assert.equal(partial.research_actions, null)
})
test('parallel pair matching cannot combine launches or games with reused pair IDs', () => {
  const rows = [
    { id: 'original-a', comparison: true, batch: 'first', pair_id: 'pair-1', game_id: 'game' },
    { id: 'original-b', comparison: true, batch: 'first', pair_id: 'pair-1', game_id: 'game' },
    { id: 'recovery-a', comparison: true, batch: 'second', pair_id: 'pair-1', game_id: 'game' },
    { id: 'different-game', comparison: true, batch: 'first', pair_id: 'pair-1', game_id: 'other' },
  ]
  assert.deepEqual(pairRuns(rows[0], rows).map(r => r.id), ['original-a', 'original-b'])
  const query = new URL(comparisonHref(['output/a', 'output/b', 'output/a']), 'http://localhost').searchParams
  assert.equal(query.get('view'), 'detail')
  assert.deepEqual(query.getAll('run'), ['output/a', 'output/b'])
})
test('results come from catalog projections without per-run archive requests', async () => {
  const previousFetch = globalThis.fetch, calls = []
  const catalog = { warnings: [], jobs: [], runs: [
    { id: 'output/test/a', kind: 'avo', game_id: 'game', config: { player: {} }, modified: 1, evaluated: 1, best_fitness: 0,
      result_inputs: { config: { player: { effort: 'high' }, max_evaluations: 10 }, evaluations: [evaluation('a', 0)], finalized: true } },
    { id: 'output/test/b', kind: 'codex', game_id: 'game', config: {}, modified: 1, levels: 2, recorded_win_levels: 7 },
    { id: 'output/test/c', kind: 'codex', game_id: 'game', config: {}, modified: 1, levels: 1, recorded_win_levels: null },
  ] }
  globalThis.fetch = async url => {
    calls.push(url)
    const data = url === '/api/workbench/catalog' ? structuredClone(catalog)
      : url === '/__games/catalog' ? { games: [{ id: 'game', levels: 20 }] } : null
    assert.notEqual(data, null, url)
    return { ok: true, json: async () => data }
  }
  try {
    const result = await resultsCatalog()
    assert.equal(result.runs[0].win_levels, 4)
    assert.equal(result.runs[0].comparison_ready, true)
    assert.equal(result.runs[0].best_fitness, 0)
    assert.equal(result.runs[0].effort, 'high')
    assert.equal(result.runs[1].win_levels, 7)
    assert.equal(result.runs[1].win_levels_source, 'recorded')
    assert.equal(result.runs[1].comparison_ready, false)
    assert.equal(result.runs[2].win_levels, 20)
    assert.equal(result.runs[2].win_levels_source, 'current-game')
    assert.deepEqual(result.warnings, [])
    const before = calls.length
    await resultsCatalog()
    assert.deepEqual(calls.slice(before), ['/api/workbench/catalog'])
  } finally { globalThis.fetch = previousFetch }
})
