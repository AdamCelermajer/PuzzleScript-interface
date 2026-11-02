import { api, escapeHtml as e, providerName, enableRunRowNavigation } from './runs-shared.js'
import { catalogRuns, failed, visibleRuns, gameName, loadVisibility, saveVisibility, visibilityControls, resultGroups, runDate } from './run-organization.mjs'
import { resultsCatalog, fitnessText, outcome, gameHref, comparisonHref, pairRuns } from './run-results.mjs'

const root = document.querySelector('[data-run-list]'), get = selector => root.querySelector(selector)
enableRunRowNavigation(root)
let data = { runs: [], jobs: [] }, loading = false, shown = []
const selected = new Set(new URLSearchParams(location.search).getAll('run'))
const search = get('[data-search]'), kind = get('[data-kind]'), status = get('[data-status]')
let preferences = loadVisibility(), showHidden = false
get('[data-run-groups]').insertAdjacentHTML('beforebegin', visibilityControls(preferences))
get('.run-filters').insertAdjacentHTML('beforeend', `<select data-game aria-label="Filter by game"><option value="">All games</option></select><select data-outcome aria-label="Filter by solved result"><option value="">All outcomes</option><option value="solved">Solved</option><option value="unsolved">Not solved</option><option value="unscored">Not evaluated / no result</option></select>`)
get('[data-run-groups]').insertAdjacentHTML('beforebegin', `<div class="compare-tray"><div><strong data-selection-count aria-live="polite">Select runs to compare</strong><small data-selection-help>Use Compare pair for parallel runs, or select AVO runs across models and launches.</small></div><div class="runs-actions"><button data-select-visible>Select visible AVO runs</button><button data-clear-selection disabled>Clear</button><a class="button primary" data-compare-selected aria-disabled="true">Compare selected (0)</a></div></div>`)
const active = r => ['running', 'starting', 'queued', 'stopping'].includes(r.status)
const date = value => value ? new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Date unavailable'
function resultCell(r) {
  const result = outcome(r)
  return `<strong class="run-fitness" title="${r.win_levels_source === 'current-game' ? 'Total from current game; this run did not record its level count.' : 'Best fresh solver fitness / total levels recorded by the game'}">${e(fitnessText(r.kind === 'avo' ? r.best_fitness : r.levels, r.win_levels))}</strong> <span class="run-outcome ${result.tone}">${result.label}</span><small>${e(r.kind === 'avo' ? r.evaluated ?? 0 : r.actions ?? '—')} / ${e(r.budget ?? '—')} ${r.kind === 'avo' ? 'evaluations' : 'actions'}${r.win_levels_source === 'current-game' ? ' · current game total' : ''}</small>`
}
function selectionTray() {
  const chosen = catalogRuns(data).filter(r => selected.has(r.id))
  get('[data-selection-count]').textContent = chosen.length ? `${chosen.length} runs selected · ${new Set(chosen.map(r => r.game_id)).size} game${new Set(chosen.map(r => r.game_id)).size === 1 ? '' : 's'}` : 'Select runs to compare'
  get('[data-selection-help]').textContent = chosen.length ? [...new Set(chosen.map(r => `${gameName(r.game_id)} · ${r.model} · ${r.effort || '—'}`))].join(' | ') : 'Use Compare pair for parallel runs, or select AVO runs across models and launches.'
  const link = get('[data-compare-selected]')
  link.textContent = `Compare selected (${chosen.length})`
  link.setAttribute('aria-disabled', String(chosen.length < 2))
  if (chosen.length >= 2) link.href = comparisonHref(chosen.map(r => r.id)); else link.removeAttribute('href')
  get('[data-clear-selection]').disabled = !chosen.length
  get('[data-select-visible]').disabled = !shown.some(r => r.comparison_ready)
}
function render() {
  const needle = search.value.trim().toLowerCase()
  const resumable = new Set(data.jobs.filter(job => job.can_resume).map(job => job.id))
  const allowed = visibleRuns(catalogRuns(data), { ...preferences, showFailed: true }, showHidden)
    .filter(run => preferences.showFailed || !failed(run) || resumable.has(run.batch))
  const ids = new Set(allowed.filter(r => r.comparison_ready).map(r => r.id))
  for (const id of selected) if (!ids.has(id)) selected.delete(id)
  shown = allowed.filter(r => (!kind.value || r.kind === kind.value) && (!get('[data-game]').value || r.game_id === get('[data-game]').value) &&
    (!needle || `${r.game_id} ${r.agent_backend} ${r.model_provider} ${r.model} ${r.effort} ${r.batch} ${r.id}`.toLowerCase().includes(needle)) &&
    (!get('[data-outcome]').value || (get('[data-outcome]').value === 'solved' ? r.solved : get('[data-outcome]').value === 'unsolved' ? !r.solved && (r.kind === 'avo' ? r.best_fitness : r.levels) != null : (r.kind === 'avo' ? r.best_fitness : r.levels) == null)) &&
    (status.value === 'all' || (status.value === 'active' ? active(r) : status.value === 'unconfirmed' ? r.status === 'unconfirmed' : !active(r) && r.status !== 'unconfirmed')))
  const groups = resultGroups(shown)
  get('[data-run-groups]').innerHTML = groups.map(({ id: batch, runs, date: groupDate }) => {
    const job = data.jobs.find(j => j.id === batch), comparison = runs[0].comparison
    const title = `${e(date(groupDate))} <small>· ${comparison ? 'Parallel comparison' : 'Experiment'} · ${runs.length} run${runs.length === 1 ? '' : 's'}</small>`
    const comparable = runs.filter(r => r.comparison_ready), seenPairs = new Set()
    return `<section class="run-group" data-sort-date="${groupDate}"><header><h2 title="${e(batch)}">${title}</h2><div class="runs-actions">${comparable.length >= 2 ? `<a class="button" href="${e(comparisonHref(comparable.map(r => r.id)))}">Compare ${comparison ? 'campaign' : 'these runs'} ↗</a>` : ''}${job ? `<button data-hide="${e(job.id)}">${preferences.hidden.includes(job.id) ? 'Restore experiment' : 'Hide experiment'}</button>` : ''}${job?.can_pause ? `<button data-pause="${e(job.id)}">Pause batch</button>` : ''}${job?.can_resume ? `<button data-resume="${e(job.id)}">Resume batch (normal tier)</button>` : ''}</div></header><div class="run-table-wrap"><table class="run-table"><thead><tr><th>Select</th><th>Game / run</th><th>Player</th><th>Fitness / levels</th><th>Process</th><th>Date ↓</th><th>Visibility</th></tr></thead><tbody>${runs.map(r => {
      const pairKey = `${r.batch}:${r.pair_id}`, pair = pairRuns(r, comparable)
      const pairHeader = comparison && !seenPairs.has(pairKey) ? `<tr class="parallel-pair"><td colspan="7"><div><span><a class="game-link" href="${gameHref(r.game_id)}">${e(gameName(r.game_id))} ↗</a> · ${e(r.pair_id)} · ${pair.length} visible runs</span>${pair.length >= 2 ? `<a class="button" href="${e(comparisonHref(pair.map(p => p.id)))}">Compare pair ↗</a>` : '<small>Partner is hidden or unavailable</small>'}</div></td></tr>` : ''
      seenPairs.add(pairKey)
      const href = r.kind === 'avo' ? `/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}` : r.href
      const runName = (r.world_model_mode || r.condition || 'Open run').replaceAll('-', ' ')
      return `${pairHeader}<tr class="${selected.has(r.id) ? 'is-selected' : ''}" ${href ? 'data-run-row' : ''}><td>${r.comparison_ready ? `<input type="checkbox" data-select="${e(r.id)}" aria-label="Select ${e(gameName(r.game_id))}, ${e(r.model)}, ${e(r.world_model_mode || r.id)}, ${e(r.id)}" ${selected.has(r.id) ? 'checked' : ''}>` : '<span title="Comparison requires an AVO campaign archive">—</span>'}</td><td><a class="game-link" href="${gameHref(r.game_id)}">${e(gameName(r.game_id))}</a><small>${href ? `<a class="run-name-link" data-run-link href="${e(href)}">${e(runName)} ↗</a>` : e(runName)}</small>${r.href ? `<small><a href="${e(r.kind === 'avo' ? `/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}` : r.href)}">Inspect run</a>${r.kind === 'avo' && r.has_result ? ` · <a href="/runs/submission.html?run=${encodeURIComponent(r.id)}">Result</a>` : ''}</small>` : ''}</td><td><strong>${e(r.model || '—')}</strong><small>${e(r.effort || '—')} · ${e(providerName(r.model_provider || 'openai'))} · ${r.kind === 'avo' ? 'AVO' : r.condition === 'baseline-plus' ? 'Baseline+' : 'Baseline'}</small></td><td>${resultCell(r)}</td><td><span class="run-status ${e(r.status)}" title="${e(r.status_source)}">${e(r.status)}</span>${r.log_href ? `<small><a href="${e(r.log_href)}" target="_blank" rel="noreferrer">Log</a></small>` : ''}</td><td class="result-date" title="Last evidence: ${e(date(r.modified))}">${e(date(runDate(r)))}<small>${r.created_at ? 'Launched' : r.started_at ? 'Started' : 'Last activity'}</small></td><td><button data-hide="${e(r.id)}">${preferences.hidden.includes(r.id) ? 'Restore' : 'Hide'}</button></td></tr>`
    }).join('')}</tbody></table></div></section>`
  }).join('') || '<div class="run-empty">No runs match these filters.</div>'
  selectionTray()
}
async function refresh() {
  if (loading) return
  loading = true
  try {
    data = await resultsCatalog()
    const game = get('[data-game]').value
    get('[data-game]').innerHTML = '<option value="">All games</option>' + [...new Set(data.runs.map(r => r.game_id).filter(Boolean))].sort().map(id => `<option value="${e(id)}">${e(gameName(id))}</option>`).join('')
    get('[data-game]').value = game
    get('[data-services]').textContent = `Workbench connected · ${data.runs.filter(active).length} active or queued · ${data.runs.length} recorded runs · checked ${new Date().toLocaleTimeString()}`
    const notice = get('[data-notice]')
    notice.textContent = [...data.warnings, ...data.jobs.filter(j => j.error && preferences.showFailed && !preferences.hidden.includes(j.id)).map(j => `${j.id}: ${j.error}`)].join('\n')
    notice.hidden = !notice.textContent
    render()
  } catch (error) {
    get('[data-services]').textContent = 'Workbench API unavailable · displayed records may be stale'
    get('[data-notice]').hidden = false; get('[data-notice]').textContent = error.message
  } finally { loading = false }
}
root.addEventListener('click', async event => {
  if (event.target.closest('[data-select-visible]')) { shown.filter(r => r.comparison_ready).forEach(r => selected.add(r.id)); render(); return }
  if (event.target.closest('[data-clear-selection]')) { selected.clear(); render(); return }
  const hide = event.target.closest('[data-hide]'), restore = event.target.closest('[data-restore-hidden]')
  if (hide || restore) {
    const id = hide?.dataset.hide
    const hidden = restore ? [] : preferences.hidden.includes(id) ? preferences.hidden.filter(x => x !== id) : [...preferences.hidden, id]
    try { saveVisibility({ ...preferences, hidden }); preferences.hidden = hidden; render() }
    catch { get('[data-notice]').hidden = false; get('[data-notice]').textContent = 'Browser storage is unavailable; visibility was not saved.' }
    return
  }
  const button = event.target.closest('[data-pause],[data-resume]')
  if (!button) return
  button.disabled = true
  const resume = button.matches('[data-resume]'), id = button.dataset.resume || button.dataset.pause
  try {
    const result = await api(`/experiments/${resume ? 'resume' : 'pause'}?job=${encodeURIComponent(id)}`, {method:'POST', ...(resume ? {headers:{'Content-Type':'application/json'}, body:JSON.stringify({service_tier:'', optimizer_service_tier:''})} : {})})
    button.textContent = resume ? 'Recovery started' : 'Pause requested'
    if (resume && result.id) location.href = '/'
  }
  catch(error) { button.disabled = false; get('[data-notice]').hidden = false; get('[data-notice]').textContent = error.message }
})
root.addEventListener('change', event => {
  if (event.target.matches('[data-select]')) { const id = event.target.dataset.select; event.target.checked ? selected.add(id) : selected.delete(id); event.target.closest('tr').classList.toggle('is-selected', event.target.checked); selectionTray() }
})
for (const input of [search, kind, status, get('[data-game]'), get('[data-outcome]')]) input.addEventListener('input', render)
get('[data-refresh]').addEventListener('click', refresh)
get('[data-show-failed]').addEventListener('change', event => { preferences.showFailed = event.target.checked; try { saveVisibility(preferences) } catch {} render() })
get('[data-show-hidden]').addEventListener('change', event => { showHidden = event.target.checked; render() })
window.addEventListener('storage', () => { preferences = loadVisibility(); get('[data-show-failed]').checked = preferences.showFailed; render() })
refresh()
setInterval(() => { if (!document.hidden) refresh() }, 5000)
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh() })
