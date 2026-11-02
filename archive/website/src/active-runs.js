import { api, escapeHtml as e, enableRunRowNavigation } from './runs-shared.js'
import { gameName, pairsByDate } from './run-organization.mjs'
import { fitnessText, outcome, gameHref, comparisonHref } from './run-results.mjs'
import { activeLaunches, activityAge, liveProgress, isActive, phaseLabel } from './active-runs.mjs'

const root = document.querySelector('[data-active-runs]'), get = selector => root.querySelector(selector)
enableRunRowNavigation(root)
const details = new Map(), levels = new Map(), pausing = new Set(), resuming = new Set(), dismissing = new Set()
let launches = [], loading = false, timer, checked = null, requestError = '', serverClockOffsetMs = 0, showSaved = false
const date = value => value ? new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Date unavailable'
const count = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
const mode = r => ({ 'final-only': 'Final only', 'between-hypotheses': 'Between hypotheses', 'baseline-plus': 'Baseline+' })[r.world_model_mode || r.condition] || (r.kind === 'avo' ? 'AVO' : 'Baseline')
function meter(value, total, label) {
  return total > 0 ? `<progress value="${Math.max(0, value || 0)}" max="${e(total)}" aria-label="${e(label)}"></progress>` : ''
}
function runRow(row) {
  const detail = details.get(row.id), run = liveProgress(row, detail?.snapshot, detail?.config, levels.get(row.game_id))
  const result = outcome(run), evaluated = run.kind === 'avo'
  const score = evaluated ? run.best_fitness : run.levels
  const href = row.href || (evaluated ? `/experiments/avo-lab.html?run=${encodeURIComponent(row.id)}` : null)
  return `<tr class="live-run" data-run="${e(row.id)}" ${href ? 'data-run-row' : ''}><td><strong>${href ? `<a class="run-name-link" data-run-link data-focus="run:${e(row.id)}" href="${e(href)}">${e(mode(run))} ↗</a>` : e(mode(run))}</strong><span class="live-status ${isActive(run) ? 'active' : run.status === 'unconfirmed' ? 'attention' : ''}" title="${e(run.status_source)}">${e(run.status)}</span></td>
    <td class="live-model">${e(run.model || 'Model pending')} · ${e(run.effort || '—')}${run.optimizer_model ? `<small>Optimizer ${e(run.optimizer_model)} · ${e(run.optimizer_effort || '—')}</small>` : ''}</td>
    <td class="live-progress"><span class="live-phase">${e(phaseLabel(run))}</span><small>${evaluated ? `${e(run.evaluated)} / ${e(run.budget ?? '—')} evaluated${run.candidate ? ` · ${e(run.candidate.replace(/^x_0*/, 'Candidate '))}` : ''}` : `${e(run.actions ?? '—')} / ${e(run.budget ?? '—')} actions`}</small>${meter(evaluated ? run.evaluated : run.actions, run.budget, evaluated ? 'Completed evaluations' : 'Actions used')}</td>
    <td class="live-moves">${evaluated && (run.research || run.fresh) ? `<span>Research <b>${e(run.research?.actions ?? '—')} / ${e(run.research?.budget ?? '—')}</b></span><span>Solver <b>${e(run.fresh?.actions ?? '—')} / ${e(run.fresh?.budget ?? '—')}</b></span>` : '<span>—</span>'}</td>
    <td class="live-score" title="${evaluated ? 'Best fresh solver fitness' : 'Completed levels'}"><strong>${e(fitnessText(score, run.win_levels))}</strong><span class="run-outcome ${result.tone}">${result.label}</span>${run.currentGameTotal ? '<small>Current game total</small>' : ''}</td>
    <td class="live-activity"><span title="${e(run.last_activity ? new Date(run.last_activity).toLocaleString() : '')}">${detail?.error ? 'Details unavailable · retrying' : e(activityAge(run.last_activity, Date.now() + serverClockOffsetMs))}</span><small>${href ? `<a href="${e(href)}" data-focus="trace:${e(row.id)}">Live trace ↗</a>` : 'Waiting for files'}${row.log_href ? ` · <a href="${e(row.log_href)}" target="_blank" rel="noreferrer" data-focus="log:${e(row.id)}">Log</a>` : ''}</small></td></tr>`
}
function launchSection(group) {
  const pairs = pairsByDate(group.runs)
  const title = group.job?.comparison ? 'Parallel comparison' : group.runs.length > 1 ? 'Experiment batch' : 'Individual run'
  const running = group.runs.filter(r => ['running', 'starting', 'stopping'].includes(r.status)).length
  const queued = group.runs.filter(r => r.status === 'queued').length
  return `<section class="live-launch ${group.attention ? 'needs-attention' : ''} ${group.recoverable ? 'is-recoverable' : ''}" data-sort-date="${group.sortTime}"><header><div><h2>${e(date(group.sortTime))} <span>· ${group.recoverable ? 'Paused / stopped · resumable' : title}${group.attention ? ' · needs attention' : ''}</span></h2><p>${group.started ? 'Launch date' : 'Last activity'} · ${count(group.runs.length, 'run')}${running ? ` · ${running} active` : ''}${queued ? ` · ${queued} queued` : ''}</p></div><div class="runs-actions">${group.job?.comparison && group.runs.length >= 2 ? `<a class="button" href="${e(comparisonHref(group.runs.map(r => r.id)))}" data-focus="compare:${e(group.id)}">Compare campaign ↗</a>` : ''}${group.job?.can_pause ? `<button data-pause="${e(group.id)}" data-focus="pause:${e(group.id)}" ${pausing.has(group.id) ? 'disabled' : ''}>${pausing.has(group.id) ? 'Pause requested' : 'Pause experiment'}</button>` : ''}${group.job?.can_resume ? `<button data-resume="${e(group.id)}" data-focus="resume:${e(group.id)}" ${resuming.has(group.id) || dismissing.has(group.id) ? 'disabled' : ''}>${resuming.has(group.id) ? 'Starting recovery' : 'Resume batch (normal tier)'}</button>` : ''}${group.job?.can_dismiss ? `<button data-dismiss="${e(group.id)}" data-focus="dismiss:${e(group.id)}" ${resuming.has(group.id) || dismissing.has(group.id) ? 'disabled' : ''}>${dismissing.has(group.id) ? 'Removing…' : 'Remove from Runs'}</button>` : ''}</div></header>
    ${group.recoverable ? '<p class="live-warning">Unfinished work is saved. Resuming creates a separate recovery batch and retries only interrupted evaluations.</p>' : ''}
    ${group.attention ? '<p class="live-warning">The worker stopped reporting. These runs are unconfirmed; open their logs to inspect them.</p>' : ''}
    ${group.job?.error ? `<p class="live-warning">${e(group.job.error)}</p>` : ''}
    ${pairs.length ? `<div class="live-table-wrap"><table class="live-table"><thead><tr><th>Condition / status</th><th>Models</th><th>Progress</th><th>Moves</th><th>Fitness / levels</th><th>Activity</th></tr></thead>${pairs.map(rows => `<tbody><tr class="live-pair"><th colspan="6"><div><a class="live-game" href="${gameHref(rows[0].game_id)}" data-focus="game:${e(rows[0].id)}">${e(gameName(rows[0].game_id))} ↗</a>${rows[0].comparison && rows.length >= 2 ? `<a href="${e(comparisonHref(rows.map(r => r.id)))}" data-focus="pair:${e(rows[0].id)}">Compare pair ↗</a>` : ''}</div></th></tr>${rows.map(runRow).join('')}</tbody>`).join('')}</table></div>` : '<p class="live-subtle">Preparing run entries…</p>'}
    </section>`
}
function savedRow(group, expanded) {
  const status = group.job?.needs_assistance ? 'failed · needs assistance' : group.job?.status || group.runs[0]?.status || 'stopped'
  const games = [...new Set(group.runs.map(r => r.game_id).filter(Boolean))].map(gameName)
  const models = [...new Set(group.runs.map(r => r.model).filter(Boolean))]
  const reason = group.runs.find(run => run.failure_reason)?.failure_reason
  const links = `${reason ? `<p>${e(reason)}</p>` : ''}${group.runs.map(run => `<a href="${e(run.href || `/experiments/avo-lab.html?run=${encodeURIComponent(run.id)}`)}">${e(gameName(run.game_id))} · ${e(run.model || 'Run')} ↗</a>`).join('')}`
  return `<details class="live-saved-row" data-saved="${e(group.id)}" ${expanded ? 'open' : ''}><summary><span class="live-status">${e(status)}</span><strong>${e(games.join(', ') || 'Experiment')}</strong><small>${e(date(group.sortTime))} · ${count(group.runs.length, 'run')} · ${e(models.join(' / ') || 'Model pending')}</small></summary><div class="live-saved-detail"><div class="live-saved-links">${links}</div><div class="runs-actions">${group.job?.can_resume ? `<button data-resume="${e(group.id)}" data-focus="resume:${e(group.id)}" ${resuming.has(group.id) ? 'disabled' : ''}>${resuming.has(group.id) ? 'Starting recovery' : 'Resume batch'}</button>` : ''}</div></div></details>`
}
function render() {
  const focus = document.activeElement?.dataset.focus
  const active = launches.filter(g => !g.recoverable), live = active.filter(g => !g.attention), rows = live.flatMap(g => g.runs), recoverable = launches.filter(g => g.recoverable)
  get('[data-live-counts]').innerHTML = `<strong><span class="live-dot"></span>${count(live.length, 'active experiment')}</strong><span>${rows.filter(r => r.status === 'running').length} running</span><span>${rows.filter(r => ['starting', 'stopping'].includes(r.status)).length} starting / stopping</span><span>${rows.filter(r => r.status === 'queued').length} queued</span>${recoverable.length ? `<button type="button" class="live-saved-toggle" data-toggle-saved data-focus="toggle-saved" aria-controls="saved-runs" aria-expanded="${showSaved}">${recoverable.length} paused / stopped / failed ${showSaved ? '▴' : '▾'}</button>` : ''}${active.some(g => g.attention) ? `<span>${active.filter(g => g.attention).length} need attention</span>` : ''}`
  const savedRoot = get('[data-saved-runs]')
  const expanded = new Set([...savedRoot.querySelectorAll('details[open]')].map(item => item.dataset.saved))
  get('[data-live-launches]').innerHTML = active.map(launchSection).join('') || '<section class="live-empty"><h2>No experiments running</h2><p>Finished experiments and their comparisons are in Results.</p><div class="runs-actions"><a class="button primary" href="/runs/new.html">New campaign</a><a class="button" href="/runs/results.html">View results</a></div></section>'
  savedRoot.innerHTML = recoverable.length ? `<h2>Paused / stopped / failed</h2><p>Saved batches stay available for inspection or recovery.</p><div class="live-saved-list">${recoverable.map(group => savedRow(group, expanded.has(group.id))).join('')}</div>` : ''
  savedRoot.hidden = !showSaved || !recoverable.length
  if (focus) [...root.querySelectorAll('[data-focus]')].find(el => el.dataset.focus === focus)?.focus({ preventScroll: true })
  get('[data-services]').textContent = requestError ? 'Connection lost · showing last known activity' : `Auto-refresh · checked ${checked?.toLocaleTimeString() || 'just now'}`
  get('[data-notice]').textContent = requestError
  get('[data-notice]').hidden = !requestError
}
async function json(url) {
  const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error(`Live details unavailable (${response.status})`)
  return response.json()
}
async function refresh() {
  if (loading) return
  clearTimeout(timer); loading = true; get('[data-refresh]').disabled = true
  try {
    const [catalog, visibility] = await Promise.all([
      api('/catalog', { signal: AbortSignal.timeout(15000) }),
      json('/run-visibility.json').catch(() => ({ dismissed_from_runs: [] })),
    ])
    const dismissed = new Set(visibility.dismissed_from_runs || [])
    catalog.jobs = catalog.jobs.map(job => dismissed.has(job.id) ? { ...job, dismissed_from_runs_at: job.dismissed_from_runs_at || 'saved' } : job)
    if (Number.isFinite(Number(catalog.checked_at))) serverClockOffsetMs = Number(catalog.checked_at) * 1000 - Date.now()
    launches = activeLaunches(catalog); checked = new Date(); requestError = ''; render()
    const rows = launches.flatMap(g => g.runs).filter(r => r.kind === 'avo' && r.config?.player)
    let cursor = 0
    await Promise.all(Array.from({ length: Math.min(4, rows.length) }, async () => {
      while (cursor < rows.length) {
        const run = rows[cursor++], previous = details.get(run.id) || {}
        if (!isActive(run) && previous.snapshot && !previous.error && previous.modified === run.modified) continue
        try {
          const [snapshot, config] = await Promise.all([
            json(`/__avo/run?run=${encodeURIComponent(run.id)}`), previous.config || json(`/__avo/artifact?run=${encodeURIComponent(run.id)}&path=evolution_config.json`).then(a => {
              if (a.truncated) throw new Error('Settings truncated')
              return JSON.parse(a.content)
            }),
          ])
          details.set(run.id, { snapshot, config, modified: run.modified })
        } catch (error) { details.set(run.id, { ...previous, error: error.message }) }
      }
    }))
    render()
  } catch (error) {
    requestError = error.message
    if (checked) render()
    else {
      get('[data-services]').textContent = 'Workbench connection unavailable'
      get('[data-live-counts]').textContent = 'Live status unavailable'
      get('[data-live-launches]').innerHTML = '<p class="live-empty">Could not load active experiments. Retrying automatically…</p>'
      get('[data-notice]').hidden = false; get('[data-notice]').textContent = requestError
    }
  } finally { loading = false; get('[data-refresh]').disabled = false; timer = setTimeout(refresh, 5000) }
}
root.addEventListener('click', async event => {
  if (event.target.closest('[data-toggle-saved]')) { showSaved = !showSaved; render(); if (showSaved) get('[data-saved-runs]').scrollIntoView({ block: 'nearest' }); return }
  const dismiss = event.target.closest('[data-dismiss]')
  if (dismiss && !dismissing.has(dismiss.dataset.dismiss)) {
    const id = dismiss.dataset.dismiss
    if (!window.confirm('Remove this unfinished batch from Runs? Its saved artifacts and Results entries will remain available.')) return
    dismissing.add(id); render()
    try {
      await api(`/experiments/dismiss?job=${encodeURIComponent(id)}`, { method: 'POST' })
      await refresh()
    } catch (error) { dismissing.delete(id); requestError = error.message; render() }
    return
  }
  const resume = event.target.closest('[data-resume]')
  if (resume && !resuming.has(resume.dataset.resume)) {
    const id = resume.dataset.resume
    resuming.add(id); render()
    try {
      await api(`/experiments/resume?job=${encodeURIComponent(id)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service_tier: '', optimizer_service_tier: '' }) })
      await refresh()
    } catch (error) { resuming.delete(id); requestError = error.message; render() }
    return
  }
  const button = event.target.closest('[data-pause]')
  if (!button || pausing.has(button.dataset.pause)) return
  const id = button.dataset.pause
  pausing.add(id); render()
  try { await api(`/experiments/pause?job=${encodeURIComponent(id)}`, { method: 'POST' }); await refresh() }
  catch (error) { pausing.delete(id); requestError = error.message; render() }
})
get('[data-refresh]').addEventListener('click', refresh)
json('/__games/catalog').then(library => { for (const game of library.games) levels.set(game.id, game.levels); if (checked) render() }).catch(() => {})
refresh()
