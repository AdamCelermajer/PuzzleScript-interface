import { api, escapeHtml as e, agentName, providerName } from './runs-shared.js'
const root = document.querySelector('[data-run-list]')
let data = { runs: [], jobs: [] }, loading = false
const search = root.querySelector('[data-search]'), kind = root.querySelector('[data-kind]'), status = root.querySelector('[data-status]')
const active = r => ['running', 'starting', 'queued', 'stopping'].includes(r.status)
function render() {
  const needle = search.value.trim().toLowerCase()
  const rows = data.runs.filter(r => (!kind.value || r.kind === kind.value) &&
    (!needle || `${r.game_id} ${r.agent_backend} ${r.model_provider} ${r.model} ${r.batch} ${r.id}`.toLowerCase().includes(needle)) &&
    (status.value === 'all' || (status.value === 'active' ? active(r) : status.value === 'unconfirmed' ? r.status === 'unconfirmed' : !active(r) && r.status !== 'unconfirmed')))
  const groups = rows.reduce((m,r) => m.set(r.batch, [...(m.get(r.batch)||[]),r]), new Map())
  root.querySelector('[data-run-groups]').innerHTML = [...groups].map(([batch, runs]) => {
    const job = data.jobs.find(j => j.id === batch)
    return `<section class="run-group"><header><h2>${e(batch || 'Individual runs')} <small> · ${runs.length} run${runs.length === 1 ? '' : 's'}</small></h2>${job?.comparison ? `<a class="button" href="/runs/compare.html?job=${encodeURIComponent(job.id)}">Compare conditions ↗</a>` : ''}${job?.can_stop ? `<button data-stop="${e(job.id)}">Stop batch</button>` : ''}</header><div class="run-table-wrap"><table class="run-table"><thead><tr><th>Game / run</th><th>Runner</th><th>Process</th><th>Progress / result</th><th>Last evidence</th></tr></thead><tbody>${runs.map(r => `<tr><td>${r.href ? `<a href="${e(r.kind === 'avo' ? `/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}` : r.href)}">${e(r.game_id || r.id)}</a>` : e(r.game_id || r.id)}<small>${e(r.id.split('/').slice(-2).join('/'))}</small>${r.kind === 'avo' && r.href ? `<small><a href="/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}">Inspect run & replay</a>${r.has_result ? ` · <a href="/runs/submission.html?run=${encodeURIComponent(r.id)}">Final result</a>` : ''}</small>` : ''}</td><td>${r.kind === 'avo' ? `AVO · ${r.agent_backend === 'opencode' ? 'OpenCode' : 'Codex'}` : r.condition === 'baseline-plus' ? 'Baseline+' : 'Baseline'}<small>${e(providerName(r.model_provider || 'openai'))} · ${e(r.model || '—')}${r.world_model_mode ? ` · ${e(r.world_model_mode)}` : ''}</small></td><td><span class="run-status ${e(r.status)}" title="${e(r.status_source)}">${e(r.status)}</span>${r.solved ? '<small>Solved · recorded result</small>' : ''}${r.log_href ? `<small><a href="${e(r.log_href)}" target="_blank" rel="noreferrer">Launch log</a></small>` : ''}</td><td>${r.kind === 'avo' ? `${e(r.evaluated ?? 0)} / ${e(r.budget ?? '—')} evaluations<small>Best fresh fitness: ${e(r.best_fitness ?? '—')} · ${e(r.candidate || 'no candidate yet')}</small>` : `${e(r.actions ?? '—')} / ${e(r.budget ?? '—')} actions<small>Levels completed: ${e(r.levels ?? '—')}</small>`}</td><td>${r.modified ? e(new Date(r.modified).toLocaleString()) : '—'}</td></tr>`).join('')}</tbody></table></div></section>`
  }).join('') || '<div class="run-empty">No runs match this view. Choose “All runs” to browse saved evidence.</div>'
}
async function refresh() {
  if (loading) return
  loading = true
  try {
    data = await api('/catalog')
    root.querySelector('[data-services]').textContent = `Workbench connected · ${data.runs.filter(active).length} active or queued · ${data.runs.length} recorded runs · checked ${new Date().toLocaleTimeString()}`
    const notice = root.querySelector('[data-notice]')
    notice.textContent = [...data.warnings, ...data.jobs.filter(j => j.error).map(j => `${j.id}: ${j.error}`)].join('\n')
    notice.hidden = !notice.textContent
    render()
  } catch (error) {
    root.querySelector('[data-services]').textContent = 'Workbench API unavailable · displayed records may be stale'
    const notice = root.querySelector('[data-notice]')
    notice.hidden = false
    notice.textContent = `${error.message}. Start npm run workbench to bring up the local services.`
  } finally { loading = false }
}
root.addEventListener('click', async event => {
  const button = event.target.closest('[data-stop]')
  if (!button) return
  button.disabled = true
  try { await api(`/experiments/stop?job=${encodeURIComponent(button.dataset.stop)}`, {method:'POST'}); button.textContent = 'Stop requested' }
  catch(error) { button.disabled = false; root.querySelector('[data-notice]').hidden = false; root.querySelector('[data-notice]').textContent = error.message }
})
for (const input of [search, kind, status]) input.addEventListener('input', render)
root.querySelector('[data-refresh]').addEventListener('click', refresh)
refresh()
setInterval(refresh, 5000)
