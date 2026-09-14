const arcColors = [
  '#111820', '#2962a8', '#d13e35', '#2f9d62', '#e2b53f', '#7e8790', '#c85aa1', '#ef8d32',
  '#56b9c9', '#754b33', '#d7dde1', '#8fb1db', '#ef938b', '#8bd0a7', '#f4d978', '#ffffff',
]

const root = document.querySelector('[data-avo-console]')
const state = {
  runId: new URLSearchParams(location.search).get('run') || '', loadedRunId: '', run: null, runs: [], runPinned: Boolean(new URLSearchParams(location.search).get('run')), timer: null, refreshing: false, runsRefreshing: false, runRequestToken: 0, runAbortController: null,
  frameSession: '', framePinned: false, frameRevision: '', frameLoadingRevision: '', frameRequestToken: 0, frameAbortController: null,
  logScope: '', logStream: 'session', logPage: 0, logEntries: [], logMeta: null, logRevision: '', logRequestToken: 0, logSearchTimer: null,
  artifacts: [], selectedArtifact: '',
  replayStep: null, replayTimer: null, replayPlaying: false, replayToken: 0,
}

function pauseReplay() {
  state.replayPlaying = false
  state.replayToken += 1
  clearTimeout(state.replayTimer)
  setText('[data-replay-play]', 'Play')
}

function selectedSession() {
  return state.run?.frame_sessions?.find(session => frameSessionKey(session) === state.frameSession)
}

function frameRevision(session) {
  return `${state.runId}:${state.frameSession}:${state.replayStep === null ? `${session.revision}:${session.actions}` : `step:${state.replayStep}`}`
}

async function showReplayStep(step) {
  const session = selectedSession()
  if (!session) return
  state.framePinned = true
  state.replayStep = Math.max(0, Math.min(Number(step), session.actions))
  root.querySelector('[data-frame-session]').value = state.frameSession
  await loadRenderedFrame(session, frameRevision(session), { force: true })
}

async function playNextFrame(token = state.replayToken) {
  if (!state.replayPlaying || token !== state.replayToken) return
  const session = selectedSession()
  if (!session) return pauseReplay()
  const next = state.replayStep === null || state.replayStep >= session.actions ? 0 : state.replayStep + 1
  await showReplayStep(next)
  if (!state.replayPlaying || token !== state.replayToken) return
  if (state.replayStep >= session.actions) return pauseReplay()
  state.replayTimer = setTimeout(() => playNextFrame(token), 500)
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]))
}

function setText(selector, value) {
  const element = root.querySelector(selector)
  if (element) element.textContent = value
}

function shortRunName(value) {
  const name = String(value || '')
  return name.length > 64 ? `${name.slice(0, 36)}…${name.slice(-24)}` : name
}

function formatTime(value) {
  if (!value) return 'No activity recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return `Updated ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
}

function setConnection(kind, label) {
  const connection = root.querySelector('.avo-connection')
  connection.dataset.connectionState = kind
  setText('[data-connection-label]', label)
}

function setRunStatus(kind, label) {
  const pill = root.querySelector('.avo-live-pill')
  pill.dataset.runStatus = kind
  setText('[data-run-status-label]', label)
}

function selectView(view) {
  if (view !== 'live') pauseReplay()
  root.querySelectorAll('[data-avo-view]').forEach((button) => button.classList.toggle('active', button.dataset.avoView === view))
  root.querySelectorAll('[data-avo-panel]').forEach((panel) => {
    const active = panel.dataset.avoPanel === view
    panel.hidden = !active
    panel.classList.toggle('active', active)
  })
  if (view === 'logs') loadLogs({ reset: true })
  if (view === 'artifacts' && !state.artifacts.length) loadArtifacts()
}

function renderGridFrame(frame, label = 'Grid fallback') {
  const container = root.querySelector('[data-game-frame]')
  const frames = Array.isArray(frame) ? frame : []
  const grid = Array.isArray(frames.at(-1)) ? frames.at(-1) : []
  if (!grid.length) {
    container.innerHTML = '<p>No live frame yet.</p>'
    return
  }
  const columns = Math.max(...grid.map((row) => Array.isArray(row) ? row.length : 0), 1)
  container.innerHTML = `<div class="avo-rendered-frame"><div class="avo-arc-grid" style="--grid-columns:${columns}">${grid.flatMap((row) => row.map((value) => `<span title="${escapeHtml(value)}" style="--cell-color:${arcColors[Number(value)] || '#6c7780'}"></span>`)).join('')}</div><span class="avo-frame-source">${escapeHtml(label)}</span></div>`
}

function renderPngFrame(renderedFrame, candidateId, phase) {
  const container = root.querySelector('[data-game-frame]')
  if (!renderedFrame?.data_url) return false
  const dimensions = renderedFrame.width && renderedFrame.height ? ` width="${Number(renderedFrame.width)}" height="${Number(renderedFrame.height)}"` : ''
  container.innerHTML = `<figure class="avo-rendered-frame"><img src="${escapeHtml(renderedFrame.data_url)}" alt="Full textured PuzzleScript frame for ${escapeHtml(candidateId)} ${escapeHtml(phase)}"${dimensions} /><figcaption class="avo-frame-source">Real PuzzleScript PNG</figcaption></figure>`
  return true
}

function renderLineage(run) {
  const candidates = run.candidates || []
  setText('[data-lineage-count]', `${candidates.length} candidate${candidates.length === 1 ? '' : 's'}`)
  const container = root.querySelector('[data-lineage]')
  if (!candidates.length) {
    container.innerHTML = '<p class="avo-empty">No candidate has been registered.</p>'
    return
  }
  container.innerHTML = candidates.slice().reverse().map((candidate, reverseIndex) => {
    const index = candidates.length - reverseIndex
    const status = candidate.candidate_id === run.current ? run.phase.replaceAll('_', ' ') : candidate.evaluated ? 'evaluated' : 'registered'
    const score = candidate.fitness == null ? status : `fitness ${candidate.fitness}`
    const frameSelected = state.frameSession.startsWith(`${candidate.candidate_id}:`)
    return `<article class="lineage-row ${candidate.candidate_id === run.current ? 'current' : ''} ${frameSelected ? 'frame-selected' : ''}" data-frame-candidate="${escapeHtml(candidate.candidate_id)}" title="Replay and inspect this hypothesis" role="button" tabindex="0">
      <span class="lineage-index">${String(index).padStart(2, '0')}</span>
      <div class="lineage-copy"><strong>${escapeHtml(candidate.candidate_id)}</strong><small>${escapeHtml(candidate.parent_ids?.length ? `from ${candidate.parent_ids.join(', ')}` : 'root candidate')}</small></div>
      <span class="lineage-score">${escapeHtml(score)}</span>
    </article>`
  }).join('')
}

function renderActivity(events) {
  const container = root.querySelector('[data-recent-activity]')
  if (!events?.length) {
    container.innerHTML = '<p class="avo-empty">Waiting for the first event.</p>'
    return
  }
  container.innerHTML = events.slice().reverse().map((event) => `<article class="activity-item">
    <span>${escapeHtml(String(event.type || 'event').replaceAll('_', ' '))}</span>
    <strong>${escapeHtml(event.title || event.action || event.type || 'Activity')}</strong>
    <small>${escapeHtml(event.detail || formatTime(event.recorded_at))}</small>
  </article>`).join('')
}

function frameSessionKey(session) {
  return session ? `${session.candidate_id}:${session.phase}` : ''
}

function latestFrameSession(sessions) {
  return sessions.slice().sort((left, right) => {
    const activity = Date.parse(right.last_activity || '') - Date.parse(left.last_activity || '')
    if (Number.isFinite(activity) && activity) return activity
    const candidateOrder = right.candidate_id.localeCompare(left.candidate_id, undefined, { numeric: true })
    if (candidateOrder) return candidateOrder
    if (left.phase !== right.phase) return left.phase === 'evaluation' ? -1 : 1
    return 0
  })[0] || null
}

function renderRun(run) {
  const changedRun = state.loadedRunId && state.loadedRunId !== run.run_id
  state.runId = run.run_id
  state.loadedRunId = run.run_id
  state.run = run
  if (changedRun) {
    pauseReplay()
    state.replayStep = null
    state.frameAbortController?.abort()
    state.frameRequestToken += 1
    state.frameSession = ''
    state.framePinned = false
    state.frameRevision = ''
    state.frameLoadingRevision = ''
    state.logPage = 0
    state.logEntries = []
    state.logMeta = null
    state.logRevision = ''
    state.logRequestToken += 1
    state.artifacts = []
    state.selectedArtifact = ''
  }
  setText('[data-run-title]', run.game_id ? `${run.game_id} · ${run.run_id.split('/').slice(-2).join('/')}` : shortRunName(run.run_id))
  root.querySelector('[data-run-title]').title = run.run_id
  setText('[data-agent-identity]', `${run.agent_backend === 'opencode' ? 'OpenCode' : 'Codex'} · player: ${run.player_model || '—'} · outer: ${run.optimizer_model || '—'}`)
  setText('[data-last-activity]', formatTime(run.last_activity))
  setText('[data-current-candidate]', run.current || '—')
  setText('[data-current-phase]', String(run.phase || 'initializing').replaceAll('_', ' '))
  const finalLink = root.querySelector('[data-final-result]')
  finalLink.hidden = !run.finalized
  finalLink.href = `/runs/submission.html?run=${encodeURIComponent(run.run_id)}`
  root.querySelector('[data-inspect="model"]').disabled = !run.world_model_available
  root.querySelector('[data-inspect="model"]').title = run.world_model_available ? '' : 'No final world model saved for this campaign'
  setText('[data-research-actions]', `${run.research.actions} / ${run.research.budget ?? '—'}`)
  const researchPercent = run.research.budget ? Math.min(100, (run.research.actions / run.research.budget) * 100) : 0
  root.querySelector('[data-research-meter]').style.width = `${researchPercent}%`
  setText('[data-levels]', `${run.research.levels} / ${run.win_levels ?? '—'}`)
  setText('[data-game-state]', run.last_transition?.after?.status || 'NOT STARTED')
  setText('[data-evaluated-count]', `${run.hypotheses_evaluated} / ${run.max_hypotheses ?? '—'}`)
  setText('[data-latest-fitness]', run.latest_fitness == null ? 'No fitness yet' : `Latest fitness ${run.latest_fitness}`)
  const frameSessions = (run.frame_sessions || []).slice().sort((left, right) => {
    const candidateOrder = right.candidate_id.localeCompare(left.candidate_id, undefined, { numeric: true })
    if (candidateOrder) return candidateOrder
    return left.phase === 'research' ? -1 : 1
  })
  const frameSelect = root.querySelector('[data-frame-session]')
  const availableFrameKeys = frameSessions.map(frameSessionKey)
  const liveFrameSession = latestFrameSession(frameSessions)
  if (!state.framePinned || !availableFrameKeys.includes(state.frameSession)) {
    state.framePinned = false
    state.frameSession = frameSessionKey(liveFrameSession)
  }
  const historyOptions = frameSessions.map((session) => {
    const phaseLabel = session.phase === 'research' ? 'inner research' : 'fresh evaluation'
    return `<option value="${escapeHtml(frameSessionKey(session))}">${escapeHtml(`${session.candidate_id} · ${phaseLabel} · ${session.actions} actions`)}</option>`
  }).join('')
  if (liveFrameSession) {
    const livePhase = liveFrameSession.phase === 'research' ? 'research' : 'evaluation'
    frameSelect.innerHTML = `<option value="__live__">${escapeHtml(`Latest frame · ${liveFrameSession.candidate_id} ${livePhase} · ${liveFrameSession.actions} actions`)}</option><optgroup label="Session history">${historyOptions}</optgroup>`
    frameSelect.value = state.framePinned ? state.frameSession : '__live__'
  } else {
    frameSelect.innerHTML = '<option value="">No session yet</option>'
  }
  const selectedFrameSession = state.framePinned
    ? frameSessions.find((session) => frameSessionKey(session) === state.frameSession)
    : liveFrameSession
  if (selectedFrameSession) {
    const revision = frameRevision(selectedFrameSession)
    if (revision !== state.frameRevision && revision !== state.frameLoadingRevision) {
      if (state.replayStep === null) renderGridFrame(selectedFrameSession.fallback_frame, 'Current grid · rendering full PNG…')
      loadRenderedFrame(selectedFrameSession, revision)
    }
  } else {
    setText('[data-frame-step]', 'No transition')
    setText('[data-last-action]', '—')
    setText('[data-frame-state]', '—')
    setText('[data-frame-phase]', '—')
    renderGridFrame(run.last_transition?.after?.payload?.frame)
  }
  renderLineage(run)
  renderActivity(run.recent_activity)
  const scope = root.querySelector('[data-log-scope]')
  const availableScopes = ['outer', ...(run.candidates || []).map((candidate) => candidate.candidate_id)]
  if (!state.logScope || !availableScopes.includes(state.logScope)) state.logScope = run.current || 'outer'
  scope.innerHTML = availableScopes.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value === 'outer' ? 'Outer optimizer' : `${value} · inner player`)}</option>`).join('')
  scope.value = state.logScope
  setRunStatus(run.active ? 'running' : 'idle', run.process_status || 'Unconfirmed')
}

async function loadRenderedFrame(session, revision, { force = false } = {}) {
  if (!state.runId || !session) return
  if (!force && revision === state.frameRevision) return
  const requestToken = ++state.frameRequestToken
  state.frameAbortController?.abort()
  const abortController = new AbortController()
  state.frameAbortController = abortController
  state.frameLoadingRevision = revision
  setText('[data-frame-step]', 'Rendering full PNG…')
  try {
    const stepQuery = state.replayStep === null ? '' : `&step=${state.replayStep}`
    const payload = await fetchJson(`/__avo/frame?run=${encodeURIComponent(state.runId)}&candidate=${encodeURIComponent(session.candidate_id)}&phase=${encodeURIComponent(session.phase)}${stepQuery}`, { signal: abortController.signal })
    if (requestToken !== state.frameRequestToken) return
    state.frameRevision = revision
    state.frameLoadingRevision = ''
    if (!renderPngFrame(payload.rendered_frame, payload.candidate_id, payload.phase)) {
      renderGridFrame(payload.fallback_frame, payload.source === 'stored_observation_grid' ? 'Recorded observation · grid view' : payload.replay_exact ? 'Grid fallback' : 'Replay mismatch · grid fallback')
    }
    const transition = payload.transition || {}
    setText('[data-frame-step]', `${payload.step === 0 ? 'Initial state' : `Action ${payload.step}`} · level ${transition.progress?.levels_completed ?? '—'}`)
    const slider = root.querySelector('[data-replay-position]')
    slider.max = payload.total_actions
    slider.value = payload.step
    setText('[data-replay-position-label]', `${payload.step} / ${payload.total_actions}`)
    setText('[data-inspect-candidate]', payload.candidate_id)
    root.querySelector('[data-inspect="solver"]').disabled = !state.run?.candidates?.find(c => c.candidate_id === payload.candidate_id)?.evaluated
    setText('[data-last-action]', transition.action?.id || '—')
    setText('[data-frame-state]', transition.status || '—')
    setText('[data-frame-phase]', `${payload.candidate_id} · ${payload.phase === 'research' ? 'inner research' : 'fresh evaluation'}`)
    renderLineage(state.run)
  } catch (error) {
    if (error.name === 'AbortError') return
    if (requestToken !== state.frameRequestToken) return
    state.frameLoadingRevision = ''
    pauseReplay()
    root.querySelector('[data-game-frame]').innerHTML = `<p>${escapeHtml(error.message)}</p>`
    setText('[data-frame-step]', 'PNG unavailable')
  }
}

function formatClock(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatBytes(value) {
  const bytes = Number(value) || 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function clipText(value, limit = 12000) {
  const text = String(value || '')
  return text.length > limit ? `${text.slice(0, limit)}\n\n… clipped in the session reader; the complete record remains in Artifacts.` : text
}

function renderChatEntry(entry) {
  if (entry.category === 'conversation') {
    const user = entry.role === 'user'
    return `<article class="chat-message ${user ? 'user' : 'assistant'}" data-log-anchor="${escapeHtml(entry.id)}">
      <span class="chat-avatar" aria-hidden="true">${user ? 'U' : 'C'}</span>
      <div class="chat-message-content">
        <header><strong>${user ? 'Run instruction' : state.run?.agent_backend === 'opencode' ? 'OpenCode' : 'Codex'}</strong><time>${escapeHtml(formatClock(entry.recorded_at))}</time></header>
        <div class="chat-copy">${escapeHtml(clipText(entry.body, 30000))}</div>
      </div>
    </article>`
  }
  if (entry.category === 'tools') {
    return `<details class="chat-tool" data-log-anchor="${escapeHtml(entry.id)}" data-log-open-id="${escapeHtml(entry.id)}">
      <summary>
        <span class="chat-tool-icon" aria-hidden="true">›_</span>
        <div><strong>${escapeHtml(entry.title)}</strong><code>${escapeHtml(entry.summary || entry.kind)}</code></div>
        <small>${escapeHtml(entry.meta || '')}</small><time>${escapeHtml(formatClock(entry.recorded_at))}</time>
      </summary>
      <div class="chat-tool-body">
        ${entry.input && entry.input !== entry.summary ? `<div class="chat-tool-call"><span>Tool call</span><pre>${escapeHtml(clipText(entry.input, 6000))}</pre></div>` : ''}
        <div class="chat-tool-output"><span>Result</span><pre>${escapeHtml(clipText(entry.body || '(no output)'))}</pre></div>
      </div>
    </details>`
  }
  const raw = clipText(JSON.stringify(entry.raw ?? {}, null, 2), 8000)
  return `<details class="telemetry-event" data-category="${escapeHtml(entry.category)}" data-log-anchor="${escapeHtml(entry.id)}" data-log-open-id="${escapeHtml(entry.id)}">
    <summary><i class="trace-type-dot ${escapeHtml(entry.category)}"></i><div><strong>${escapeHtml(entry.title)}</strong><small>${escapeHtml(entry.summary || entry.kind)}</small></div><time>${escapeHtml(formatClock(entry.recorded_at))}</time></summary>
    <div class="telemetry-event-body">${entry.body ? `<pre>${escapeHtml(clipText(entry.body, 8000))}</pre>` : ''}<details data-log-open-id="${escapeHtml(`${entry.id}:raw`)}"><summary>Recorded details</summary><pre>${escapeHtml(raw)}</pre></details></div>
  </details>`
}

function captureLogViewState() {
  const container = root.querySelector('[data-log-groups]')
  const containerTop = container.getBoundingClientRect().top
  const anchor = [...container.querySelectorAll('[data-log-anchor]')].find((element) => element.getBoundingClientRect().bottom >= containerTop)
  return {
    openIds: new Set([...container.querySelectorAll('[data-log-open-id][open]')].map((element) => element.dataset.logOpenId)),
    anchorId: anchor?.dataset.logAnchor || '',
    anchorOffset: anchor ? anchor.getBoundingClientRect().top - containerTop : 0,
    scrollTop: container.scrollTop,
    scrollHeight: container.scrollHeight,
    nearBottom: container.scrollHeight - container.scrollTop - container.clientHeight < 80,
  }
}

function restoreLogViewState(container, viewState) {
  if (!viewState) return
  container.querySelectorAll('[data-log-open-id]').forEach((element) => {
    element.open = viewState.openIds.has(element.dataset.logOpenId)
  })
  if (viewState.nearBottom) {
    container.scrollTop = container.scrollHeight
    return
  }
  container.scrollTop = Math.min(viewState.scrollTop, container.scrollHeight)
  const anchor = [...container.querySelectorAll('[data-log-anchor]')].find((element) => element.dataset.logAnchor === viewState.anchorId)
  if (anchor) {
    const containerTop = container.getBoundingClientRect().top
    container.scrollTop += anchor.getBoundingClientRect().top - containerTop - viewState.anchorOffset
    return
  }
}

function logRevision(payload, entries) {
  return `${state.runId}:${state.logScope}:${state.logStream}:${payload.total}:${JSON.stringify(entries.map(entry => [entry.id, entry.recorded_at, entry.meta, entry.body]))}`
}

function renderLogs(viewState = null) {
  const container = root.querySelector('[data-log-groups]')
  const entries = state.logEntries
  const total = state.logMeta?.total ?? entries.length
  const actor = state.logMeta?.actor || state.logScope || 'Session'
  setText('[data-log-session-name]', actor)
  setText('[data-log-count]', `${total} item${total === 1 ? '' : 's'}`)
  root.querySelector('[data-load-older]').hidden = !state.logMeta?.has_more
  if (!entries.length) {
    setText('[data-log-summary]', `${actor} · no matching ${String(state.logStream).replaceAll('_', ' ')}`)
    container.innerHTML = '<p class="avo-empty">Nothing useful to show in this view.</p>'
    restoreLogViewState(container, viewState)
    return
  }
  if (state.logStream === 'session') {
    const messages = entries.filter((entry) => entry.category === 'conversation').length
    const tools = entries.filter((entry) => entry.category === 'tools').length
    setText('[data-log-summary]', `${actor} · ${messages} message${messages === 1 ? '' : 's'} · ${tools} tool call${tools === 1 ? '' : 's'} · chronological`)
    const turns = new Map()
    entries.forEach((entry) => {
      const turn = entry.turn == null ? 'Session' : `Turn ${entry.turn}`
      if (!turns.has(turn)) turns.set(turn, [])
      turns.get(turn).push(entry)
    })
    container.innerHTML = [...turns.entries()].map(([turn, items]) => `<section class="chat-turn"><div class="chat-turn-divider"><span>${escapeHtml(turn)}</span></div>${items.map(renderChatEntry).join('')}</section>`).join('')
    restoreLogViewState(container, viewState)
    return
  }
  setText('[data-log-summary]', `${actor} · ${String(state.logStream).replaceAll('_', ' ')} · chronological`)
  container.innerHTML = `<div class="telemetry-list">${entries.map(renderChatEntry).join('')}</div>`
  restoreLogViewState(container, viewState)
}

async function loadLogs({ reset = false, live = false } = {}) {
  if (!state.runId || !state.logScope) return
  const requestToken = ++state.logRequestToken
  const viewState = live || !reset ? captureLogViewState() : null
  if (reset) {
    state.logPage = 0
  }
  const page = reset ? 0 : state.logPage + 1
  const search = root.querySelector('[data-log-search]').value.trim()
  if (!live) setText('[data-log-summary]', 'Reading the structured trace…')
  try {
    const payload = await fetchJson(`/__avo/logs?run=${encodeURIComponent(state.runId)}&scope=${encodeURIComponent(state.logScope)}&stream=${encodeURIComponent(state.logStream)}&page=${page}&limit=60&search=${encodeURIComponent(search)}`)
    if (requestToken !== state.logRequestToken) return
    const nextEntries = reset ? payload.entries : [...payload.entries, ...state.logEntries]
    const nextRevision = logRevision(payload, nextEntries)
    if (live && nextRevision === state.logRevision) {
      state.logMeta = payload
      return
    }
    state.logPage = page
    state.logEntries = nextEntries
    state.logMeta = payload
    state.logRevision = nextRevision
    renderLogs(viewState)
  } catch (error) {
    if (requestToken !== state.logRequestToken) return
    root.querySelector('[data-log-groups]').innerHTML = `<p class="avo-empty">${escapeHtml(error.message)}</p>`
  }
}

const artifactSectionOrder = ['Summary', 'Strategy & seed', 'Research session', 'Self-checks', 'Completed solver', 'Fresh evaluation', 'Run setup', 'Outer agent session', 'Outer workspace']

function artifactOwner(artifact) {
  const first = artifact.path.split('/')[0]
  return /^x_\d+$/.test(first) ? first : 'outer'
}

function artifactSectionName(artifact) {
  const parts = artifact.path.split('/')
  if (!/^x_\d+$/.test(parts[0])) {
    if (parts[0] === 'optimizer_analysis') return 'Outer agent session'
    if (parts[0] === 'outer') return 'Outer workspace'
    return 'Run setup'
  }
  if (parts.length === 2 && parts[1] === 'summary.json') return 'Summary'
  if (parts[1] === 'evaluation') return 'Fresh evaluation'
  if (parts[1] === 'solver') return 'Completed solver'
  if (parts[1] === 'research' && parts[2] === 'self_check') return 'Self-checks'
  if (parts[1] === 'research') return 'Research session'
  return 'Strategy & seed'
}

function artifactFriendlyName(artifact) {
  const labels = {
    'STRATEGY.md': 'Strategy', 'summary.json': 'Candidate summary', 'solver.py': 'Solver source',
    'NOTES.md': 'Research notes', 'evidence.jsonl': 'Environment evidence', 'conversation.jsonl': 'Agent conversation',
    'session.json': 'Session metadata', 'prompt.json': 'Session prompt', 'solver_evaluation.json': 'Evaluation result',
    'workspace_changes.jsonl': 'Workspace changes', 'app_server_events.jsonl': 'Raw SDK events', 'agent_events.jsonl': 'Agent events',
  }
  return labels[artifact.name] || artifact.name
}

function renderArtifactFiles(files, owner) {
  return files.map((artifact) => {
    const relative = owner === 'outer' ? artifact.path : artifact.path.slice(owner.length + 1)
    return `<button type="button" class="artifact-file ${artifact.path === state.selectedArtifact ? 'active' : ''}" data-artifact-path="${escapeHtml(artifact.path)}"><b>${escapeHtml(artifactFriendlyName(artifact))}</b><span>${escapeHtml(relative)} · ${formatBytes(artifact.size)}</span></button>`
  }).join('')
}

function renderArtifactTree(filter = '') {
  const container = root.querySelector('[data-artifact-tree]')
  const needle = filter.trim().toLowerCase()
  const artifacts = needle ? state.artifacts.filter((artifact) => `${artifact.path} ${artifact.role}`.toLowerCase().includes(needle)) : state.artifacts
  if (!artifacts.length) {
    container.innerHTML = `<p class="avo-empty">${state.artifacts.length ? 'No matching artifacts.' : 'No readable artifacts found.'}</p>`
    return
  }
  const groups = new Map()
  artifacts.forEach((artifact) => {
    const owner = artifactOwner(artifact)
    if (!groups.has(owner)) groups.set(owner, [])
    groups.get(owner).push(artifact)
  })
  const owners = [...groups.keys()].sort((left, right) => {
    if (left === 'outer') return 1
    if (right === 'outer') return -1
    return right.localeCompare(left, undefined, { numeric: true })
  })
  container.innerHTML = owners.map((owner) => {
    const files = groups.get(owner)
    const candidate = state.run?.candidates?.find((item) => item.candidate_id === owner)
    const selectedOwner = state.selectedArtifact && artifactOwner({ path: state.selectedArtifact }) === owner
    const open = Boolean(needle || selectedOwner || owner === state.run?.current)
    const status = owner === 'outer' ? 'Run-level files and persistent optimizer session'
      : candidate?.fitness == null ? (owner === state.run?.current ? 'Current candidate' : 'Not evaluated') : `Fitness ${candidate.fitness}`
    const sections = new Map()
    files.forEach((artifact) => {
      const section = artifactSectionName(artifact)
      if (!sections.has(section)) sections.set(section, [])
      sections.get(section).push(artifact)
    })
    const orderedSections = [...sections.entries()].sort((left, right) => artifactSectionOrder.indexOf(left[0]) - artifactSectionOrder.indexOf(right[0]))
    return `<details class="artifact-candidate" ${open ? 'open' : ''}>
      <summary><span class="artifact-owner-mark">${owner === 'outer' ? 'A' : escapeHtml(owner.replace('x_00', ''))}</span><div><strong>${escapeHtml(owner === 'outer' ? 'Run & outer optimizer' : owner)}</strong><small>${escapeHtml(status)}</small></div><b>${files.length}</b></summary>
      <div class="artifact-sections">${orderedSections.map(([section, sectionFiles]) => {
        const selectedSection = sectionFiles.some((artifact) => artifact.path === state.selectedArtifact)
        return `<details class="artifact-section" ${needle || selectedSection || section === 'Summary' || section === 'Strategy & seed' ? 'open' : ''}><summary>${escapeHtml(section)}<small>${sectionFiles.length}</small></summary><div class="artifact-files">${renderArtifactFiles(sectionFiles, owner)}</div></details>`
      }).join('')}</div>
    </details>`
  }).join('')
}

async function loadArtifacts(preferredPath = '') {
  if (!state.runId) return
  const container = root.querySelector('[data-artifact-tree]')
  container.innerHTML = '<p class="avo-empty">Indexing this run by lifecycle role…</p>'
  try {
    const payload = await fetchJson(`/__avo/artifacts?run=${encodeURIComponent(state.runId)}`)
    state.artifacts = payload.artifacts || []
    renderArtifactTree(root.querySelector('[data-artifact-search]').value)
    const preferred = state.artifacts.find((artifact) => artifact.path === preferredPath)
      || state.artifacts.find((artifact) => artifact.path === `${state.run?.current}/STRATEGY.md`)
      || state.artifacts.find((artifact) => artifact.path === 'evolution_config.json')
      || state.artifacts[0]
    if (preferred) loadArtifact(preferred.path)
  } catch (error) {
    container.innerHTML = `<p class="avo-empty">${escapeHtml(error.message)}</p>`
  }
}

async function loadArtifact(path) {
  if (!state.runId || !path) return
  state.selectedArtifact = path
  renderArtifactTree(root.querySelector('[data-artifact-search]').value)
  setText('[data-artifact-name]', path)
  setText('[data-artifact-role]', 'Loading artifact')
  root.querySelector('[data-artifact-content]').textContent = 'Reading file…'
  try {
    const artifact = await fetchJson(`/__avo/artifact?run=${encodeURIComponent(state.runId)}&path=${encodeURIComponent(path)}`)
    if (state.selectedArtifact !== path) return
    const meta = state.artifacts.find((item) => item.path === path)
    setText('[data-artifact-role]', meta?.role || 'Run artifact')
    if (path === 'world_model.md') {
      const provenance = await fetchJson(`/__avo/artifact?run=${encodeURIComponent(state.runId)}&path=world_model.json`).catch(() => null)
      if (state.selectedArtifact !== path) return
      try {
        if (JSON.parse(provenance?.content || '{}').provenance === 'reconstructed_from_saved_outer_history') {
          setText('[data-artifact-role]', 'Post-run report reconstructed from saved outer history')
        }
      } catch { /* Older reports may have no structured provenance. */ }
    }
    setText('[data-artifact-name]', path)
    setText('[data-artifact-meta]', `${formatBytes(artifact.size)}${artifact.truncated ? ' · preview truncated at 512 KB' : ''}`)
    root.querySelector('[data-artifact-content]').textContent = artifact.content || '(empty file)'
  } catch (error) {
    setText('[data-artifact-role]', 'Could not open artifact')
    root.querySelector('[data-artifact-content]').textContent = error.message
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { cache: 'no-store', ...options })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`)
  return payload
}

async function loadRun() {
  if (!state.runId) return
  const requestedRunId = state.runId
  const requestToken = ++state.runRequestToken
  state.runAbortController?.abort()
  const abortController = new AbortController()
  state.runAbortController = abortController
  state.refreshing = true
  try {
    const run = await fetchJson(`/__avo/run?run=${encodeURIComponent(requestedRunId)}`, { signal: abortController.signal })
    if (requestToken !== state.runRequestToken || requestedRunId !== state.runId) return
    renderRun(run)
    setConnection('live', 'Local trace connected')
    root.querySelector('[data-console-notice]').hidden = true
    if (!root.querySelector('[data-avo-panel="logs"]').hidden && state.logPage === 0) loadLogs({ reset: true, live: true })
    if (!root.querySelector('[data-avo-panel="artifacts"]').hidden && !state.artifacts.length) loadArtifacts()
  } catch (error) {
    if (error.name === 'AbortError') return
    if (requestToken !== state.runRequestToken) return
    setConnection('error', 'Trace bridge unavailable')
    setRunStatus('error', 'Offline')
    const notice = root.querySelector('[data-console-notice]')
    notice.textContent = `${error.message}. The website and Workbench API must both be running (npm run workbench).`
    notice.hidden = false
  } finally {
    if (requestToken === state.runRequestToken) state.refreshing = false
  }
}

async function loadRuns() {
  if (state.runsRefreshing) return
  state.runsRefreshing = true
  const select = root.querySelector('[data-run-select]')
  try {
    const payload = await fetchJson('/__avo/runs')
    state.runs = payload.runs
    if (!payload.runs.length) {
      select.innerHTML = '<option value="">No evolution runs found</option>'
      setConnection('error', 'No local runs')
      return
    }
    const availableRunIds = payload.runs.map((run) => run.run_id)
    if (state.runPinned && !availableRunIds.includes(state.runId)) {
      // Accept links to the old single-folder IDs without silently selecting another run.
      const legacy = `avo/output/evolution/${state.runId}`
      if (availableRunIds.includes(legacy)) state.runId = legacy
      else throw new Error('Selected run is unavailable')
    }
    if (!state.runPinned) {
      state.runPinned = false
      state.runId = payload.runs[0].run_id
    }
    select.innerHTML = `<option value="__live__">Follow latest · ${escapeHtml(payload.runs[0].label)}</option><optgroup label="Campaigns">${payload.runs.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(`${run.status} · ${run.label}`)}</option>`).join('')}</optgroup>`
    select.value = state.runPinned ? state.runId : '__live__'
    await loadRun()
  } catch (error) {
    select.innerHTML = '<option value="">Live trace unavailable</option>'
    setConnection('error', 'Trace bridge unavailable')
    const notice = root.querySelector('[data-console-notice]')
    notice.textContent = `${error.message}. Run npm run workbench to serve the website and run catalog.`
    notice.hidden = false
  } finally {
    state.runsRefreshing = false
  }
}

root.querySelectorAll('[data-avo-view]').forEach((button) => button.addEventListener('click', () => selectView(button.dataset.avoView)))
root.querySelector('[data-run-select]').addEventListener('change', (event) => {
  state.runPinned = event.target.value !== '__live__'
  state.runId = state.runPinned ? event.target.value : state.runs[0]?.run_id || ''
  loadRun()
})
root.querySelector('[data-refresh-run]').addEventListener('click', loadRuns)
root.querySelector('[data-frame-session]').addEventListener('change', (event) => {
  pauseReplay()
  const sessions = state.run?.frame_sessions || []
  let session
  if (event.target.value === '__live__') {
    state.replayStep = null
    state.framePinned = false
    session = latestFrameSession(sessions)
    state.frameSession = frameSessionKey(session)
  } else {
    state.replayStep = 0
    state.framePinned = true
    state.frameSession = event.target.value
    const [candidateId, phase] = state.frameSession.split(':')
    session = sessions.find((item) => item.candidate_id === candidateId && item.phase === phase)
  }
  state.frameRevision = ''
  if (session) {
    loadRenderedFrame(session, frameRevision(session), { force: true })
  }
  renderLineage(state.run)
})
root.querySelector('[data-lineage]').addEventListener('click', (event) => {
  const row = event.target.closest('[data-frame-candidate]')
  if (!row || !state.run) return
  const candidateId = row.dataset.frameCandidate
  pauseReplay()
  state.replayStep = 0
  const session = (state.run.frame_sessions || []).find((item) => item.candidate_id === candidateId && item.phase === 'evaluation')
    || (state.run.frame_sessions || []).find((item) => item.candidate_id === candidateId)
  if (!session) return
  state.frameSession = `${session.candidate_id}:${session.phase}`
  state.framePinned = true
  state.frameRevision = ''
  root.querySelector('[data-frame-session]').value = state.frameSession
  renderLineage(state.run)
  loadRenderedFrame(session, frameRevision(session), { force: true })
})
root.querySelector('[data-lineage]').addEventListener('keydown', event => {
  if (event.key === 'Enter' || event.key === ' ') {
    const row = event.target.closest('[data-frame-candidate]')
    if (row) { event.preventDefault(); row.click() }
  }
})
root.querySelector('[data-replay-play]').addEventListener('click', () => {
  if (state.replayPlaying) return pauseReplay()
  state.replayPlaying = true
  setText('[data-replay-play]', 'Pause')
  playNextFrame()
})
root.querySelector('[data-replay-start]').addEventListener('click', () => { pauseReplay(); showReplayStep(0) })
root.querySelector('[data-replay-prev]').addEventListener('click', () => { pauseReplay(); showReplayStep((state.replayStep ?? selectedSession()?.actions ?? 0) - 1) })
root.querySelector('[data-replay-next]').addEventListener('click', () => { pauseReplay(); showReplayStep((state.replayStep ?? selectedSession()?.actions ?? 0) + 1) })
root.querySelector('[data-replay-position]').addEventListener('input', event => { pauseReplay(); showReplayStep(event.target.value) })
root.querySelector('[data-replay-latest]').addEventListener('click', () => {
  pauseReplay()
  state.replayStep = null
  state.framePinned = false
  if (state.run) renderRun(state.run)
})
root.querySelectorAll('[data-inspect]').forEach(button => button.addEventListener('click', async () => {
  pauseReplay()
  const candidate = selectedSession()?.candidate_id || state.run?.current
  if (button.dataset.inspect === 'logs') {
    state.logScope = candidate || 'outer'
    root.querySelector('[data-log-scope]').value = state.logScope
    return selectView('logs')
  }
  const path = button.dataset.inspect === 'model' ? 'world_model.md' : `${candidate}/${button.dataset.inspect === 'solver' ? 'solver/solver.py' : 'STRATEGY.md'}`
  if (!state.artifacts.length) await loadArtifacts(path)
  selectView('artifacts')
  loadArtifact(path)
}))
root.querySelector('[data-log-scope]').addEventListener('change', (event) => { state.logScope = event.target.value; loadLogs({ reset: true }) })
root.querySelectorAll('[data-log-stream]').forEach((button) => button.addEventListener('click', () => {
  state.logStream = button.dataset.logStream
  root.querySelectorAll('[data-log-stream]').forEach((item) => item.classList.toggle('active', item === button))
  const advanced = root.querySelector('.avo-advanced-menu')
  advanced.classList.toggle('active', Boolean(button.closest('.avo-advanced-menu')))
  if (button.closest('.avo-advanced-menu')) advanced.open = false
  loadLogs({ reset: true })
}))
root.querySelector('[data-log-search]').addEventListener('input', () => {
  window.clearTimeout(state.logSearchTimer)
  state.logSearchTimer = window.setTimeout(() => loadLogs({ reset: true }), 250)
})
root.querySelector('[data-load-older]').addEventListener('click', () => loadLogs())
root.querySelector('[data-artifact-search]').addEventListener('input', (event) => renderArtifactTree(event.target.value))
root.querySelector('[data-artifact-tree]').addEventListener('click', (event) => {
  const button = event.target.closest('[data-artifact-path]')
  if (button) loadArtifact(button.dataset.artifactPath)
})
state.timer = window.setInterval(() => {
  if (root.querySelector('[data-auto-refresh]').checked) loadRuns()
}, 3000)

loadRuns()
