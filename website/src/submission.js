import { api, escapeHtml as e, agentName, providerName } from './runs-shared.js'
const run = new URLSearchParams(location.search).get('run') || '', q = encodeURIComponent(run)
const selectedCandidate = new URLSearchParams(location.search).get('candidate') || ''
const get = s => document.querySelector(s)
let record
get('[data-evidence]').href = `/experiments/avo-lab.html?run=${q}`
const fileUrl = (file, download = false) => `/api/workbench/submission/file?run=${q}&file=${encodeURIComponent(file)}${download ? '&download=true' : ''}`
async function view(file, scroll = true) {
  try {
    const response = await fetch(fileUrl(file))
    if (!response.ok) throw new Error(await response.text())
    get('[data-file-title]').textContent = file
    get('[data-content]').textContent = await response.text()
    get('[data-viewer]').hidden = false
    if (scroll) get('[data-viewer]').scrollIntoView({behavior:'smooth', block:'start'})
  } catch(error) { get('[data-notice]').hidden = false; get('[data-notice]').textContent = error.message }
}
async function refresh() {
  try {
    record = await api(`/submission?run=${q}&candidate=${encodeURIComponent(selectedCandidate)}`)
    get('[data-notice]').hidden = true
    get('[data-selection-help]').textContent = record.selection === 'candidate' ? 'This archived solver belongs to the selected completed evaluation. The outer report, when available, describes its understanding of the game’s rules after the campaign.' : 'Highest fresh-evaluation fitness; earliest evaluation wins a tie. This is the archived implementation that earned the score. A running campaign may improve it.'
    get('[data-selection]').textContent = record.selection === 'candidate' ? `Evaluated solver · ${record.best.candidate_id}` : 'Best evaluated solver'
    get('[data-title]').textContent = record.game_id || 'Evaluated submission'
    get('[data-status]').textContent = `${agentName(record.agent_backend)} · ${providerName(record.model_provider)} · player: ${record.model} · outer: ${record.optimizer_model || '—'} · ${record.finalized ? 'Campaign result' : 'No final campaign summary yet'} · ${run}`
    get('[data-best]').textContent = record.best ? `${record.best.candidate_id} · fresh fitness ${record.best.fitness} · ${record.best.environment_steps ?? '—'} evaluation actions · ${record.best.success ? 'Solved' : 'Not solved'} · ${record.best.finish_reason || ''}` : 'No completed evaluation yet.'
    if (record.evaluations_to_success) get('[data-best]').textContent += ` · first solved at evaluation ${record.evaluations_to_success}${record.seconds_to_success == null ? '' : `, ${Math.round(record.seconds_to_success)} seconds of search (before final reporting)`}`
    const solver = record.files.find(f => f.name === 'solver.py')
    get('[data-solver]').disabled = !solver
    get('[data-solver-download]').hidden = !solver
    get('[data-bundle]').hidden = !solver
    if (solver) get('[data-solver-download]').href = fileUrl(solver.path, true)
    get('[data-bundle]').href = `/api/workbench/submission/download?run=${q}&candidate=${encodeURIComponent(record.best?.candidate_id || '')}`
    const reportStatus = record.world_model_record?.provenance === 'reconstructed_from_saved_outer_history' ? 'Post-run report reconstructed from saved outer history.' : record.world_model ? 'Final outer report available.' : 'No final outer report saved.'
    get('[data-model-status]').textContent = `${record.mode === 'not-recorded' ? 'Older campaign: world-model condition was not recorded' : record.mode} · ${reportStatus}`
    get('[data-model]').disabled = !record.world_model
    get('[data-model-download]').hidden = !record.world_model
    get('[data-model-download]').href = fileUrl('world_model.md', true)
    get('[data-files]').innerHTML = record.files.filter(f => f.name !== 'solver.py').map(f => `<li><button data-file="${e(f.path)}">${e(f.name)}</button> <small>${Math.ceil(f.size / 1024)} KB · <a href="${e(fileUrl(f.path, true))}">Download</a></small></li>`).join('') || '<li>No evaluated solver files saved.</li>'
    get('[data-history]').innerHTML = `<table class="run-table"><thead><tr><th>Candidate</th><th>Fresh fitness</th><th>Actions</th><th>Outcome</th></tr></thead><tbody>${record.evaluations.map(v => `<tr><td><a href="/runs/submission.html?run=${q}&candidate=${encodeURIComponent(v.candidate_id)}">${e(v.candidate_id)}</a>${v.candidate_id === record.best?.candidate_id ? ' · selected' : ''}</td><td>${e(v.fitness)}</td><td>${e(v.environment_steps ?? '—')}</td><td>${e(v.finish_reason || '')}</td></tr>`).join('')}</tbody></table>`
    if (solver) await view(solver.path, false)
  } catch(error) { get('[data-notice]').hidden = false; get('[data-notice]').textContent = error.message }
}
get('[data-solver]').addEventListener('click', () => view(record.files.find(f => f.name === 'solver.py').path))
get('[data-model]').addEventListener('click', () => view('world_model.md'))
get('[data-files]').addEventListener('click', event => { const button = event.target.closest('[data-file]'); if (button) view(button.dataset.file) })
get('[data-refresh]').addEventListener('click', refresh)
refresh()
