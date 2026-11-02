import { api } from './runs-shared.js'

export const numeric = value => typeof value === 'number' && Number.isFinite(value)
const levelCount = value => Number.isInteger(value) && value > 0 ? value : null
export function evaluationLevels(evaluation) {
  return levelCount(evaluation?.score?.environment_task?.score?.win_levels)
    ?? levelCount(evaluation?.score?.win_levels)
    ?? levelCount(evaluation?.score?.research_score?.win_levels)
}
export function fitnessText(fitness, levels) {
  return `${numeric(fitness) ? Number(fitness.toFixed(3)) : '—'} / ${levelCount(levels) ?? '—'}`
}
export function outcome(run) {
  if (run.solved === true || run.success === true) return { label: 'Solved', tone: 'solved' }
  const score = run.kind === 'codex' ? run.levels : (run.best_fitness ?? run.fitness)
  if (!numeric(score)) return { label: run.kind === 'codex' ? 'No result yet' : 'Not evaluated', tone: 'pending' }
  if (['running', 'starting', 'queued', 'stopping'].includes(run.status)) return { label: 'Not solved yet', tone: 'pending' }
  return { label: 'Not solved', tone: 'unsolved' }
}
export const gameHref = id => `/games/?game=${encodeURIComponent(id || '')}`
export function comparisonHref(ids, detail = true) {
  const query = new URLSearchParams(detail ? { view: 'detail' } : {})
  for (const id of new Set(ids)) query.append('run', id)
  return `/runs/compare.html?${query}`
}
export function pairRuns(run, rows) {
  return run.comparison && run.pair_id
    ? rows.filter(r => r.batch === run.batch && r.pair_id === run.pair_id && r.game_id === run.game_id)
    : []
}
export function summarizeEvaluations(config, lineage, summary = {}, fallbackLevels = null) {
  const evaluations = (lineage.evaluations || []).filter(e => numeric(e?.fitness))
  const best = evaluations.reduce((best, e) => !best || e.fitness > best.fitness ? e : best, null)
  const firstSuccess = evaluations.findIndex(e => e.success === true)
  const initialLevels = config.initial_observation?.progress?.win_levels
  const recordedLevels = evaluationLevels(best) ?? evaluations.map(evaluationLevels).find(Boolean)
    ?? (Number.isInteger(initialLevels) && initialLevels > 0 ? initialLevels : null)
  const researchActions = evaluations.map(e => e.score?.research_environment_actions)
  return {
    comparison_ready: true, best_fitness: best?.fitness ?? null, best_candidate: best?.candidate_id ?? null,
    solved: firstSuccess >= 0, evaluated: evaluations.length, finalized: Object.keys(summary).length > 0,
    win_levels: recordedLevels ?? fallbackLevels, win_levels_source: recordedLevels ? 'recorded' : fallbackLevels ? 'current-game' : null,
    effort: config.player?.effort, optimizer_effort: config.optimizer_effort,
    comparison_config: { max_evaluations: config.max_evaluations, research_moves: config.player?.max_environment_steps,
      solver_moves: config.fresh_solver_max_environment_steps, max_hours: numeric(config.player?.max_wall_seconds) ? config.player.max_wall_seconds / 3600 : null },
    first_success_evaluation: firstSuccess >= 0 ? firstSuccess + 1 : null,
    seconds_to_success: firstSuccess >= 0 ? evaluations[firstSuccess].score?.search_session_elapsed_seconds ?? null : null,
    search_seconds: evaluations.at(-1)?.score?.search_session_elapsed_seconds ?? null,
    research_actions: researchActions.length && researchActions.every(numeric) ? researchActions.reduce((a, b) => a + b, 0) : null,
    solver_actions: best?.environment_steps ?? null, finish_reason: best?.finish_reason ?? null,
    history: evaluations.map(e => ({ candidate: e.candidate_id, fitness: e.fitness, win_levels: evaluationLevels(e) ?? recordedLevels ?? fallbackLevels, success: e.success === true })),
  }
}

// The game library is static for a page view; share one request between pollers.
let libraryRequest = null
function libraryCatalog() {
  libraryRequest ||= fetch('/__games/catalog').then(r => r.ok ? r.json() : { games: [] }).catch(() => ({ games: [] }))
    .then(library => { if (!library.games?.length) libraryRequest = null; return library })
  return libraryRequest
}
// The catalog carries each run's compact settings and evaluations, so results need
// no per-run archive requests.
export async function resultsCatalog() {
  const [catalog, library] = await Promise.all([api('/catalog'), libraryCatalog()])
  const gameLevels = new Map((library.games || []).map(g => [g.id, g.levels]))
  const runs = catalog.runs.map(run => {
    const fallback = gameLevels.get(run.game_id) ?? null
    const base = { ...run, win_levels: fallback, win_levels_source: fallback ? 'current-game' : null, comparison_ready: false }
    if (!run.config || (run.kind === 'avo' && !run.config.player)) return base
    const projection = run.kind === 'codex' ? { win_levels: run.recorded_win_levels ?? null }
      : run.result_inputs ? summarizeEvaluations(run.result_inputs.config, run.result_inputs, run.result_inputs.finalized ? { finalized: true } : {})
        : null
    if (!projection) return base
    return { ...base, ...projection, win_levels: projection.win_levels ?? fallback, win_levels_source: projection.win_levels ? 'recorded' : base.win_levels_source }
  })
  return { ...catalog, runs }
}
