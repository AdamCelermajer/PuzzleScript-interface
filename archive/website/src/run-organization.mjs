export const failed = run => ['failed', 'cancelled', 'canceled', 'error'].includes(run.status)
export const gameName = id => (id || 'Unknown game').replace(/^ps_/, '').replace(/-v1$/, '').replaceAll('_', ' ')
const storageKey = 'workbench.run-visibility.v1'

export function loadVisibility(storage = globalThis.localStorage) {
  try {
    const value = JSON.parse(storage.getItem(storageKey) || '{}')
    return { showFailed: value.showFailed === true, hidden: Array.isArray(value.hidden) ? value.hidden.filter(x => typeof x === 'string') : [] }
  } catch { return { showFailed: false, hidden: [] } }
}
export function saveVisibility(value, storage = globalThis.localStorage) {
  storage.setItem(storageKey, JSON.stringify(value))
}

// Keep every recorded attempt, including the original attempts before a recovery.
export function catalogRuns(catalog) {
  const owners = new Map(catalog.jobs.flatMap(job => (job.runs || []).map(row => [row.id, { job, row }])))
  return catalog.runs.map(run => {
    const owner = owners.get(run.id)
    return { ...run, comparison: !!owner?.job.comparison, pair_id: owner?.row.pair_id,
      effort: owner?.row.effort || run.effort || run.config?.player?.effort || run.config?.reasoning_effort,
      repeat: owner?.row.repeat,
      started_at: owner?.row.started_at || run.started_at,
      created_at: owner?.job.created_at || run.created_at, job_status: owner?.job.status }
  })
}

export function runDate(run) {
  const created = typeof run.created_at === 'number' ? run.created_at : Date.parse(run.created_at)
  const started = typeof run.started_at === 'number' ? run.started_at * 1000 : Date.parse(run.started_at)
  return (Number.isFinite(created) && created > 0 ? created : 0)
    || (Number.isFinite(started) && started > 0 ? started : 0)
    || (Number.isFinite(run.modified) ? run.modified : 0)
}

// Sort whole pairs together so dates never interleave their two conditions.
export function pairsByDate(runs) {
  const groups = new Map()
  for (const run of runs) {
    const key = run.comparison && run.pair_id ? `${run.batch}:${run.game_id}:${run.pair_id}` : run.id
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(run)
  }
  return [...groups.values()].map(rows => rows.sort((a, b) => runDate(b) - runDate(a) || a.id.localeCompare(b.id)))
    .sort((a, b) => runDate(b[0]) - runDate(a[0]) || a[0].id.localeCompare(b[0].id))
}

export function resultGroups(runs) {
  const groups = new Map()
  for (const run of runs) {
    const id = run.batch || run.id
    if (!groups.has(id)) groups.set(id, { id, runs: [] })
    groups.get(id).runs.push(run)
  }
  return [...groups.values()].map(group => ({ ...group, date: Math.max(...group.runs.map(runDate)), runs: pairsByDate(group.runs).flat() }))
    .sort((a, b) => b.date - a.date || a.id.localeCompare(b.id))
}

export function visibleRuns(runs, preferences, showHidden = false) {
  const hidden = new Set(preferences.hidden)
  return runs.filter(run => (preferences.showFailed || !failed(run)) &&
    (showHidden || (!hidden.has(run.id) && !hidden.has(run.batch))))
}

export function comparisonRuns(catalog, reports) {
  const current = new Map(catalogRuns(catalog).map(run => [run.id, run]))
  return reports.flatMap(report => report.pairs.flatMap(pair => Object.entries(pair.runs).map(([mode, run]) => {
    const live = current.get(run.id)
    if (!live) return null
    return { ...live, ...run, status: live.status, batch: report.id, config: report.config,
      game_id: pair.game_id, model: pair.model, effort: pair.effort, repeat: pair.repeat,
      world_model_mode: mode, pair_id: pair.id, created_at: report.created_at,
      optimizer_model: report.config.optimizer_model, optimizer_effort: report.config.optimizer_effort }
  }).filter(Boolean)))
}

export function visibilityControls(preferences) {
  return `<div class="visibility-controls"><label><input type="checkbox" data-show-failed ${preferences.showFailed ? 'checked' : ''}> Show failed / cancelled</label><label><input type="checkbox" data-show-hidden> Show hidden</label><button type="button" data-restore-hidden>Restore hidden</button><span>Visibility is saved in this browser. Run files are kept.</span></div>`
}
