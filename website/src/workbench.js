const apiBase = '/api/workbench'
const activeStatuses = new Set(['starting', 'running', 'stopping'])
const arcColors = [
  '#111820', '#2962a8', '#d13e35', '#2f9d62', '#e2b53f', '#7e8790', '#c85aa1', '#ef8d32',
  '#56b9c9', '#754b33', '#d7dde1', '#8fb1db', '#ef938b', '#8bd0a7', '#f4d978', '#ffffff',
]

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]))
}

function selectedValue(root, name) {
  return root.querySelector(`input[name="${name}"]:checked`)?.value || ''
}

function setSelected(root, name, value) {
  const input = root.querySelector(`input[name="${name}"][value="${value}"]`)
  if (input) input.checked = true
}

function renderEmpty(message) {
  return `<p class="evidence-empty">${escapeHtml(message)}</p>`
}

function renderNaturalRules(rules) {
  if (!rules.length) return renderEmpty('No natural-language hypotheses yet.')
  return `<div class="evidence-list">${rules.map((rule) => {
    const lifecycle = rule.lifecycle || (rule.status === 'archived' ? 'archived' : 'active')
    return `
    <article class="evidence-row">
      <div class="evidence-row-heading"><strong>${escapeHtml(rule.id)}</strong><span class="rule-status ${escapeHtml(lifecycle)}">${escapeHtml(lifecycle)}</span></div>
      <p>${escapeHtml(rule.summary)}</p>
      <small>Evidence: ${escapeHtml((rule.evidence_ids || []).join(', ') || 'none')}</small>
      ${rule.logical_rule_id ? `<small class="rule-mapping">${escapeHtml(rule.id)} -&gt; ${escapeHtml(rule.logical_rule_id)}</small>` : ''}
      ${(rule.superseded_by || []).length ? `<small>Superseded by: ${escapeHtml(rule.superseded_by.join(', '))}</small>` : ''}
      ${rule.failure_reason ? `<small class="failure-text">${escapeHtml(rule.failure_reason)}</small>` : ''}
    </article>
  `}).join('')}</div>`
}

function renderLogicalRules(rules) {
  if (!rules.length) return renderEmpty('No verified executable rules yet.')
  return `<div class="evidence-list">${rules.map((rule) => {
    const logical = rule.logical_rule || {}
    const evidence = rule.evidence || {}
    const lifecycle = rule.lifecycle || 'active'
    return `
      <article class="evidence-row">
        <div class="evidence-row-heading"><strong>${escapeHtml(rule.ruleID)}</strong><span class="rule-status ${escapeHtml(lifecycle)}">${escapeHtml(lifecycle)}</span></div>
        <p>${escapeHtml(rule.natural_language)}</p>
        <code>${escapeHtml(JSON.stringify({ anchor: logical.anchor, conditions: logical.conditions, effects: logical.effects }))}</code>
        <small>Supports: ${escapeHtml((evidence.supports || []).join(', ') || 'none')} | Hits: ${escapeHtml(evidence.prediction_hits || 0)} | Failures: ${escapeHtml(evidence.prediction_failures || 0)}</small>
        ${(rule.superseded_by || []).length ? `<small>Superseded by: ${escapeHtml(rule.superseded_by.join(', '))}</small>` : ''}
      </article>
    `
  }).join('')}</div>`
}

function renderFailures(failures) {
  if (!failures.length) return renderEmpty('No rule-learning failures recorded.')
  return `<div class="evidence-list">${failures.slice().reverse().map((failure) => `
    <article class="evidence-row failure-row">
      <div class="evidence-row-heading"><strong>${escapeHtml(failure.stage)}</strong><span>${escapeHtml(failure.timestamp || '')}</span></div>
      <p>${escapeHtml(failure.reason)}</p>
      <small>${escapeHtml([failure.hypothesis_id, failure.transition_id, failure.attempt ? `attempt ${failure.attempt}` : ''].filter(Boolean).join(' | '))}</small>
    </article>
  `).join('')}</div>`
}

function renderRuleAttempts(attempts) {
  if (!attempts.length) return renderEmpty('No logical-rule compiler attempts yet.')
  return `<div class="evidence-list">${attempts.slice().reverse().map((attempt) => `
    <article class="evidence-row ${attempt.outcome === 'rejected' ? 'failure-row' : ''}">
      <div class="evidence-row-heading"><strong>${escapeHtml(attempt.hypothesis_id || (attempt.stage === 'revision' ? 'Rule revision' : 'Rule attempt'))}</strong><span>${escapeHtml(`attempt ${attempt.attempt || '?'} | ${attempt.outcome || 'unknown'}`)}</span></div>
      <p>${escapeHtml(attempt.compilation_failure || (attempt.verification?.failures || []).join('; ') || 'Verified')}</p>
      <small>${escapeHtml([attempt.transition_id, attempt.model, attempt.timestamp].filter(Boolean).join(' | '))}</small>
      <details><summary>Raw model response</summary><pre>${escapeHtml(attempt.raw_response || '(empty response)')}</pre></details>
      ${attempt.candidate || attempt.candidates ? `<details><summary>Parsed candidate and verification</summary><pre>${escapeHtml(JSON.stringify({ candidate: attempt.candidate, candidates: attempt.candidates, verification: attempt.verification }, null, 2))}</pre></details>` : ''}
    </article>
  `).join('')}</div>`
}

function renderTimeline(timeline) {
  if (!timeline.length) return renderEmpty('No observed transitions yet.')
  return `<div class="timeline-table"><table><thead><tr><th>Transition</th><th>Action</th><th>Before</th><th>After</th></tr></thead><tbody>${timeline.slice().reverse().map((item) => `
    <tr><td>${escapeHtml(item.id)}</td><td>${escapeHtml(item.action)}</td><td><code>${escapeHtml((item.before?.grid || []).map((row) => row.join('')).join(' / '))}</code></td><td><code>${escapeHtml((item.after?.grid || []).map((row) => row.join('')).join(' / '))}</code></td></tr>
  `).join('')}</tbody></table></div>`
}

function renderLogs(events) {
  if (!events.length) return renderEmpty('No run logs yet.')
  return `<ol class="log-list">${events.slice().reverse().map((event) => `<li>${escapeHtml(event)}</li>`).join('')}</ol>`
}

function renderGrid(container, grid) {
  if (!grid?.length) {
    container.innerHTML = '<div class="frame-empty">Waiting for a frame</div>'
    return
  }
  const columns = Math.max(...grid.map((row) => row.length), 1)
  container.innerHTML = `<div class="arc-grid" style="--grid-columns:${columns}">${grid.flatMap((row) => row.map((value) => `<span title="${escapeHtml(value)}" style="--cell-color:${arcColors[Number(value)] || '#6c7780'}"></span>`)).join('')}</div>`
}

function transitionNumber(value) {
  const match = String(value || '').match(/^T(\d+)$/)
  return match ? Number(match[1]) : 0
}

function firstEvidenceNumber(item, evidenceIds) {
  const numbers = evidenceIds.map(transitionNumber).filter((value) => value > 0)
  if (numbers.length) return Math.min(...numbers)
  return transitionNumber(item.transition_id)
}

function installTabs(root, buttonSelector, buttonKey, panelSelector, panelKey) {
  root.addEventListener('click', (event) => {
    const button = event.target.closest(buttonSelector)
    if (!button) return
    const value = button.dataset[buttonKey]
    root.querySelectorAll(buttonSelector).forEach((item) => item.classList.toggle('active', item === button))
    root.querySelectorAll(panelSelector).forEach((panel) => {
      const active = panel.dataset[panelKey] === value
      panel.classList.toggle('active', active)
      panel.hidden = !active
    })
  })
}

function installWorkbench(root) {
  let runId = ''
  let pollTimer = null
  let replayTimer = null
  let replayFrames = []
  let replayIndex = 0
  let replayPayload = null
  let runBusy = false
  let openRouterBlocked = false
  let codexBlocked = false
  const startButton = root.querySelector('[data-run-start]')
  const stopButton = root.querySelector('[data-run-stop]')
  const status = root.querySelector('[data-run-status]')
  const summary = root.querySelector('[data-run-summary]')
  const error = root.querySelector('[data-run-error]')
  const agentModeInputs = root.querySelectorAll('input[name="agent-mode"]')
  const backendInputs = root.querySelectorAll('input[name="backend"]')
  const localGame = root.querySelector('[data-local-game]')
  const arcGame = root.querySelector('[data-arc-game]')
  const maxSteps = root.querySelector('[data-max-steps]')
  const provideLegend = root.querySelector('[data-provide-legend]')
  const provideEndGoal = root.querySelector('[data-provide-end-goal]')
  const endGoal = root.querySelector('[data-end-goal]')
  const endGoalField = root.querySelector('[data-end-goal-field]')
  const modelSelect = root.querySelector('[data-model]')
  const reasoningField = root.querySelector('[data-reasoning-field]')
  const reasoningEffort = root.querySelector('[data-reasoning-effort]')
  const codexModel = root.querySelector('[data-codex-model]')
  const codexEffort = root.querySelector('[data-codex-effort]')
  const codexState = root.querySelector('[data-codex-state]')
  const codexVersion = root.querySelector('[data-codex-version]')
  const codexAuth = root.querySelector('[data-codex-auth]')
  const codexRefresh = root.querySelector('[data-codex-refresh]')
  const codexMessage = root.querySelector('[data-codex-message]')
  const openRouterState = root.querySelector('[data-openrouter-state]')
  const openRouterLabel = root.querySelector('[data-openrouter-label]')
  const openRouterUsage = root.querySelector('[data-openrouter-usage]')
  const openRouterMonthly = root.querySelector('[data-openrouter-monthly]')
  const openRouterRemaining = root.querySelector('[data-openrouter-remaining]')
  const openRouterReset = root.querySelector('[data-openrouter-reset]')
  const openRouterRefresh = root.querySelector('[data-openrouter-refresh]')
  const openRouterKey = root.querySelector('[data-openrouter-key]')
  const openRouterSave = root.querySelector('[data-openrouter-save]')
  const openRouterMessage = root.querySelector('[data-openrouter-message]')
  const replayArtifact = root.querySelector('[data-replay-artifact]')
  const replayDelete = root.querySelector('[data-replay-delete]')
  const replayPlay = root.querySelector('[data-replay-play]')
  const promptSelect = root.querySelector('[data-prompt-select]')
  const promptEditor = root.querySelector('[data-prompt-editor]')
  const promptVersion = root.querySelector('[data-prompt-version]')
  const promptState = root.querySelector('[data-prompt-state]')
  const promptMessage = root.querySelector('[data-prompt-message]')
  const promptSave = root.querySelector('[data-prompt-save]')
  const promptReset = root.querySelector('[data-prompt-reset]')
  let modelCatalog = []
  let promptCatalog = []

  function agentMode() {
    return selectedValue(root, 'agent-mode') || 'rule'
  }

  function activeProviderBlocked() {
    return agentMode() === 'codex' ? codexBlocked : openRouterBlocked
  }

  function currentConfig() {
    const backend = selectedValue(root, 'backend') || 'puzzlescript'
    const mode = agentMode()
    return {
      agent_mode: mode,
      provider: mode === 'codex' ? 'codex_oauth' : 'openrouter',
      model: mode === 'codex' ? codexModel.value : modelSelect.value,
      reasoning_effort: mode === 'codex'
        ? codexEffort.value
        : reasoningField.hidden ? '' : reasoningEffort.value,
      backend,
      game_id: backend === 'puzzlescript' ? localGame.value : arcGame.value.trim(),
      max_steps: Number(maxSteps.value),
      memory_mode: selectedValue(root, 'memory-mode') || 'fresh',
      provide_legend: provideLegend.checked,
      provide_end_goal: provideEndGoal.checked,
      end_goal: endGoal.value.trim(),
    }
  }

  function refreshSummary() {
    const config = currentConfig()
    const provider = config.agent_mode === 'codex' ? 'Codex OAuth session' : 'OpenRouter rule agent'
    const effort = config.agent_mode === 'codex' ? ` | ${config.reasoning_effort === 'low' ? 'Light' : config.reasoning_effort}` : ''
    summary.textContent = `${provider} | ${config.backend === 'puzzlescript' ? 'Local PuzzleScript' : 'Official ARC'} | ${config.game_id || 'No game'} | ${config.model}${effort} | ${config.max_steps} steps`
  }

  function refreshAgentMode() {
    const codex = agentMode() === 'codex'
    root.querySelectorAll('[data-rule-only]').forEach((item) => { item.hidden = codex })
    root.querySelectorAll('[data-rule-settings]').forEach((item) => { item.hidden = codex })
    root.querySelectorAll('[data-codex-settings]').forEach((item) => { item.hidden = !codex })
    if (codex) {
      const activeView = root.querySelector('[data-view-tab].active')
      if (activeView?.dataset.viewTab !== 'run' && activeView?.dataset.viewTab !== 'settings') {
        root.querySelector('[data-view-tab="run"]').click()
      }
      root.querySelector('[data-evidence-tab="timeline"]').click()
      loadCodexStatus()
    } else {
      refreshReasoningEfforts()
    }
    startButton.disabled = runBusy || activeProviderBlocked()
    refreshSummary()
  }

  function refreshReasoningEfforts() {
    const selected = modelCatalog.find((model) => model.id === modelSelect.value)
    const efforts = selected?.supported_efforts || []
    reasoningField.hidden = efforts.length === 0
    if (!efforts.length) {
      reasoningEffort.innerHTML = '<option value="">Not configurable</option>'
      reasoningEffort.value = ''
      return
    }
    const defaultLabel = selected.default_effort
      ? `Provider default (${selected.default_effort})`
      : 'Provider default'
    reasoningEffort.innerHTML = [
      `<option value="">${escapeHtml(defaultLabel)}</option>`,
      ...efforts.map((effort) => `<option value="${escapeHtml(effort)}">${escapeHtml(effort)}</option>`),
    ].join('')
  }

  function setBusy(value) {
    runBusy = value
    startButton.disabled = value || activeProviderBlocked()
    stopButton.disabled = !value
    root.querySelectorAll('input:not([data-openrouter-key]), select:not([data-replay-artifact])').forEach((input) => { input.disabled = value })
    openRouterSave.disabled = value
    openRouterRefresh.disabled = value
    codexRefresh.disabled = value
    promptEditor.disabled = value
    promptSave.disabled = value
    promptReset.disabled = value
  }

  function formatCredits(value) {
    if (value === null || value === undefined || value === '') return '--'
    const amount = Number(value)
    if (!Number.isFinite(amount)) return '--'
    return `$${amount.toFixed(Math.abs(amount) >= 1 ? 2 : 4)}`
  }

  function renderOpenRouterStatus(payload) {
    const blockedStates = new Set([
      'not_configured', 'invalid', 'insufficient_credits', 'forbidden',
      'limit_exhausted', 'expired',
    ])
    const labels = {
      usable: 'Key valid',
      not_configured: 'Key missing',
      invalid: 'Invalid key',
      insufficient_credits: 'No credits',
      forbidden: 'Access forbidden',
      limit_exhausted: 'Limit exhausted',
      expired: 'Key expired',
      rate_limited: 'Temporarily rate limited',
      unreachable: 'Status unreachable',
      unavailable: 'Status unavailable',
    }
    openRouterBlocked = blockedStates.has(payload.state)
    openRouterState.textContent = labels[payload.state] || payload.state || 'Unknown'
    openRouterState.dataset.state = openRouterBlocked ? 'blocked' : 'usable'
    openRouterLabel.textContent = payload.label || '--'
    openRouterUsage.textContent = formatCredits(payload.usage)
    openRouterMonthly.textContent = formatCredits(payload.usage_monthly)
    openRouterRemaining.textContent = payload.configured && payload.limit_remaining == null
      ? 'Unlimited'
      : formatCredits(payload.limit_remaining)
    openRouterReset.textContent = payload.limit_reset || 'Never'
    openRouterKey.value = payload.api_key || ''
    startButton.disabled = runBusy || activeProviderBlocked()
  }

  async function loadOpenRouterStatus() {
    openRouterRefresh.disabled = true
    openRouterMessage.classList.remove('error')
    openRouterMessage.textContent = 'Checking OpenRouter account...'
    try {
      const payload = await request('/openrouter/status', { cache: 'no-store' })
      renderOpenRouterStatus(payload)
      openRouterMessage.textContent = payload.checked_at
        ? `Checked ${new Date(payload.checked_at).toLocaleString()}`
        : 'Status checked.'
    } catch (statusError) {
      openRouterMessage.classList.add('error')
      openRouterMessage.textContent = statusError.message
    } finally {
      openRouterRefresh.disabled = runBusy
    }
  }

  function renderCodexStatus(payload) {
    codexBlocked = !payload.available || !payload.logged_in
    const labels = {
      ready: 'Ready',
      login_required: 'Login required',
      runtime_missing: 'Runtime missing',
      unavailable: 'Unavailable',
    }
    codexState.textContent = labels[payload.state] || payload.state || 'Unknown'
    codexState.dataset.state = codexBlocked ? 'blocked' : 'usable'
    codexVersion.textContent = payload.version || '--'
    codexAuth.textContent = payload.logged_in ? 'Logged in with ChatGPT' : 'Not logged in'
    codexMessage.textContent = payload.message || 'Uses the Codex desktop login on this machine.'
    startButton.disabled = runBusy || activeProviderBlocked()
  }

  async function loadCodexStatus() {
    codexRefresh.disabled = true
    codexMessage.classList.remove('error')
    codexMessage.textContent = 'Checking the local Codex session...'
    try {
      renderCodexStatus(await request('/codex/status', { cache: 'no-store' }))
    } catch (statusError) {
      codexBlocked = true
      codexMessage.classList.add('error')
      codexMessage.textContent = statusError.message
      startButton.disabled = runBusy || activeProviderBlocked()
    } finally {
      codexRefresh.disabled = runBusy
    }
  }

  function update(snapshot) {
    if (
      snapshot.config?.agent_mode
      && snapshot.config.agent_mode !== agentMode()
    ) {
      setSelected(root, 'agent-mode', snapshot.config.agent_mode)
      refreshAgentMode()
    }
    const running = activeStatuses.has(snapshot.status)
    setBusy(running)
    status.textContent = snapshot.status || 'idle'
    status.dataset.status = snapshot.status || 'idle'
    error.textContent = snapshot.error || ''
    const progress = snapshot.progress || {}
    root.querySelector('[data-step-count]').textContent = progress.step || 0
    root.querySelector('[data-game-state]').textContent = progress.state || 'UNKNOWN'
    root.querySelector('[data-last-action]').textContent = progress.last_action || 'None'
    root.querySelector('[data-level-progress]').textContent = `${progress.levels_completed || 0} / ${progress.win_levels || 0} levels`

    const frameContainer = root.querySelector('[data-game-frame]')
    const rendered = snapshot.frame?.rendered_frame
    if (rendered?.data_url) {
      frameContainer.innerHTML = `<img src="${escapeHtml(rendered.data_url)}" alt="Current PuzzleScript game frame" />`
    } else {
      renderGrid(frameContainer, snapshot.frame?.grid || [])
    }

    const reasoning = snapshot.reasoning || {}
    const codex = snapshot.config?.agent_mode === 'codex'
    root.querySelector('[data-task-goal]').textContent = reasoning.task_goal || 'Not defined'
    root.querySelector('[data-subgoal]').textContent = reasoning.subgoal || 'None'
    const decision = reasoning.decision
    root.querySelector('[data-decision]').textContent = decision
      ? codex
        ? `${decision.action} | ${decision.note || 'no note'} | decision ${decision.decision || ''}`.replace(/\s+\| decision\s*$/, '')
        : `${decision.action} | ${decision.source} | ${decision.prediction_count} predictions`
      : 'None'
    const plan = reasoning.active_plan
    root.querySelector('[data-active-plan]').textContent = codex
      ? 'One action per observed frame'
      : plan ? `${plan.remaining.join(' > ') || 'Complete'}${plan.exploratory ? ' | exploratory' : ''}` : 'None'
    const legend = snapshot.legend || {}
    root.querySelector('[data-legend]').textContent = codex
      ? 'Not supplied; Codex sees the rendered frame and integer grid'
      : Object.entries(legend).map(([value, description]) => `${value} = ${description}`).join(' | ') || 'Not available'

    const collections = {
      natural: snapshot.natural_rules || [], logical: snapshot.logical_rules || [], failures: snapshot.failures || [], attempts: snapshot.rule_attempts || [], timeline: snapshot.timeline || [], logs: snapshot.events || [],
    }
    root.querySelector('[data-natural-count]').textContent = collections.natural.length
    root.querySelector('[data-logical-count]').textContent = collections.logical.length
    root.querySelector('[data-failure-count]').textContent = collections.failures.length
    root.querySelector('[data-attempt-count]').textContent = collections.attempts.length
    root.querySelector('[data-timeline-count]').textContent = collections.timeline.length
    root.querySelector('[data-log-count]').textContent = collections.logs.length
    root.querySelector('[data-evidence-panel="natural"]').innerHTML = renderNaturalRules(collections.natural)
    root.querySelector('[data-evidence-panel="logical"]').innerHTML = renderLogicalRules(collections.logical)
    root.querySelector('[data-evidence-panel="failures"]').innerHTML = renderFailures(collections.failures)
    root.querySelector('[data-evidence-panel="attempts"]').innerHTML = renderRuleAttempts(collections.attempts)
    root.querySelector('[data-evidence-panel="timeline"]').innerHTML = renderTimeline(collections.timeline)
    root.querySelector('[data-evidence-panel="logs"]').innerHTML = renderLogs(collections.logs)
    if (!running && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, options)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || data.error || `${response.status} ${response.statusText}`)
    return data
  }

  function renderSelectedPrompt() {
    const selected = promptCatalog.find((item) => item.id === promptSelect.value)
    if (!selected) return
    promptEditor.value = selected.content
    promptVersion.textContent = `Version ${selected.version}`
    promptState.textContent = selected.customized ? 'Customized' : 'Default'
    promptMessage.textContent = ''
  }

  async function loadPrompts(selectedId = promptSelect.value) {
    const payload = await request('/prompts', { cache: 'no-store' })
    promptCatalog = payload.prompts || []
    promptSelect.innerHTML = promptCatalog.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join('')
    if (promptCatalog.some((item) => item.id === selectedId)) promptSelect.value = selectedId
    renderSelectedPrompt()
  }

  async function poll() {
    if (!runId) return
    try {
      update(await request(`/runs/${encodeURIComponent(runId)}`))
    } catch (pollError) {
      error.textContent = pollError.message
    }
  }

  async function restoreCurrentRun() {
    const payload = await request('/runs/current', { cache: 'no-store' })
    const snapshot = payload.run
    if (!snapshot) return
    runId = snapshot.run_id
    update(snapshot)
    if (activeStatuses.has(snapshot.status) && !pollTimer) {
      pollTimer = setInterval(poll, 500)
    }
  }

  function stopReplay() {
    if (replayTimer) clearInterval(replayTimer)
    replayTimer = null
    replayPlay.textContent = 'Play'
  }

  function renderReplayFrame() {
    const container = root.querySelector('[data-replay-frame]')
    if (!replayFrames.length) {
      container.innerHTML = '<div class="frame-empty">No frames recorded</div>'
      root.querySelector('[data-replay-position]').textContent = '0 / 0'
      root.querySelector('[data-replay-subgoal]').textContent = 'Subgoal: Unavailable'
      root.querySelector('[data-replay-plan]').textContent = 'Plan: Unavailable'
      renderReplayPrediction(null)
      renderReplayRules('')
      return
    }
    const frame = replayFrames[replayIndex]
    const state = frame.state || {}
    if (state.image?.data_url) {
      container.innerHTML = `<img src="${escapeHtml(state.image.data_url)}" alt="Saved PuzzleScript game frame" />`
    } else {
      renderGrid(container, state.grid || [])
    }
    root.querySelector('[data-replay-position]').textContent = `${replayIndex + 1} / ${replayFrames.length}`
    root.querySelector('[data-replay-state]').textContent = state.state || 'UNKNOWN'
    root.querySelector('[data-replay-action]').textContent = `Action: ${frame.action || 'None'}`
    const plan = frame.plan
    root.querySelector('[data-replay-subgoal]').textContent = plan
      ? `Subgoal: ${plan.subgoal}`
      : 'Subgoal: Unavailable'
    root.querySelector('[data-replay-plan]').textContent = plan
      ? `Plan ${plan.step_index} / ${plan.total_steps}: ${plan.actions.map((action, index) => index + 1 === plan.step_index ? `[${action}]` : action).join(' > ')}`
      : 'Plan: Unavailable'
    const legend = replayPayload?.legend || {}
    root.querySelector('[data-replay-legend]').textContent = Object.entries(legend).map(([value, description]) => `${value} = ${description}`).join(' | ') || 'Legend unavailable'
    renderReplayPrediction(frame)
    renderReplayRules(frame.transition_id)
  }

  function renderReplayPrediction(frame) {
    const prediction = frame?.prediction || { recorded: false, result: 'unavailable' }
    const observedContainer = root.querySelector('[data-replay-observed]')
    const predictedContainer = root.querySelector('[data-replay-predicted]')
    renderGrid(observedContainer, frame?.state?.grid || [])
    const labels = {
      exact_match: 'Exact match',
      mismatch: 'Prediction mismatch',
      no_prediction: 'No existing prediction',
      unavailable: 'Prediction not recorded',
    }
    root.querySelector('[data-replay-prediction-status]').textContent = labels[prediction.result] || prediction.result
    const ruleIds = (prediction.rule_ids || []).join(', ')
    root.querySelector('[data-replay-prediction-source]').textContent = prediction.recorded
      ? `Decision: ${prediction.decision_source || 'unknown'} | Rules: ${ruleIds || 'none'}`
      : 'Source unavailable for this saved run'
    if (prediction.displayed_state?.grid?.length) {
      renderGrid(predictedContainer, prediction.displayed_state.grid)
    } else {
      predictedContainer.innerHTML = `<div class="frame-empty">${prediction.recorded ? 'No rule predicted this transition' : 'Not recorded in this run'}</div>`
    }
    const differences = prediction.closest_cell_differences || []
    root.querySelector('[data-replay-prediction-diff]').textContent = prediction.result === 'exact_match'
      ? 'No differing cells.'
      : differences.length
        ? differences.map((item) => `(${item.x},${item.y}): predicted ${item.before}, observed ${item.after}`).join(' | ')
        : ''
  }

  function renderReplayRules(transitionId) {
    const through = transitionNumber(transitionId)
    const evidenceThrough = (ids) => (ids || []).filter(
      (id) => transitionNumber(id) > 0 && transitionNumber(id) <= through,
    )
    const visibleByEvidence = (items, evidenceFor) => (items || []).filter((item) => {
      const first = firstEvidenceNumber(item, evidenceFor(item))
      return first > 0 && first <= through
    })
    const natural = visibleByEvidence(
      replayPayload?.natural_rules,
      (rule) => rule.evidence_ids || [],
    ).map((rule) => ({ ...rule, evidence_ids: evidenceThrough(rule.evidence_ids) }))
    const logical = visibleByEvidence(
      replayPayload?.logical_rules,
      (rule) => rule.evidence?.supports || [],
    ).map((rule) => {
      const supports = evidenceThrough(rule.evidence?.supports)
      return {
        ...rule,
        evidence: {
          ...(rule.evidence || {}),
          supports,
          prediction_hits: Math.min(
            Number(rule.evidence?.prediction_hits || 0),
            Math.max(0, supports.length - 1),
          ),
        },
      }
    })
    const failures = visibleByEvidence(
      replayPayload?.failures,
      (failure) => [failure.transition_id],
    )
    const attempts = visibleByEvidence(
      replayPayload?.rule_attempts,
      (attempt) => [attempt.transition_id],
    )
    root.querySelector('[data-replay-through]').textContent = transitionId
      ? `Through ${transitionId}`
      : 'Before first transition'
    root.querySelector('[data-replay-natural-count]').textContent = natural.length
    root.querySelector('[data-replay-logical-count]').textContent = logical.length
    root.querySelector('[data-replay-failure-count]').textContent = failures.length
    root.querySelector('[data-replay-attempt-count]').textContent = attempts.length
    root.querySelector('[data-replay-rule-panel="natural"]').innerHTML = renderNaturalRules(natural)
    root.querySelector('[data-replay-rule-panel="logical"]').innerHTML = renderLogicalRules(logical)
    root.querySelector('[data-replay-rule-panel="failures"]').innerHTML = renderFailures(failures)
    root.querySelector('[data-replay-rule-panel="attempts"]').innerHTML = renderRuleAttempts(attempts)
  }

  async function loadReplay() {
    stopReplay()
    const artifactId = replayArtifact.value
    if (!artifactId) {
      replayFrames = []
      replayPayload = null
      replayDelete.disabled = true
      renderReplayFrame()
      return
    }
    const gameId = currentConfig().game_id
    replayPayload = await request(`/artifacts/${encodeURIComponent(artifactId)}?game_id=${encodeURIComponent(gameId)}`)
    replayFrames = replayPayload.frames || []
    replayIndex = 0
    replayDelete.disabled = artifactId === 'current' || runBusy
    renderReplayFrame()
  }

  async function loadArtifactList() {
    const gameId = currentConfig().game_id
    const payload = await request(`/artifacts?game_id=${encodeURIComponent(gameId)}`)
    const artifacts = payload.artifacts || []
    replayArtifact.innerHTML = artifacts.length
      ? artifacts.map((artifact) => `<option value="${escapeHtml(artifact.id)}">${escapeHtml(`${artifact.label} | ${artifact.frames} frames | ${artifact.transitions} transitions`)}</option>`).join('')
      : '<option value="">No saved runs</option>'
    await loadReplay()
  }

  startButton.addEventListener('click', async () => {
    error.textContent = ''
    const config = currentConfig()
    if (!config.game_id || !Number.isInteger(config.max_steps) || config.max_steps < 1 || config.max_steps > 200) {
      error.textContent = 'Choose a game and a step limit from 1 to 200.'
      return
    }
    setBusy(true)
    try {
      const snapshot = await request('/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
      })
      runId = snapshot.run_id
      update(snapshot)
      if (!pollTimer) pollTimer = setInterval(poll, 500)
    } catch (startError) {
      setBusy(false)
      error.textContent = startError.message
    }
  })

  stopButton.addEventListener('click', async () => {
    if (!runId) return
    stopButton.disabled = true
    try {
      update(await request(`/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST' }))
    } catch (stopError) {
      error.textContent = stopError.message
    }
  })

  openRouterRefresh.addEventListener('click', loadOpenRouterStatus)
  codexRefresh.addEventListener('click', loadCodexStatus)
  openRouterSave.addEventListener('click', async () => {
    const apiKey = openRouterKey.value.trim()
    if (!apiKey) {
      openRouterMessage.classList.add('error')
      openRouterMessage.textContent = 'Enter an OpenRouter API key.'
      return
    }
    openRouterSave.disabled = true
    openRouterMessage.classList.remove('error')
    openRouterMessage.textContent = 'Validating key with OpenRouter...'
    try {
      const payload = await request('/openrouter/key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      })
      renderOpenRouterStatus(payload.status)
      error.textContent = ''
      openRouterMessage.textContent = 'Key is valid and saved to .env.'
    } catch (saveError) {
      openRouterMessage.classList.add('error')
      openRouterMessage.textContent = saveError.message
    } finally {
      openRouterSave.disabled = runBusy
    }
  })

  promptSelect.addEventListener('change', renderSelectedPrompt)
  promptEditor.addEventListener('input', () => { promptMessage.textContent = 'Unsaved changes' })
  promptSave.addEventListener('click', async () => {
    promptSave.disabled = true
    try {
      const payload = await request(`/prompts/${encodeURIComponent(promptSelect.value)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: promptEditor.value }),
      })
      const index = promptCatalog.findIndex((item) => item.id === payload.prompt.id)
      if (index >= 0) promptCatalog[index] = payload.prompt
      renderSelectedPrompt()
      promptMessage.textContent = 'Saved'
    } catch (promptError) {
      promptMessage.textContent = promptError.message
    } finally {
      promptSave.disabled = runBusy
    }
  })
  promptReset.addEventListener('click', async () => {
    if (!window.confirm('Reset this prompt to its repository default?')) return
    promptReset.disabled = true
    try {
      const payload = await request(`/prompts/${encodeURIComponent(promptSelect.value)}`, { method: 'DELETE' })
      const index = promptCatalog.findIndex((item) => item.id === payload.prompt.id)
      if (index >= 0) promptCatalog[index] = payload.prompt
      renderSelectedPrompt()
      promptMessage.textContent = 'Default restored'
    } catch (promptError) {
      promptMessage.textContent = promptError.message
    } finally {
      promptReset.disabled = runBusy
    }
  })

  root.querySelector('[data-replay-refresh]').addEventListener('click', () => {
    loadArtifactList().catch((replayError) => { error.textContent = replayError.message })
  })
  replayArtifact.addEventListener('change', () => {
    loadReplay().catch((replayError) => { error.textContent = replayError.message })
  })
  root.querySelector('[data-replay-previous]').addEventListener('click', () => {
    stopReplay()
    replayIndex = Math.max(0, replayIndex - 1)
    renderReplayFrame()
  })
  root.querySelector('[data-replay-next]').addEventListener('click', () => {
    stopReplay()
    replayIndex = Math.min(Math.max(0, replayFrames.length - 1), replayIndex + 1)
    renderReplayFrame()
  })
  replayPlay.addEventListener('click', () => {
    if (replayTimer) {
      stopReplay()
      return
    }
    if (replayFrames.length < 2) return
    if (replayIndex >= replayFrames.length - 1) replayIndex = 0
    replayPlay.textContent = 'Pause'
    replayTimer = setInterval(() => {
      replayIndex += 1
      renderReplayFrame()
      if (replayIndex >= replayFrames.length - 1) stopReplay()
    }, 800)
  })
  replayDelete.addEventListener('click', async () => {
    const artifactId = replayArtifact.value
    if (!artifactId || artifactId === 'current') return
    if (!window.confirm(`Delete archive ${artifactId}?`)) return
    try {
      await request(`/artifacts/${encodeURIComponent(artifactId)}?game_id=${encodeURIComponent(currentConfig().game_id)}`, { method: 'DELETE' })
      await loadArtifactList()
    } catch (deleteError) {
      error.textContent = deleteError.message
    }
  })

  backendInputs.forEach((input) => input.addEventListener('change', () => {
    const local = selectedValue(root, 'backend') === 'puzzlescript'
    root.querySelector('[data-local-game-field]').hidden = !local
    root.querySelector('[data-arc-game-field]').hidden = local
    refreshSummary()
  }))
  agentModeInputs.forEach((input) => input.addEventListener('change', refreshAgentMode))
  provideEndGoal.addEventListener('change', () => {
    endGoalField.hidden = !provideEndGoal.checked
    refreshSummary()
  })
  root.addEventListener('change', refreshSummary)
  modelSelect.addEventListener('change', () => {
    refreshReasoningEfforts()
    refreshSummary()
  })

  installTabs(root, '[data-view-tab]', 'viewTab', '[data-view-panel]', 'viewPanel')
  installTabs(root, '[data-evidence-tab]', 'evidenceTab', '[data-evidence-panel]', 'evidencePanel')
  installTabs(root, '[data-replay-rule-tab]', 'replayRuleTab', '[data-replay-rule-panel]', 'replayRulePanel')
  root.querySelectorAll('[data-view-panel="settings"], [data-evidence-panel]:not(.active)').forEach((panel) => { panel.hidden = true })
  root.querySelector('[data-view-tab="replay"]').addEventListener('click', () => {
    loadArtifactList().catch((replayError) => { error.textContent = replayError.message })
  })
  root.querySelector('[data-view-tab="prompts"]').addEventListener('click', () => {
    loadPrompts().catch((promptError) => { promptMessage.textContent = promptError.message })
  })

  request('/games?backend=puzzlescript').then((payload) => {
    if (!payload.games?.length) return
    localGame.innerHTML = payload.games.map((game) => `<option value="${escapeHtml(game.game_id)}">${escapeHtml(game.title || game.game_id)}</option>`).join('')
    if ([...localGame.options].some((option) => option.value === 'ps_sokoban_basic-v1')) localGame.value = 'ps_sokoban_basic-v1'
    refreshSummary()
  }).catch(() => {})
  request('/models').then((payload) => {
    modelCatalog = payload.models || []
    const defaultModel = payload.default_model || 'anthropic/claude-opus-4.8'
    modelSelect.innerHTML = modelCatalog.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.label)}</option>`).join('')
    if ([...modelSelect.options].some((option) => option.value === defaultModel)) modelSelect.value = defaultModel
    refreshReasoningEfforts()
    const codexCatalog = payload.codex || {}
    const codexModels = codexCatalog.models || []
    codexModel.innerHTML = codexModels.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.label)}</option>`).join('')
    if (codexCatalog.default_model && [...codexModel.options].some((option) => option.value === codexCatalog.default_model)) {
      codexModel.value = codexCatalog.default_model
    }
    refreshSummary()
  }).catch((modelError) => { error.textContent = modelError.message })
  request('/health').then((health) => {
    if (!health.openrouter_configured) error.textContent = 'OPENROUTER_API_KEY is not configured.'
  }).catch((healthError) => { error.textContent = healthError.message })
  restoreCurrentRun().catch((restoreError) => { error.textContent = restoreError.message })
  loadOpenRouterStatus()
  setSelected(root, 'backend', 'puzzlescript')
  setSelected(root, 'agent-mode', 'rule')
  refreshAgentMode()
}

const root = document.querySelector('[data-workbench]')
if (root) installWorkbench(root)
