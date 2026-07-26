const apiBase = '/api/optimal-path'
const activeStatuses = new Set(['starting', 'running', 'stopping'])
const numberFormat = new Intl.NumberFormat()

async function request(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const payload = response.status === 204 ? null : await response.json()
  if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`)
  return payload
}

function installOptimalPath(root) {
  const elements = {
    game: root.querySelector('[data-optimal-game]'),
    timeout: root.querySelector('[data-optimal-timeout]'),
    states: root.querySelector('[data-optimal-states]'),
    start: root.querySelector('[data-optimal-start]'),
    stop: root.querySelector('[data-optimal-stop]'),
    error: root.querySelector('[data-optimal-error]'),
    status: root.querySelector('[data-optimal-status]'),
    elapsed: root.querySelector('[data-elapsed-time]'),
    timeLimit: root.querySelector('[data-time-limit]'),
    timeProgress: root.querySelector('[data-time-progress]'),
    levelProgress: root.querySelector('[data-level-progress]'),
    depth: root.querySelector('[data-depth]'),
    expanded: root.querySelector('[data-expanded]'),
    visited: root.querySelector('[data-visited]'),
    frontier: root.querySelector('[data-frontier]'),
    transitions: root.querySelector('[data-transitions]'),
    speed: root.querySelector('[data-speed]'),
    idle: root.querySelector('[data-result-idle]'),
    failure: root.querySelector('[data-result-failure]'),
    failureMessage: root.querySelector('[data-failure-message]'),
    solved: root.querySelector('[data-result-solved]'),
    solutionDepth: root.querySelector('[data-solution-depth]'),
    levelsSolved: root.querySelector('[data-levels-solved]'),
    replayImage: root.querySelector('[data-replay-image]'),
    replayEmpty: root.querySelector('[data-replay-empty]'),
    replayPrevious: root.querySelector('[data-replay-previous]'),
    replayPlay: root.querySelector('[data-replay-play]'),
    replayNext: root.querySelector('[data-replay-next]'),
    replayPosition: root.querySelector('[data-replay-position]'),
    replayAction: root.querySelector('[data-replay-action]'),
    replayLevel: root.querySelector('[data-replay-level]'),
    resultTime: root.querySelector('[data-result-time]'),
    resultStates: root.querySelector('[data-result-states]'),
    actionPath: root.querySelector('[data-action-path]'),
  }

  let currentRun = null
  let pollTimer = null
  let replayFrames = []
  let replayIndex = 0
  let replayTimer = null

  function setError(message = '') {
    elements.error.textContent = message
  }

  function setControls(active) {
    elements.game.disabled = active
    elements.timeout.disabled = active
    elements.states.disabled = active
    elements.start.disabled = active
    elements.stop.disabled = !active
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
  }

  function stopReplay() {
    if (replayTimer) clearInterval(replayTimer)
    replayTimer = null
    elements.replayPlay.textContent = 'Play'
  }

  function showResult(kind) {
    elements.idle.hidden = kind !== 'idle'
    elements.failure.hidden = kind !== 'failure'
    elements.solved.hidden = kind !== 'solved'
  }

  function renderReplayFrame() {
    const frame = replayFrames[replayIndex]
    if (!frame) return
    const rendered = frame.renderedFrame
    if (rendered?.data_url) {
      elements.replayImage.src = rendered.data_url
      elements.replayImage.hidden = false
      elements.replayEmpty.hidden = true
    } else {
      elements.replayImage.removeAttribute('src')
      elements.replayImage.hidden = true
      elements.replayEmpty.hidden = false
    }
    elements.replayPosition.textContent = `${replayIndex + 1} / ${replayFrames.length}`
    elements.replayAction.textContent = frame.action || 'RESET'
    elements.replayLevel.textContent = `${frame.levelNumber || 1} / ${frame.totalLevels || 1}`
    elements.replayPrevious.disabled = replayIndex === 0
    elements.replayNext.disabled = replayIndex >= replayFrames.length - 1
    for (const button of elements.actionPath.querySelectorAll('button')) {
      button.classList.toggle('active', Number(button.dataset.frameIndex) === replayIndex)
    }
  }

  function setReplay(frames) {
    stopReplay()
    replayFrames = frames || []
    replayIndex = 0
    elements.actionPath.innerHTML = replayFrames.map((frame, index) => `
      <button type="button" data-frame-index="${index}" class="${index === 0 ? 'active' : ''}">
        <small>${index}</small>${frame.action || 'RESET'}
      </button>
    `).join('')
    for (const button of elements.actionPath.querySelectorAll('button')) {
      button.addEventListener('click', () => {
        stopReplay()
        replayIndex = Number(button.dataset.frameIndex)
        renderReplayFrame()
      })
    }
    renderReplayFrame()
  }

  function elapsedFor(run) {
    const reported = Number(run.progress?.elapsedMs || 0)
    if (!activeStatuses.has(run.status)) return reported
    const wall = Date.now() - Date.parse(run.started_at)
    const limit = Number(run.progress?.timeoutMs || 0)
    return Math.min(limit, Math.max(reported, wall))
  }

  function renderRun(run) {
    currentRun = run
    const progress = run?.progress || {}
    const active = Boolean(run && activeStatuses.has(run.status))
    setControls(active)
    const statusLabel = (run?.status || 'idle').replace('_', ' ')
    elements.status.textContent = statusLabel
    elements.status.dataset.status = run?.status || 'idle'

    const elapsedMs = run ? elapsedFor(run) : 0
    const timeoutMs = Number(progress.timeoutMs || Number(elements.timeout.value) * 1000)
    elements.elapsed.textContent = `${(elapsedMs / 1000).toFixed(1)}s`
    elements.timeLimit.textContent = `${Math.round(timeoutMs / 1000)}s`
    elements.timeProgress.value = timeoutMs > 0 ? Math.min(1, elapsedMs / timeoutMs) : 0
    const levelNumber = progress.levelNumber || run?.result?.failedLevelNumber || run?.result?.totalLevels || 0
    const totalLevels = progress.totalLevels || run?.result?.totalLevels || 0
    elements.levelProgress.textContent = totalLevels
      ? `Level ${levelNumber} of ${totalLevels} · whole-game budget`
      : 'Waiting to start'
    elements.depth.textContent = numberFormat.format(progress.maxDepthDiscovered || 0)
    elements.expanded.textContent = numberFormat.format(progress.expandedStates || 0)
    elements.visited.textContent = numberFormat.format(progress.uniqueStates || 0)
    elements.frontier.textContent = numberFormat.format(progress.frontierStates || 0)
    elements.transitions.textContent = numberFormat.format(progress.transitions || 0)
    elements.speed.textContent = `${numberFormat.format(Math.round(progress.transitionsPerSecond || 0))}/s`

    if (!run) {
      showResult('idle')
      return
    }
    if (active) {
      showResult('idle')
      root.querySelector('[data-result-idle] h2').textContent = 'Searching…'
      root.querySelector('[data-result-idle] p').textContent = 'The frontier is expanding breadth-first. You can leave and return to this page without losing the active run.'
      return
    }
    if (run.status === 'solved' && run.result?.solved) {
      showResult('solved')
      elements.solutionDepth.textContent = run.result.solutionDepth
      elements.levelsSolved.textContent = `${run.result.levelsSolved} / ${run.result.totalLevels}`
      elements.resultTime.textContent = `${(Number(run.result.searchMs || 0) / 1000).toFixed(2)}s`
      elements.resultStates.textContent = numberFormat.format(run.result.uniqueStates || 0)
      setReplay(run.replay)
      return
    }

    showResult('failure')
    const outcome = run.result?.status || run.status
    const failedAt = run.result?.failedLevelNumber
      ? ` on level ${run.result.failedLevelNumber} of ${run.result.totalLevels}`
      : ''
    const messages = {
      time_limit: `The ${Math.round(timeoutMs / 1000)} second whole-game time limit expired${failedAt}.`,
      state_limit: `The search reached ${numberFormat.format(run.config?.max_states || 0)} unique states${failedAt}.`,
      exhausted: 'The reachable state graph was exhausted without finding a win.',
      unsupported: `This game uses a mechanic the current solver does not support (${run.result?.reason || 'unknown'}).`,
      ineligible: 'This game does not expose a formal PuzzleScript win condition or playable level.',
      cancelled: 'The search was stopped before it found a winning path.',
      failed: run.error || 'The solver could not complete this run.',
    }
    elements.failureMessage.textContent = messages[outcome] || messages[run.status] || `Search ended: ${outcome}.`
  }

  async function poll() {
    if (!currentRun?.run_id) return
    try {
      const run = await request(`/runs/${currentRun.run_id}`, { cache: 'no-store' })
      renderRun(run)
      if (!activeStatuses.has(run.status)) stopPolling()
    } catch (error) {
      setError(error.message)
      stopPolling()
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(poll, 500)
  }

  async function loadGames() {
    const payload = await request('/games')
    const games = payload.games || []
    elements.game.innerHTML = games.map((game) => (
      `<option value="${game.game_id}">${game.title} (${game.game_id})</option>`
    )).join('')
    const preferred = games.find((game) => game.game_id === 'ps_sokoban_basic-v1')
    if (preferred) elements.game.value = preferred.game_id
  }

  async function restoreCurrentRun() {
    const payload = await request('/runs/current', { cache: 'no-store' })
    if (payload.run) {
      renderRun(payload.run)
      if (activeStatuses.has(payload.run.status)) startPolling()
    } else {
      renderRun(null)
    }
  }

  elements.start.addEventListener('click', async () => {
    setError()
    stopReplay()
    try {
      const run = await request('/runs', {
        method: 'POST',
        body: JSON.stringify({
          game_id: elements.game.value,
          timeout_seconds: Number(elements.timeout.value),
          max_states: Number(elements.states.value),
        }),
      })
      renderRun(run)
      startPolling()
    } catch (error) {
      setError(error.message)
    }
  })

  elements.stop.addEventListener('click', async () => {
    if (!currentRun?.run_id) return
    setError()
    try {
      renderRun(await request(`/runs/${currentRun.run_id}/stop`, { method: 'POST' }))
    } catch (error) {
      setError(error.message)
    }
  })

  elements.replayPrevious.addEventListener('click', () => {
    stopReplay()
    replayIndex = Math.max(0, replayIndex - 1)
    renderReplayFrame()
  })
  elements.replayNext.addEventListener('click', () => {
    stopReplay()
    replayIndex = Math.min(replayFrames.length - 1, replayIndex + 1)
    renderReplayFrame()
  })
  elements.replayPlay.addEventListener('click', () => {
    if (replayTimer) {
      stopReplay()
      return
    }
    if (replayIndex >= replayFrames.length - 1) replayIndex = 0
    elements.replayPlay.textContent = 'Pause'
    renderReplayFrame()
    replayTimer = setInterval(() => {
      if (replayIndex >= replayFrames.length - 1) {
        stopReplay()
        return
      }
      replayIndex += 1
      renderReplayFrame()
    }, 500)
  })

  Promise.all([loadGames(), restoreCurrentRun()]).catch((error) => setError(error.message))
}

const root = document.querySelector('[data-optimal-path]')
if (root) installOptimalPath(root)
