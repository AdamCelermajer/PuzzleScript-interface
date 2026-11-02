import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { escapeHtml as e } from './runs-shared.js'
import { catalogRuns, visibleRuns, loadVisibility, saveVisibility } from './run-organization.mjs'

import { resultsCatalog, fitnessText, outcome } from './run-results.mjs'

const get = s => document.querySelector(s), content = get('[data-game-content]')
let games = [], allRuns = [], selectedId, detail, revision = 0, session = null, busy = false, moves = 0
let preferences = loadVisibility(), showHidden = false
let editor = null, saveMessage = ''
let view = new URLSearchParams(location.search).get('view') === 'compare' ? 'compare' : 'overview'
let compareRunId = new URLSearchParams(location.search).get('compare_run'), comparisonRevision = 0
const pinStorageKey = 'puzzlescript-library-pins-v1'
const initialPins = ['ps_modality-v1', 'ps_knightoban-v1', 'ps_icecrates-v1']
function loadPins() {
  try {
    const saved = localStorage.getItem(pinStorageKey)
    if (saved !== null) {
      const ids = JSON.parse(saved)
      if (Array.isArray(ids)) return new Set(ids.filter(id => typeof id === 'string' && /^ps_[a-z0-9_]+-v\d+$/.test(id)))
    }
  } catch {}
  return new Set(initialPins)
}
let pinnedGames = loadPins()
const enc = encodeURIComponent, pretty = v => String(v || '—').replaceAll('_', ' ')
const date = v => v ? new Date(v).toLocaleString() : 'Date not recorded'
const markdown = text => DOMPurify.sanitize(marked.parse(text || ''))
const notice = text => { get('[data-notice]').textContent = text; get('[data-notice]').hidden = !text }
async function request(path, options = {}) {
  const response = await fetch('/__games/' + path, options)
  const data = await response.json()
  if (!response.ok) throw Object.assign(new Error(data.error || 'Could not load the game library'), { status: response.status })
  return data
}
function gameRuns() { return allRuns.filter(r => r.game_id === selectedId) }
function shownRuns() { return visibleRuns(gameRuns(), preferences, showHidden) }
function pinButton(game, heading = false) {
  const pinned = pinnedGames.has(game.id)
  const label = `${pinned ? 'Unpin' : 'Pin'} ${game.name}`
  return `<button type="button" class="${heading ? 'heading-pin' : 'game-pin'}" data-pin-game="${e(game.id)}" aria-label="${e(label)}" aria-pressed="${pinned}" title="${e(label)}"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z"/><path d="M12 14v7"/></svg>${heading ? `<span>${pinned ? 'Pinned' : 'Pin game'}</span>` : ''}</button>`
}
function updateHeadingPin() {
  const button = content.querySelector('.game-heading [data-pin-game]')
  if (!button || !detail) return
  const pinned = pinnedGames.has(selectedId), label = `${pinned ? 'Unpin' : 'Pin'} ${detail.name}`
  button.setAttribute('aria-pressed', String(pinned)); button.setAttribute('aria-label', label); button.title = label
  button.querySelector('span').textContent = pinned ? 'Pinned' : 'Pin game'
}
function togglePin(id) {
  if (pinnedGames.has(id)) pinnedGames.delete(id)
  else pinnedGames.add(id)
  try { localStorage.setItem(pinStorageKey, JSON.stringify([...pinnedGames])) } catch { notice('Pin changes will last only until this page closes because browser storage is unavailable.') }
  renderMenu(); updateHeadingPin()
}
function renderMenu() {
  const collection = get('[data-collection]').value, query = get('[data-search]').value.trim().toLowerCase()
  const matches = g => `${g.name} ${g.id} ${g.difficulty}`.toLowerCase().includes(query)
  const pinned = [...pinnedGames].map(id => games.find(g => g.id === id)).filter(g => g && matches(g))
  const filtered = games.filter(g => !pinnedGames.has(g.id) && (collection === 'all' || g.collections.includes(collection)) && matches(g))
  const row = g => `<div class="game-choice-row"><button type="button" class="game-choice" data-game="${e(g.id)}" ${g.id === selectedId ? 'aria-current="true"' : ''}><span>${e(g.name)}</span><small>${e(pretty(g.difficulty))}${allRuns.some(r => r.game_id === g.id) ? ' · runs' : ''}</small></button>${pinButton(g)}</div>`
  get('[data-library-count]').textContent = pinned.length + filtered.length
  get('[data-game-list]').innerHTML = `${pinned.length ? `<p class="game-group-label">Pinned games</p>${pinned.map(row).join('')}` : ''}${filtered.length ? `<p class="game-group-label">${pinned.length ? 'Other games' : 'Games'}</p>${filtered.map(row).join('')}` : ''}` || '<p class="muted">No games match.</p>'
}
async function closeSession() {
  const old = session; session = null
  if (old) await fetch(`/__games/play?session=${enc(old)}`, { method: 'DELETE', keepalive: true }).catch(() => {})
}
async function selectGame(id) {
  if (editor) { editor.element.querySelector('[data-editor-status]').textContent = 'Save or cancel this note before switching games.'; editor.element.scrollIntoView({ block: 'center' }); return }
  const ticket = ++revision
  const previousId = selectedId
  void closeSession(); busy = false; moves = 0; selectedId = id; detail = null; saveMessage = ''; ++comparisonRevision; renderMenu()
  const url = new URL(location.href); url.searchParams.set('game', id)
  if (previousId && previousId !== id) { compareRunId = null; url.searchParams.delete('compare_run') }
  history.replaceState(null, '', url)
  content.innerHTML = '<p class="library-empty">Loading the game notebook…</p>'
  try {
    const result = await request(`detail?game=${enc(id)}`)
    if (ticket !== revision) return
    detail = result; renderGame()
  } catch (error) { if (ticket === revision) content.innerHTML = `<p class="library-empty">${e(error.message)}</p>` }
}
function section(name, hint, body, attributes = '') {
  if (attributes === 'data-play-section') return `<section class="notebook-section play-section" data-play-section><header><h3>${name}</h3><small>${hint}</small></header><div class="section-content">${body}</div></section>`
  return `<details class="notebook-section" ${attributes}><summary><span>${name}</span><small>${hint}</small></summary><div class="section-content">${body}</div></details>`
}
function renderGame() {
  const goals = detail.goals, answerCount = goals.studies.reduce((sum, study) => sum + study.answers.length, 0)
  content.innerHTML = `<header class="game-heading"><div class="game-tags"><span>${e(pretty(detail.difficulty))}</span><span data-game-levels ${detail.levels == null ? 'hidden' : ''}>${detail.levels ?? ''} playable levels</span></div><h2>${e(detail.name)}</h2><p>${e(detail.id)}</p>${pinButton(detail, true)}</header>
    <div class="game-view-tabs" role="tablist" aria-label="Game inspection views"><button type="button" role="tab" data-game-view="overview" aria-controls="game-overview">Game notebook</button><button type="button" role="tab" data-game-view="compare" aria-controls="game-comparison">Rule comparison</button></div>
    <div id="game-overview" role="tabpanel" data-game-panel="overview">
    ${section('Play', 'Explore at your own pace', `<div class="play-toolbar"><button class="primary" data-play-start>Start playing</button><label data-level-label hidden>Level <select data-level aria-label="Playable level"></select></label><button data-play-end hidden>End session</button><span data-play-status role="status">A fresh game, ready when you are.</span></div><div class="play-board" data-board tabindex="0" aria-label="Game board. Arrow keys to move, Space to act, Z to undo, R to restart."><p data-play-placeholder>Discover the mechanics yourself.<br><small>The rule notes stay folded until you open them.</small></p><img data-play-image hidden alt="Current game board"></div><div class="play-controls" data-play-controls hidden><div class="direction-pad"><button data-action="ACTION1" aria-label="Move up">↑</button><button data-action="ACTION3" aria-label="Move left">←</button><button data-action="ACTION2" aria-label="Move down">↓</button><button data-action="ACTION4" aria-label="Move right">→</button></div><button data-action="ACTION5">Action · Space</button><button data-action="ACTION7">Undo · Z</button><button data-action="RESET">Restart · R</button></div><p class="muted play-help">Click the board to use the keyboard. You can also use the buttons or choose any level.</p>`, 'data-play-section')}
    ${section('Experiments', `${gameRuns().length} agent runs · ${detail.searches.length} search results · ${detail.legacy.length} rule archives`, '<div data-experiments></div>', 'data-experiment-section')}
    ${section('Rules & understanding', `${detail.rules.length} reviewed rules · agent notes`, '<div data-rules></div>')}
    ${section('Goal recognition', `${goals.studies.length} studies · ${answerCount} model answers · ${goals.human_answers.length} human answers`, renderGoals())}</div>
    <div id="game-comparison" role="tabpanel" data-game-panel="compare" data-rule-comparison hidden></div>`
  renderExperiments(); renderRules()
  applyView()
}
function applyView() {
  content.querySelectorAll('[data-game-view]').forEach(tab => {
    tab.setAttribute('aria-selected', String(tab.dataset.gameView === view))
    tab.tabIndex = tab.dataset.gameView === view ? 0 : -1
  })
  content.querySelectorAll('[data-game-panel]').forEach(panel => { panel.hidden = panel.dataset.gamePanel !== view })
  if (view === 'compare') renderComparison()
  else ++comparisonRevision
}
function compareRuns() {
  return shownRuns().filter(run => run.kind === 'avo').sort((a, b) =>
    Number(Boolean(b.solved)) - Number(Boolean(a.solved)) ||
    Number(b.best_fitness ?? -1) - Number(a.best_fitness ?? -1) ||
    String(b.created_at || b.modified || '').localeCompare(String(a.created_at || a.modified || '')))
}
function renderComparison() {
  const target = get('[data-rule-comparison]')
  if (!target || !detail) return
  const runs = compareRuns()
  if (!runs.some(run => run.id === compareRunId)) compareRunId = runs[0]?.id || null
  const selected = runs.find(run => run.id === compareRunId)
  const source = detail.source_rules
  const study = ['ps_modality-v1', 'ps_knightoban-v1', 'ps_icecrates-v1'].includes(selectedId)
    ? `<a href="/runs/mechanics.html?game=${enc(selectedId)}">Three-game assessment ↗</a>` : ''
  target.innerHTML = `<header class="rule-comparison-heading"><div><h3>Source rules beside the agent report</h3><p>Reviewed notes summarize the game source. The report records what the selected agent stated; inspect its run for the experiments behind it.</p></div>${study}</header>
    <div class="rule-comparison-toolbar">${runs.length ? `<label>Agent run<select data-compare-run aria-label="Agent run to compare">${runs.map(run => `<option value="${e(run.id)}" ${run.id === compareRunId ? 'selected' : ''}>${e(run.model || 'AVO')} · ${e(fitnessText(run.best_fitness, run.win_levels))} · ${e(date(run.created_at || run.modified))} · ${e(run.id.split('/').slice(-3).join('/'))}</option>`).join('')}</select></label><div class="link-row"><a href="${e(runLink(selected))}">Replay run ↗</a><a href="/runs/submission.html?run=${enc(selected.id)}">Solver & report ↗</a></div>` : '<p class="muted">No AVO run is available to compare yet.</p>'}</div>
    <div class="rule-comparison-grid"><article class="rule-comparison-card"><p class="eyebrow">GAME SOURCE</p><h4>Actual mechanics</h4>${detail.rules.length ? `<ol class="rule-list">${detail.rules.map(rule => `<li>${e(rule.replace(/^\d+\.\s*/, ''))}</li>`).join('')}</ol>` : '<p>No reviewed rule notes are available for this game.</p>'}<p class="source-path">Reviewed notes: ${e(detail.rule_source)}</p>${source ? `<details><summary>Show exact PuzzleScript rules and win conditions</summary><p class="source-path">${e(source.source)}:${source.rules_line}</p><pre>${e(source.rules)}</pre><p class="source-path">Win conditions, line ${source.win_line}</p><pre>${e(source.winconditions)}</pre></details>` : '<p class="muted">PuzzleScript source rules are unavailable for this game.</p>'}</article>
    <article class="rule-comparison-card"><p class="eyebrow">AGENT OUTPUT</p><h4>Reported world model</h4><div data-compare-report class="markdown-body" aria-live="polite">${selected ? 'Loading selected report…' : 'No visible AVO runs for this game.'}</div></article></div>`
  if (selected) void loadComparisonReport(selected.id)
}
async function loadComparisonReport(runId) {
  const ticket = ++comparisonRevision
  const target = get('[data-compare-report]')
  const artifact = async path => {
    const response = await fetch(`/__avo/artifact?run=${enc(runId)}&path=${enc(path)}`)
    if (response.status === 404) return null
    const data = await response.json()
    if (!response.ok) throw new Error(data.error || `Could not load ${path}`)
    return data
  }
  try {
    const [report, metadata] = await Promise.all([artifact('world_model.md'), artifact('world_model.json')])
    if (ticket !== comparisonRevision || runId !== compareRunId || !target?.isConnected) return
    if (!report) { target.textContent = 'No final world-model report was saved for this run. Open its replay or logs to inspect intermediate hypotheses.'; return }
    let meta = null
    try { meta = metadata ? JSON.parse(metadata.content) : null } catch {}
    const provenance = meta?.provenance === 'reconstructed_from_saved_outer_history'
      ? 'This report was reconstructed after the experiment from its saved outer-agent history. Use the run notes and replay for contemporaneous evidence.'
      : meta?.mode ? `Report mode: ${meta.mode}.` : 'Report provenance was not recorded.'
    target.innerHTML = `<p class="comparison-provenance">${e(provenance)}</p>${markdown(report.content)}${report.truncated ? '<p class="muted">Preview truncated. Open the full run to inspect all artifacts.</p>' : ''}`
  } catch (error) { if (ticket === comparisonRevision && target?.isConnected) target.textContent = error.message }
}
function runLink(r) { return r.href || `/runs/detail.html?run=${enc(r.id)}` }
function renderExperiments() {
  get('[data-experiment-section]>summary>small').textContent = `${gameRuns().length} agent runs · ${detail.searches.length} search results · ${detail.legacy.length} rule archives`
  get('[data-experiments]').innerHTML = `<div class="experiment-toolbar"><label><input type="checkbox" data-show-failed ${preferences.showFailed ? 'checked' : ''}> Show failed / cancelled</label><label><input type="checkbox" data-show-hidden ${showHidden ? 'checked' : ''}> Show hidden</label><button data-refresh-runs>Refresh runs</button><a href="/runs/compare.html?game=${enc(selectedId)}">Compare runs ↗</a></div><p class="muted">${shownRuns().length} of ${gameRuns().length} agent runs visible. Visibility follows your Runs preferences.</p>
    ${shownRuns().map(r => `<details class="evidence-row"><summary><span><strong>${e(r.model || r.kind)}</strong><small>${e(r.comparison ? 'Comparison' : r.kind === 'avo' ? 'AVO' : 'Direct player')} · ${e(r.effort || r.config?.reasoning_effort || '—')} · ${e(r.world_model_mode || r.condition || '—')}</small></span><span class="result-pill">${r.kind === 'avo' ? `Fitness ${e(fitnessText(r.best_fitness, r.win_levels))}` : `${e(fitnessText(r.levels, r.win_levels))} levels`}<small>${outcome(r).label} · ${e(r.status)}</small></span></summary><div class="evidence-body"><p>${e(date(r.created_at || r.modified))}</p><p class="source-path">${e(r.id)}</p><div class="link-row"><a href="${e(runLink(r))}">Inspect run & replay ↗</a>${r.kind === 'avo' ? `<a href="/games/?game=${enc(selectedId)}&view=compare&compare_run=${enc(r.id)}">Compare its rules ↗</a><a href="/runs/submission.html?run=${enc(r.id)}">Solver & report ↗</a>` : ''}${r.comparison ? `<a href="/runs/compare.html?job=${enc(r.batch)}&game=${enc(selectedId)}">Compare this launch ↗</a>` : ''}</div></div></details>`).join('') || '<p class="muted">No visible agent runs for this game.</p>'}
    ${section('Search experiments', `${detail.searches.length} records`, detail.searches.map(s => `<details class="evidence-row"><summary><span>${e(s.solver)}<small>${e(date(s.date))} · engine level ${e(s.levelIndex)}</small></span><span>${e(s.status)}</span></summary><div class="evidence-body"><p>${s.solved ? 'Solved' : 'Not solved'} · ${s.optimalityProven ? 'Optimality proven' : 'Optimality not established'} · ${e(s.solutionDepth ?? '—')} moves · ${s.searchMs == null ? '—' : (s.searchMs / 1000).toFixed(1)}s</p><p class="source-path">${e(s.source)}</p><a href="/experiments/optimal-path.html">Open search workbench ↗</a></div></details>`).join('') || '<p class="muted">No saved search results for this game.</p>')}
    <p class="muted">Historical rule-learning archives appear under Rules & understanding. Goal-study runs have their own section below.</p>`
}
function editableNote(kind, index, body, label) {
  return `<div class="editable-note" data-edit-kind="${kind}" data-note-index="${index}" tabindex="0" aria-label="${e(label)}. Double-click or press Enter to edit" title="Double-click to edit the source note">${body}</div>`
}
function mechanicNote(m) {
  return editableNote('mechanic', m.source_index, `<p><strong>${e(m.mechanic)}</strong><br>${e(m.evidence)}<br><small>Introduction: ${e(m.introduction)} · Levels: ${e(m.levels)}</small></p>`, m.mechanic)
}
function renderRules() {
  if (editor) return
  const target = get('[data-rules]')
  const expanded = new Set([...target.querySelectorAll('[data-note-panel][open]')].map(d => d.dataset.notePanel))
  target.innerHTML = `<p class="muted">Double-click a reviewed rule or level note to edit its source. Ctrl/⌘+Enter saves; Esc cancels.</p><p class="notebook-save-status" data-save-status role="status">${e(saveMessage)}</p>
    ${section('Reviewed game rules', detail.rules.length ? `${detail.rules.length} notes` : 'No reviewed notes yet', detail.rules.length ? `<p class="muted">Our source-reviewed mechanic notes. Level exposure and replay evidence are recorded separately.</p><ol class="rule-list">${detail.rules.map((rule, i) => `<li>${editableNote('rule', i, e(rule.replace(/^\d+\.\s*/, '')), `Reviewed rule ${i + 1}`)}</li>`).join('')}</ol><p class="source-path">${e(detail.rule_source)}</p>` : '<p class="muted">This older collection has no reviewed rule notebook yet.</p>', 'data-note-panel="reviewed"')}
    ${section('Mechanics by level', `${detail.annotations.length} annotated levels`, `<p class="muted">${e(detail.annotation_method)}</p><p class="source-path">${e(detail.annotation_source)}</p>${detail.annotations.map(l => `<details class="evidence-row" data-note-panel="level-${l.level}"><summary>Level ${l.level}<small>${l.mechanics.length} mechanic notes</small></summary><div class="evidence-body">${l.focus ? editableNote('focus', l.level - 1, `<p><strong>Level focus</strong><br>${e(l.focus)}</p>`, `Level ${l.level} focus`) : ''}${l.mechanics.map(mechanicNote).join('')}</div></details>`).join('')}
    ${(detail.mechanic_sources || []).some(m => m.levels === 'none') ? `<details class="evidence-row" data-note-panel="unexposed"><summary>Not exposed in current levels</summary><div class="evidence-body">${detail.mechanic_sources.filter(m => m.levels === 'none').map(mechanicNote).join('')}</div></details>` : ''}`, 'data-note-panel="levels"')}
    ${section('Agent-inferred world models', `${shownRuns().filter(r => r.kind === 'avo').length} runs`, `<p class="muted">What each agent inferred during its run. These reports can contain incorrect or incomplete rules.</p>${shownRuns().filter(r => r.kind === 'avo').map(r => `<details class="evidence-row" data-world-model="${e(r.id)}"><summary><span>${e(r.model)} · ${e(r.effort)}<small>${e(r.world_model_mode)} · ${e(date(r.created_at || r.modified))}</small></span><small>Fitness ${e(fitnessText(r.best_fitness, r.win_levels))}</small></summary><div class="evidence-body markdown-body" data-world-content>Open to load this run’s report.</div></details>`).join('') || '<p class="muted">No visible AVO runs for this game.</p>'}`)}
    ${section('Historical rule-learning archives', `${detail.legacy.length} records`, detail.legacy.map(r => `<details class="evidence-row"><summary><span>${e(r.id.split('/').at(-1))}<small>${e(r.config.model || 'Archived rule agent')}</small></span><small>${r.natural?.rules?.length ?? 0} natural rules</small></summary><div class="evidence-body"><p class="source-path">${e(r.id)}</p>${(r.natural?.rules || []).map(rule => `<p><strong>${e(rule.id)} · ${e(rule.status)}</strong><br>${e(rule.summary)}</p>`).join('')}<details><summary>Logical rule data</summary><pre>${e(JSON.stringify(r.rules, null, 2))}</pre></details></div></details>`).join('') || '<p class="muted">No archived rule-learning sessions for this game.</p>')}`
  target.querySelectorAll('[data-note-panel]').forEach(d => { d.open = expanded.has(d.dataset.notePanel) })
}
function beginEdit(element) {
  if (!element || editor) return
  const kind = element.dataset.editKind, index = Number(element.dataset.noteIndex)
  let before, fields
  if (kind === 'rule') {
    before = detail.rules[index]; fields = [['value', 'Reviewed rule', before.replace(/^\d+\.\s*/, ''), true]]
  } else if (kind === 'focus') {
    before = detail.annotations.find(l => l.level === index + 1).focus; fields = [['value', 'Level focus', before, true]]
  } else {
    const { source_index, ...original } = detail.mechanic_sources.find(m => m.source_index === index)
    before = original
    fields = [['mechanic', 'Mechanic', original.mechanic], ['evidence', 'Evidence / note', original.evidence, true], ['introduction', 'First / teaching level', original.introduction], ['levels', 'Applies to levels', original.levels]]
  }
  editor = { element, kind, index, before, game: selectedId, saving: false }
  element.classList.add('is-editing')
  element.innerHTML = `<form class="note-editor" data-note-editor><p class="muted">${kind === 'mechanic' ? 'This mechanic is shared by its listed levels. Saving updates each occurrence.' : 'Save changes directly to the original note file.'}</p>${fields.map(([name, label, value, multiline]) => `<label>${label}${multiline ? `<textarea name="${name}" rows="5" required maxlength="16000">${e(value)}</textarea>` : `<input name="${name}" value="${e(value)}" required maxlength="16000">`}</label>`).join('')}<div class="note-editor-actions"><button class="primary" type="submit">Save</button><button type="button" data-cancel-edit>Cancel</button><span data-editor-status role="status"></span></div></form>`
  element.querySelector('textarea,input').focus()
}
function cancelEdit() {
  if (!editor || editor.saving) return
  editor = null; renderRules()
  get('[data-save-status]').textContent = 'Edit cancelled.'
}
async function saveEdit(form) {
  if (!editor || editor.saving || !form.reportValidity()) return
  const current = editor, values = Object.fromEntries(new FormData(form))
  current.saving = true
  form.querySelectorAll('input,textarea,button').forEach(n => { n.disabled = true })
  form.querySelector('[data-editor-status]').textContent = 'Saving…'
  try {
    const result = await request('notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game: current.game, kind: current.kind, index: current.index, before: current.before, value: current.kind === 'mechanic' ? values : values.value }) })
    detail.rules = result.rules; detail.annotations = result.annotations; detail.mechanic_sources = result.mechanic_sources
    saveMessage = `Saved to ${result.file}`
    editor = null; renderRules()
  } catch (error) {
    current.saving = false
    form.querySelectorAll('input,textarea,button').forEach(n => { n.disabled = false })
    form.querySelector('[data-editor-status]').textContent = error.message
    if (error.status === 409) {
      try { const latest = await request(`detail?game=${enc(current.game)}`); detail.rules = latest.rules; detail.annotations = latest.annotations; detail.mechanic_sources = latest.mechanic_sources } catch {}
    }
  }
}
content.addEventListener('dblclick', event => { const element = event.target.closest('[data-edit-kind]'); if (element && !editor) { event.preventDefault(); beginEdit(element) } })
content.addEventListener('click', event => { if (event.target.closest('[data-cancel-edit]')) cancelEdit() })
content.addEventListener('submit', event => { if (event.target.matches('[data-note-editor]')) { event.preventDefault(); void saveEdit(event.target) } })
content.addEventListener('keydown', event => {
  if (event.target.closest('[data-note-editor]')) {
    if (event.key === 'Escape') { event.preventDefault(); cancelEdit() }
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); void saveEdit(event.target.closest('form')) }
  } else if (event.key === 'Enter' && event.target.matches('[data-edit-kind]')) { event.preventDefault(); beginEdit(event.target) }
})
window.addEventListener('beforeunload', event => { if (editor) { event.preventDefault(); event.returnValue = '' } })
function renderGoals() {
  const goals = detail.goals
  return `<p class="muted">Recorded goal guesses from the goal-recognition experiment. Confidence is the model’s own estimate, not an accuracy score.</p>${goals.studies.map(study => section(e(study.id), `${study.answers.length} answers`, study.answers.map(a => `<details class="evidence-row"><summary><span>${e(a.model)}<small>${e(pretty(a.evidence_mode))} · ${e(pretty(a.input_mode))}</small></span><small>${a.prediction?.confidence == null ? '' : `Confidence ${e(a.prediction.confidence)}`}</small></summary><div class="evidence-body"><h4>Goal guess</h4><p>${e(a.prediction?.goal_guess || 'No goal guess recorded.')}</p><h4>Win condition guess</h4><p>${e(a.prediction?.win_condition_guess || 'Not supplied separately.')}</p><h4>Rationale</h4><p>${e(a.prediction?.rationale || 'No rationale recorded.')}</p>${a.prediction?.uncertainties?.length ? `<h4>Uncertainties</h4><ul>${a.prediction.uncertainties.map(u => `<li>${e(u)}</li>`).join('')}</ul>` : ''}</div></details>`).join(''))).join('') || '<p class="muted">No goal-recognition study was recorded for this game.</p>'}
    ${section('Human answers', `${goals.human_answers.length} responses`, goals.human_answers.map((a, i) => `<article class="evidence-body"><h4>Participant ${i + 1}</h4><p>${e(a.answer_text)}</p><small>${e(a.submitted_at)}</small></article>`).join('') || '<p class="muted">No human responses recorded.</p>')}
    ${goals.screenshot || goals.first_frame ? section('Evidence shown to the model', 'Archived first frame', `${goals.screenshot ? `<img class="goal-evidence" loading="lazy" src="${e(goals.screenshot)}" alt="Archived first frame used in the goal study">` : ''}${goals.first_frame ? `<pre>${e(goals.first_frame)}</pre>` : ''}`) : ''}<a href="/experiments/goal-recognition/index.html?game=${enc(selectedId)}">Open the complete goal study ↗</a>`
}
async function play(payload = {}) {
  if (busy) return
  const ticket = revision; busy = true
  get('[data-play-status]').textContent = 'Loading…'
  try {
    const result = await request('play', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game: selectedId, session, ...payload }) })
    if (ticket !== revision) { void fetch(`/__games/play?session=${enc(result.session)}`, { method: 'DELETE' }); return }
    session = result.session; moves = payload.action ? moves + 1 : 0
    get('[data-game-levels]').textContent = `${result.levels} playable levels`; get('[data-game-levels]').hidden = false
    get('[data-play-image]').src = result.image.data_url; get('[data-play-image]').hidden = false
    get('[data-play-placeholder]').hidden = true; get('[data-play-start]').hidden = true
    get('[data-play-end]').hidden = false; get('[data-play-controls]').hidden = false; get('[data-level-label]').hidden = false
    get('[data-level]').innerHTML = Array.from({ length: result.levels }, (_, i) => `<option value="${i}" ${i === result.level ? 'selected' : ''}>${i + 1}</option>`).join('')
    get('[data-play-status]').textContent = `${result.state === 'WIN' ? 'Game complete' : `Level ${result.level + 1} of ${result.levels}`} · ${moves} inputs`
    document.querySelectorAll('[data-action]').forEach(button => { button.disabled = !result.available_actions.includes(button.dataset.action) && button.dataset.action !== 'RESET' })
    get('[data-board]').focus({ preventScroll: true })
  } catch (error) { if (ticket === revision) { void closeSession(); get('[data-play-start]').hidden = false; get('[data-play-controls]').hidden = true; get('[data-level-label]').hidden = true; get('[data-play-status]').textContent = error.message } }
  finally { if (ticket === revision) busy = false }
}
async function refreshRuns() {
  const catalog = await resultsCatalog(); allRuns = catalogRuns(catalog); renderMenu()
  if (detail) { renderExperiments(); renderRules(); if (view === 'compare') renderComparison() }
}
get('[data-search]').addEventListener('input', renderMenu)
get('[data-collection]').addEventListener('change', renderMenu)
get('[data-game-list]').addEventListener('click', event => {
  const pin = event.target.closest('[data-pin-game]')
  if (pin) { togglePin(pin.dataset.pinGame); return }
  const button = event.target.closest('[data-game]')
  if (button) void selectGame(button.dataset.game)
})
get('[data-nav-toggle]').addEventListener('click', event => { const hidden = document.body.classList.toggle('library-nav-collapsed'); event.target.setAttribute('aria-expanded', String(!hidden)) })
document.body.classList.add('library-nav-collapsed')
content.addEventListener('click', event => {
  const pin = event.target.closest('[data-pin-game]')
  if (pin) { togglePin(pin.dataset.pinGame); return }
  const tab = event.target.closest('[data-game-view]')
  if (tab) {
    view = tab.dataset.gameView
    const url = new URL(location.href)
    if (view === 'compare') url.searchParams.set('view', 'compare')
    else url.searchParams.delete('view')
    history.replaceState(null, '', url)
    applyView()
  }
  if (event.target.closest('[data-play-start]')) void play()
  if (event.target.closest('[data-play-end]')) {
    ++revision; void closeSession(); busy = false
    for (const name of ['play-end', 'play-controls', 'level-label', 'play-image']) get(`[data-${name}]`).hidden = true
    get('[data-play-start]').hidden = false; get('[data-play-placeholder]').hidden = false; get('[data-play-status]').textContent = 'Session ended. Start again whenever you like.'
  }
  const action = event.target.closest('[data-action]'); if (action) void play({ action: action.dataset.action })
  if (event.target.closest('[data-refresh-runs]')) void refreshRuns().catch(error => notice(error.message))
})
content.addEventListener('change', event => {
  if (event.target.matches('[data-compare-run]')) { compareRunId = event.target.value; const url = new URL(location.href); url.searchParams.set('compare_run', compareRunId); history.replaceState(null, '', url); renderComparison() }
  if (event.target.matches('[data-level]')) void play({ level: Number(event.target.value) })
  if (event.target.matches('[data-show-failed]')) { preferences.showFailed = event.target.checked; try { saveVisibility(preferences) } catch {} renderExperiments(); renderRules(); if (view === 'compare') renderComparison() }
  if (event.target.matches('[data-show-hidden]')) { showHidden = event.target.checked; renderExperiments(); renderRules(); if (view === 'compare') renderComparison() }
})
content.addEventListener('keydown', event => {
  if (event.target.matches('[data-game-view]') && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    const next = event.key === 'ArrowLeft' || event.key === 'Home' ? 'overview' : 'compare'
    const tab = content.querySelector(`[data-game-view="${next}"]`)
    tab.click(); tab.focus()
    return
  }
  if (!event.target.matches('[data-board]') || !session) return
  const action = { ArrowUp: 'ACTION1', ArrowDown: 'ACTION2', ArrowLeft: 'ACTION3', ArrowRight: 'ACTION4', ' ': 'ACTION5', z: 'ACTION7', r: 'RESET' }[event.key]
  if (action) { event.preventDefault(); if (!event.repeat && !get(`[data-action="${action}"]`).disabled) void play({ action }) }
})
content.addEventListener('toggle', async event => {
  const element = event.target
  if (!element.matches('[data-world-model]') || !element.open || element.dataset.loaded) return
  element.dataset.loaded = 'true'
  const target = element.querySelector('[data-world-content]'); target.textContent = 'Loading report…'
  try {
    const response = await fetch(`/__avo/artifact?run=${enc(element.dataset.worldModel)}&path=world_model.md`)
    if (response.status === 404) { target.textContent = 'No final world-model report was saved for this run. Its trace may contain intermediate hypotheses.'; return }
    const artifact = await response.json()
    if (!response.ok) throw new Error(artifact.error || 'Report could not be loaded')
    target.innerHTML = markdown(artifact.content) + (artifact.truncated ? '<p>Report preview truncated. Open the full run to read more.</p>' : '')
  } catch (error) { target.textContent = error.message; delete element.dataset.loaded }
}, true)
window.addEventListener('pagehide', () => { void closeSession() })
window.addEventListener('storage', () => { preferences = loadVisibility(); if (detail) { renderExperiments(); renderRules(); if (view === 'compare') renderComparison() } })
async function init() {
  const results = await Promise.allSettled([request('catalog'), resultsCatalog()])
  if (results[0].status === 'rejected') { notice(results[0].reason.message); return }
  games = results[0].value.games
  if (results[1].status === 'fulfilled') allRuns = catalogRuns(results[1].value)
  else notice('Game library available; agent-run catalog could not load. Use Refresh runs to retry.')
  get('[data-collection]').innerHTML = results[0].value.collections.map(c => `<option value="${e(c.id)}">${e(c.name)}</option>`).join('') + '<option value="all">All benchmark collections</option>'
  const requested = new URLSearchParams(location.search).get('game'), game = games.find(g => g.id === requested) || games[0]
  if (game && !game.collections.includes('current')) get('[data-collection]').value = 'all'
  renderMenu(); if (game) await selectGame(game.id)
}
void init()

