import { escapeHtml as e, agentName } from './runs-shared.js'
import { catalogRuns, visibleRuns, gameName, loadVisibility, saveVisibility, visibilityControls } from './run-organization.mjs'
import { resultsCatalog, fitnessText, outcome, gameHref, comparisonHref, pairRuns, numeric } from './run-results.mjs'

const root = document.querySelector('[data-comparison]'), get = s => root.querySelector(s), params = new URLSearchParams(location.search)
const detailView = params.get('view') === 'detail' || !!params.get('job')
let preferences = loadVisibility(), showHidden = false, busy = false, rows = [], initialized = false
let selected = new Set(params.getAll('run'))
get('[data-visibility]').innerHTML = visibilityControls(preferences)
get('[data-scope]').value = params.has('run') || params.has('game') ? 'all' : 'paired'
const value = x => x == null ? '—' : e(x), duration = x => x == null ? '—' : `${Math.round(x / 60)}m`
const date = r => r.created_at ? new Date(r.created_at).toLocaleString() : r.modified ? new Date(r.modified).toLocaleString() : r.batch?.split('/').at(-1) || 'Date not recorded'
const condition = r => r.world_model_mode === 'final-only' ? 'Final only' : r.world_model_mode === 'between-hypotheses' ? 'Between hypotheses' : 'Condition not recorded'
const label = r => `${r.model || 'Unknown model'} · ${r.effort || '—'} · ${condition(r)}`
function group(runs) { const groups = new Map(); for (const r of runs) groups.set(r.game_id, [...(groups.get(r.game_id) || []), r]); return [...groups] }
function filtered() {
  const search = get('[data-search]').value.toLowerCase().trim()
  return visibleRuns(rows, preferences, showHidden).filter(r => (get('[data-scope]').value !== 'paired' || r.comparison) &&
    (!get('[data-game]').value || r.game_id === get('[data-game]').value) && (!get('[data-mode]').value || r.world_model_mode === get('[data-mode]').value) &&
    (!search || `${r.game_id} ${r.model} ${r.effort} ${r.optimizer_model} ${r.optimizer_effort} ${r.batch} ${r.agent_backend}`.toLowerCase().includes(search)))
}
function links(r) { return `<a href="/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}">Trace & replay ↗</a>${r.best_candidate ? `<a href="/runs/submission.html?run=${encodeURIComponent(r.id)}">Solver & report ↗</a>` : ''}` }
function score(r) {
  const result = outcome(r)
  return `<strong class="run-fitness">${e(fitnessText(r.best_fitness, r.win_levels))}</strong><span class="run-outcome ${result.tone}">${result.label}</span>${r.win_levels_source === 'current-game' ? '<small>Current game total</small>' : ''}`
}
function render() {
  // Explicit detail URLs retain their runs even if they later fail or are hidden in the catalog.
  const allowed = new Set((detailView ? rows : visibleRuns(rows, preferences, showHidden)).map(r => r.id))
  selected = new Set([...selected].filter(id => allowed.has(id)))
  if (detailView) { renderSelected(); return }
  const visible = filtered()
  get('[data-count]').textContent = `${visible.length} runs · ${group(visible).length} games · ${new Set(visible.map(r => r.batch)).size} launches`
  const jump = get('[data-jump]')
  jump.textContent = `Compare selected (${selected.size})`; jump.setAttribute('aria-disabled', String(selected.size < 2))
  if (selected.size >= 2) jump.href = comparisonHref(selected); else jump.removeAttribute('href')
  get('[data-clear]').disabled = !selected.size; get('[data-restore-hidden]').disabled = !preferences.hidden.length
  get('[data-comparison-content]').innerHTML = group(visible).map(([game, runs]) => `<section class="run-group comparison-overview"><header><h2><a href="${gameHref(game)}">${e(gameName(game))}</a> <small>· ${runs.length} runs</small></h2><div class="runs-actions"><button data-select-game="${e(game)}">Select this game</button>${runs.length >= 2 ? `<a class="button" href="${e(comparisonHref(runs.map(r => r.id)))}">Compare this game ↗</a>` : ''}</div></header><div class="run-table-wrap"><table class="run-table"><thead><tr><th>Select</th><th>Player / optimizer</th><th>Condition</th><th>Fresh fitness / levels</th><th>Evaluations</th><th>Process</th><th>Launch / attempt</th><th>Actions</th></tr></thead><tbody>${runs.map(r => {
    const pair = pairRuns(r, visible)
    return `<tr class="${selected.has(r.id) ? 'is-selected' : ''}"><td><input type="checkbox" data-select="${e(r.id)}" aria-label="Compare ${e(gameName(game))}, ${e(label(r))}, ${e(date(r))}" ${selected.has(r.id) ? 'checked' : ''}></td><td><strong>${e(r.model)}</strong><small>${e(r.effort || '—')} · ${e(agentName(r.agent_backend))}</small><small>Optimizer: ${e(r.optimizer_model || '—')} · ${e(r.optimizer_effort || '—')}</small></td><td><span class="condition-label ${r.world_model_mode === 'final-only' ? 'final' : 'between'}">${condition(r)}</span></td><td>${score(r)}</td><td>${value(r.evaluated)} / ${value(r.comparison_config.max_evaluations)}</td><td><span class="run-status ${e(r.status)}">${e(r.status)}</span></td><td>${e(date(r))}<small>${e(r.batch?.split('/').at(-1))}</small><small>${e(r.pair_id || 'Individual campaign')}</small></td><td><div class="run-links">${pair.length >= 2 ? `<a href="${e(comparisonHref(pair.map(p => p.id)))}">Compare pair ↗</a>` : ''}${links(r)}<button data-hide="${e(r.id)}">${preferences.hidden.includes(r.id) ? 'Restore run' : 'Hide run'}</button><button data-hide="${e(r.batch)}">${preferences.hidden.includes(r.batch) ? 'Restore experiment' : 'Hide experiment'}</button></div></td></tr>`
  }).join('')}</tbody></table></div></section>`).join('') || '<div class="comparison-empty"><h2>No runs match this view.</h2><p>Choose all AVO runs, clear the filters, or show failed runs.</p></div>'
}
function curve(runs) {
  const colors = ['#196d5f', '#7664aa', '#be6a2b', '#327ba6', '#b64568', '#657534']
  const totals = [...new Set(runs.map(r => r.win_levels).filter(numeric))]
  const maxIndex = Math.max(2, ...runs.map(r => r.history.length)), maxFitness = Math.max(1, ...totals, ...runs.flatMap(r => r.history.map(p => p.fitness)))
  if (!runs.some(r => r.history.length)) return '<p>No evaluated candidates yet. Scores will appear here as evaluations finish.</p>'
  const y = fitness => 205 - fitness / maxFitness * 170
  const targets = totals.map(total => `<path d="M60 ${y(total)}H710" stroke="#9aafa5" stroke-dasharray="5 5"/><text x="710" y="${y(total) - 9}" text-anchor="end">${total} / ${total} levels</text>`).join('')
  const lines = runs.map((r, i) => {
    let best = -Infinity
    const color = colors[i % colors.length]
    const points = r.history.map((p, n) => { best = Math.max(best, p.fitness); return { x: 60 + n / (maxIndex - 1) * 650, y: y(best), fitness: best, level: p.win_levels, n: n + 1 } })
    return `<polyline fill="none" stroke="${color}" stroke-width="2.5" stroke-dasharray="${i % 2 ? '6 4' : 'none'}" points="${points.map(p => `${p.x},${p.y}`).join(' ')}"/>${points.map(p => `<circle cx="${p.x}" cy="${p.y}" r="${i % 2 ? 2.5 : 4.5}" fill="${color}"><title>Run ${i + 1} · evaluation ${p.n} · ${e(label(r))} · fitness ${fitnessText(p.fitness, p.level)}</title></circle>`).join('')}`
  }).join('')
  return `<svg viewBox="0 0 750 250" role="img" aria-label="Best fresh fitness by evaluated candidate for ${e(gameName(runs[0].game_id))}"><path d="M60 30V205H710" fill="none" stroke="#ccd5d8"/><text x="45" y="${y(maxFitness) + 4}" text-anchor="end">${maxFitness}</text><text x="45" y="209" text-anchor="end">0</text><text x="60" y="225">1</text><text x="710" y="225" text-anchor="end">${maxIndex}</text><text x="385" y="244" text-anchor="middle">Evaluated candidate</text>${targets}${lines}</svg><div class="selected-legend">${runs.map((r, i) => `<span style="border-color:${colors[i % colors.length]}">Run ${i + 1}: ${e(label(r))}<small>${e(fitnessText(r.best_fitness, r.win_levels))} · ${outcome(r).label} · ${e(date(r))}</small></span>`).join('')}</div>${totals.length > 1 ? '<p>These runs recorded different total level counts. Each target line shows its own total.</p>' : ''}`
}
function renderSelected() {
  const chosen = rows.filter(r => selected.has(r.id)), games = group(chosen)
  const expanded = new Set([...get('[data-selected]').querySelectorAll('[data-metrics-game][open]')].map(el => el.dataset.metricsGame))
  get('[data-edit-selection]').href = comparisonHref(selected, false)
  get('[data-detail-title]').innerHTML = games.length === 1 ? `<a href="${gameHref(games[0][0])}">${e(gameName(games[0][0]))}</a> comparison` : 'Selected comparison'
  document.title = `${games.length === 1 ? gameName(games[0][0]) + ' comparison' : 'Selected comparison'} · Research Workbench`
  get('[data-detail-subtitle]').textContent = `${chosen.length} runs · ${games.length} game${games.length === 1 ? '' : 's'} · ${new Set(chosen.map(r => r.batch)).size} launch${new Set(chosen.map(r => r.batch)).size === 1 ? '' : 'es'}`
  if (!chosen.length) { get('[data-selected]').innerHTML = '<div class="comparison-empty"><h2>No selected runs are available.</h2><a href="/runs/compare.html">Browse comparisons</a></div>'; return }
  get('[data-selected]').innerHTML = games.map(([game, runs]) => {
    const row = (name, fn) => `<tr><th scope="row">${name}</th>${runs.map(r => `<td>${fn(r)}</td>`).join('')}</tr>`
    return `<article class="comparison-pair"><header><h2><a href="${gameHref(game)}">${e(gameName(game))} ↗</a></h2><span class="pair-badge">${runs.length} runs</span></header><div class="comparison-scorecards">${runs.map((r, i) => `<div><small>Run ${i + 1} · ${e(condition(r))}</small><h3>${e(r.model)}</h3><p>${e(r.effort || '—')} reasoning</p>${score(r)}<small>Process: ${e(r.status)}</small></div>`).join('')}</div><div class="comparison-chart"><h3>Best fresh fitness by evaluated candidate</h3><p>Fitness / total levels. Dashed lines mark the full level count. Live runs can improve.</p>${curve(runs)}</div><details class="comparison-metrics" data-metrics-game="${e(game)}" ${expanded.has(game) ? 'open' : ''}><summary>Settings, timing & evidence</summary><div class="run-table-wrap"><table class="run-table selected-table"><thead><tr><th>Metric</th>${runs.map((r, i) => `<th>Run ${i + 1}<small>${e(label(r))}</small></th>`).join('')}</tr></thead><tbody>
    ${row('Best fresh fitness / levels', score)}
    ${row('Optimizer', r => `${e(r.optimizer_model || '—')} · ${e(r.optimizer_effort || '—')}`)}
    ${row('Harness', r => e(agentName(r.agent_backend)))}
    ${row('Process', r => e(r.status))}
    ${row('Candidate budget', r => `${r.evaluated} / ${value(r.comparison_config.max_evaluations)}`)}
    ${row('Research / solver action limits', r => `${value(r.comparison_config.research_moves)} / ${value(r.comparison_config.solver_moves)}`)}
    ${row('Player time limit', r => r.comparison_config.max_hours == null ? '—' : `${Number(r.comparison_config.max_hours.toFixed(2))}h`)}
    ${row('First solved', r => r.first_success_evaluation == null ? '—' : `Evaluation ${r.first_success_evaluation} · ${duration(r.seconds_to_success)}`)}
    ${row('Recorded search time', r => duration(r.search_seconds))}${row('Research actions used', r => value(r.research_actions))}${row('Best solver actions', r => value(r.solver_actions))}
    ${row('Finish reason', r => e(r.finish_reason || '—'))}${row('Launch', r => `${e(date(r))}<small>${e(r.id)}</small>`)}${row('Evidence', r => `<div class="run-links">${links(r)}</div>`)}
    </tbody></table></div></details></article>`
  }).join('')
}
async function refresh() {
  if (busy) return; busy = true
  try {
    const catalog = await resultsCatalog()
    rows = catalogRuns(catalog).filter(r => r.kind === 'avo' && r.comparison_ready).sort((a, b) => a.game_id.localeCompare(b.game_id) || (b.created_at || '').localeCompare(a.created_at || '') || (a.pair_id || '').localeCompare(b.pair_id || '') || (a.world_model_mode || '').localeCompare(b.world_model_mode || ''))
    const game = initialized ? get('[data-game]').value : params.get('game') || ''
    get('[data-game]').innerHTML = '<option value="">All games</option>' + [...new Set(rows.map(r => r.game_id))].map(id => `<option value="${e(id)}">${e(gameName(id))}</option>`).join(''); get('[data-game]').value = game
    if (!initialized && params.get('job')) selected = new Set(rows.filter(r => r.batch === params.get('job') && (!game || r.game_id === game) && (!params.get('pair') || r.pair_id === params.get('pair'))).map(r => r.id))
    const missing = params.getAll('run').filter(id => !rows.some(r => r.id === id))
    initialized = true; render(); get('[data-checked]').textContent = `Updated ${new Date().toLocaleTimeString()} · Scores come from fresh solver evaluations.`
    const errors = [...catalog.warnings, ...(missing.length ? [`${missing.length} selected run(s) are unavailable or have no campaign archive.`] : [])]
    get('[data-notice]').hidden = !errors.length; get('[data-notice]').textContent = errors.join('\n')
  } catch (error) { get('[data-notice]').hidden = false; get('[data-notice]').textContent = `${error.message}. Displayed records may be stale.` }
  finally { busy = false }
}
function persist() { try { saveVisibility(preferences) } catch { get('[data-notice]').hidden = false; get('[data-notice]').textContent = 'Browser storage is unavailable; visibility was not saved.' } }
root.addEventListener('change', event => {
  if (event.target.matches('[data-select]')) { const id = event.target.dataset.select; event.target.checked ? selected.add(id) : selected.delete(id); render() }
  if (event.target.matches('[data-show-hidden]')) { showHidden = event.target.checked; render() }
  if (event.target.matches('[data-show-failed]')) { preferences.showFailed = event.target.checked; persist(); render() }
  if (event.target.matches('[data-game], [data-mode], [data-scope]')) render()
})
root.addEventListener('click', event => {
  const hide = event.target.closest('[data-hide]'), game = event.target.closest('[data-select-game]')
  if (hide) { const id = hide.dataset.hide; preferences.hidden = preferences.hidden.includes(id) ? preferences.hidden.filter(x => x !== id) : [...preferences.hidden, id]; persist(); render() }
  if (event.target.closest('[data-restore-hidden]')) { preferences.hidden = []; persist(); render() }
  if (event.target.closest('[data-clear]')) { selected.clear(); render() }
  if (event.target.closest('[data-select-visible]') || game) { filtered().filter(r => !game || r.game_id === game.dataset.selectGame).forEach(r => selected.add(r.id)); render() }
})
get('[data-search]').addEventListener('input', render); get('[data-refresh]').addEventListener('click', refresh)
window.addEventListener('storage', () => { preferences = loadVisibility(); get('[data-show-failed]').checked = preferences.showFailed; render() })
root.classList.toggle('comparison-detail', detailView)
get('[data-browse-heading]').hidden = detailView; get('[data-detail-heading]').hidden = !detailView
get('[data-selected]').hidden = !detailView
refresh(); setInterval(refresh, 15000)
