import { catalogRuns, runDate } from './run-organization.mjs'
import { numeric } from './run-results.mjs'

export const isActive = run => ['running', 'starting', 'queued', 'stopping'].includes(run.status)

export function activityAge(value, nowMs = Date.now()) {
  const time = typeof value === 'number' ? value : Date.parse(value)
  if (!time) return 'No evidence yet'
  const seconds = Math.max(0, Math.floor((nowMs - time) / 1000))
  return seconds < 60 ? `${seconds}s ago` : seconds < 3600 ? `${Math.floor(seconds / 60)}m ago` : `${Math.floor(seconds / 3600)}h ago`
}

// Live activity is independent of historical visibility preferences. Keep a
// finished partner beside its running partner until their whole launch finishes.
export function activeLaunches(catalog) {
  const rows = catalogRuns(catalog)
  const jobs = new Map(catalog.jobs.map(job => [job.id, job]))
  const groups = new Map()
  for (const run of rows) {
    const id = jobs.has(run.batch) ? run.batch : run.id
    if (!groups.has(id)) groups.set(id, { id, job: jobs.get(id), runs: [] })
    groups.get(id).runs.push(run)
  }
  for (const job of catalog.jobs) {
    if (isActive(job) && !groups.has(job.id)) groups.set(job.id, { id: job.id, job, runs: [] })
  }
  return [...groups.values()].flatMap(group => {
    const active = isActive(group.job || {}) || group.runs.some(isActive)
    const attention = !active && group.job?.status === 'unconfirmed' && group.job.runs?.some(isActive)
    const recoverable = !active && (group.job?.can_resume === true || group.job?.needs_assistance === true) && !group.job?.dismissed_from_runs_at
    if (!active && !attention && !recoverable) return []
    const timestamp = group.job?.created_at || group.runs[0]?.created_at
    return [{ ...group, attention, recoverable, started: timestamp, sortTime: runDate({ created_at: timestamp }) || Math.max(0, ...group.runs.map(runDate)) }]
  }).sort((a, b) => b.sortTime - a.sortTime || a.id.localeCompare(b.id))
}

export function liveProgress(run, snapshot, config = {}, fallbackLevels = null) {
  const candidates = (snapshot?.candidates || []).filter(c => c.evaluated && numeric(c.fitness))
  const best = candidates.reduce((best, c) => !best || c.fitness > best.fitness ? c : best, null)
  const recordedLevels = best?.win_levels || snapshot?.win_levels || run.win_levels || config.initial_observation?.progress?.win_levels
  const fitness = [best?.fitness, run.best_fitness].filter(numeric)
  return { ...run, best_fitness: fitness.length ? Math.max(...fitness) : null,
    solved: run.solved === true || candidates.some(c => c.success === true),
    evaluated: Math.max(snapshot?.hypotheses_evaluated || 0, run.evaluated || 0),
    budget: snapshot?.max_hypotheses ?? run.budget,
    win_levels: recordedLevels || fallbackLevels,
    currentGameTotal: !recordedLevels && !!fallbackLevels,
    effort: run.effort || config.player?.effort,
    optimizer_effort: config.optimizer_effort,
    optimizer_model: run.optimizer_model || config.optimizer_model,
    candidate: run.candidate || snapshot?.current,
    phase: snapshot?.phase,
    research: snapshot?.research,
    fresh: snapshot?.fresh_evaluation,
    last_activity: snapshot?.last_activity || run.modified,
  }
}

export function phaseLabel(run) {
  if (run.status === 'queued') return 'Waiting for a parallel slot'
  if (run.status === 'starting') return 'Starting the runner'
  if (run.status === 'stopping') return 'Stopping'
  if (run.status === 'paused') return 'Paused; saved for recovery'
  if (run.status === 'cancelled') return 'Stopped; saved for recovery'
  if (run.status === 'unconfirmed') return 'Worker heartbeat unavailable'
  if (run.needs_assistance) return 'Failed · needs assistance'
  if (!isActive(run)) return run.status === 'completed' ? 'Finished' : run.status
  if (run.kind === 'codex') return 'Playing'
  return ({ research: 'Researching game mechanics', fresh_evaluation: 'Testing the fresh solver',
    starting_fresh_evaluation: 'Starting the fresh solver', finishing_evaluation: 'Saving evaluation',
    evaluated: 'Optimizer reviewing results', pending: 'Preparing the candidate', initializing: 'Initializing' })[run.phase] || 'Loading live activity…'
}
