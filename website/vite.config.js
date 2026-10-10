import fs from 'fs'
import { promises as fsp } from 'fs'
import { createRequire } from 'module'
import { dirname, extname, isAbsolute, resolve, sep } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import { resolveAvoRun } from './run-paths.js'
import { selectEvidenceFrame, reasoningAtAction } from './avo-replay.js'
import { readEvidenceSummary } from './evidence-summary.mjs'
import { openCodeConversation } from './history/opencode-events.js'
import { gameLibraryPlugin } from './game-library-server.mjs'
import { evaluationLevels } from './src/run-results.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(__dirname, '..')
const requireFromConfig = createRequire(import.meta.url)
const puzzlescriptRuntime = requireFromConfig(resolve(repoRoot, 'puzzlescript_interface/runtime/server.js'))
const goalRecognitionSource = resolve(repoRoot, 'studies/goal_recognition/website')
const thinkingComparisonSource = resolve(repoRoot, 'thinking-comparison')
const pseudocodeSource = resolve(repoRoot, 'docs/pseudocode')
const pseudocodeManifest = resolve(pseudocodeSource, 'manifest.json')
const pseudocodeSaveRoute = '/__pseudocode/save'
const notesSource = resolve(repoRoot, 'docs/notes')
const architectureSource = resolve(repoRoot, 'docs/architecture')
const allowedNotesFiles = new Set(['workbench-notes.md', 'todo.md', 'benchmark-positioning.md'])
const notesSaveRoute = '/__notes/save'
const avoRunsRoute = '/__avo/runs'
const avoRunRoute = '/__avo/run'
const avoFrameRoute = '/__avo/frame'
const avoLogsRoute = '/__avo/logs'
const avoArtifactsRoute = '/__avo/artifacts'
const avoArtifactRoute = '/__avo/artifact'
const avoEvolutionRoot = resolve(repoRoot, 'avo/output/evolution')
const avoFrameReplayCache = new Map()
const maxAvoArtifactBytes = 512 * 1024
const maxPseudocodeBytes = 1024 * 1024
const workbenchApiPort = process.env.WORKBENCH_API_PORT || '8010'
const allowedHosts = (process.env.WORKBENCH_ALLOWED_HOSTS || 'adampalace-pc.tail65f3f9.ts.net')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean)

const sourceRoutes = [
  {
    route: '/experiments/goal-recognition/assets/',
    source: resolve(goalRecognitionSource, 'assets'),
    buildTarget: 'experiments/goal-recognition/assets',
  },
  {
    route: '/experiments/thinking-comparison/',
    source: thinkingComparisonSource,
    buildTarget: 'experiments/thinking-comparison',
  },
  {
    route: '/docs/pseudocode/',
    source: pseudocodeSource,
    buildTarget: 'docs/pseudocode',
  },
  {
    route: '/docs/notes/',
    source: notesSource,
    buildTarget: 'docs/notes',
  },
  {
    route: '/docs/architecture-assets/',
    source: architectureSource,
    buildTarget: 'docs/architecture-assets',
  },
]

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'application/jsonlines; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8',
}

function safeResolve(base, requestPath) {
  const relativePath = decodeURIComponent(requestPath).replace(/^\/+/, '')
  const target = resolve(base, relativePath)
  if (target !== base && !target.startsWith(base + sep)) return null
  return target
}

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify(payload))
}

function readJsonBody(req) {
  return new Promise((resolveBody, rejectBody) => {
    let body = ''
    let byteLength = 0
    let tooLarge = false

    req.setEncoding('utf8')
    req.on('data', (chunk) => {
      byteLength += Buffer.byteLength(chunk, 'utf8')
      if (byteLength > maxPseudocodeBytes) {
        tooLarge = true
        return
      }
      body += chunk
    })
    req.on('end', () => {
      if (tooLarge) {
        rejectBody(Object.assign(new Error('Markdown exceeds the 1 MB limit'), { statusCode: 413 }))
        return
      }
      try {
        resolveBody(JSON.parse(body))
      } catch {
        rejectBody(Object.assign(new Error('Request body must be valid JSON'), { statusCode: 400 }))
      }
    })
    req.on('error', rejectBody)
  })
}

async function savePseudocodeMarkdown(payload) {
  const file = payload?.file
  const markdown = payload?.markdown
  if (typeof file !== 'string' || typeof markdown !== 'string') {
    throw Object.assign(new Error('Both file and markdown are required'), { statusCode: 400 })
  }

  const manifest = JSON.parse(await fsp.readFile(pseudocodeManifest, 'utf8'))
  if (!manifest.some((item) => item.file === file)) {
    throw Object.assign(new Error('Only pseudocode files listed in the manifest can be saved'), { statusCode: 403 })
  }

  const filePath = safeResolve(pseudocodeSource, file)
  if (!filePath || extname(filePath).toLowerCase() !== '.md') {
    throw Object.assign(new Error('Invalid pseudocode Markdown path'), { statusCode: 400 })
  }

  await fsp.writeFile(filePath, markdown, 'utf8')
}

async function saveNotesMarkdown(payload) {
  const file = payload?.file
  const markdown = payload?.markdown
  if (typeof file !== 'string' || typeof markdown !== 'string') {
    throw Object.assign(new Error('Both file and markdown are required'), { statusCode: 400 })
  }
  if (!allowedNotesFiles.has(file)) {
    throw Object.assign(new Error('Only notebook files listed by the Notes page can be saved'), { statusCode: 403 })
  }
  const filePath = safeResolve(notesSource, file)
  if (!filePath || extname(filePath).toLowerCase() !== '.md') {
    throw Object.assign(new Error('Invalid notes Markdown path'), { statusCode: 400 })
  }
  await fsp.writeFile(filePath, markdown, 'utf8')
}

async function readJsonSafe(path) {
  try {
    const payload = JSON.parse(await fsp.readFile(path, 'utf8'))
    return payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {}
  } catch {
    return {}
  }
}

async function readJsonLinesSafe(path) {
  try {
    return (await fsp.readFile(path, 'utf8')).split(/\r?\n/).flatMap((line) => {
      if (!line.trim()) return []
      try {
        const payload = JSON.parse(line)
        return payload && typeof payload === 'object' ? [payload] : []
      } catch {
        return []
      }
    })
  } catch {
    return []
  }
}

function directAvoRunPath(runId) {
  return resolveAvoRun(repoRoot, runId)
}

async function fileModified(path) {
  try { return (await fsp.stat(path)).mtimeMs } catch { return 0 }
}

async function buildAvoSnapshot(runId) {
  const root = directAvoRunPath(runId)
  if (!root) throw Object.assign(new Error('Invalid AVO run'), { statusCode: 400 })
  try {
    if (!(await fsp.stat(root)).isDirectory()) throw new Error('not a directory')
  } catch {
    throw Object.assign(new Error('AVO run not found'), { statusCode: 404 })
  }

  const catalogRequest = listAvoRuns()
  const [config, lineage] = await Promise.all([readJsonSafe(resolve(root, 'evolution_config.json')), readJsonSafe(resolve(root, 'lineage.json'))])
  const candidateEntries = Array.isArray(lineage.candidates) ? lineage.candidates : []
  const evaluations = Array.isArray(lineage.evaluations) ? lineage.evaluations : []
  const candidateIds = candidateEntries.map((item) => item?.candidate_id).filter(Boolean)
  const currentId = candidateIds.at(-1) || ''
  const current = currentId ? resolve(root, currentId) : root
  const [research, fresh, summary, solverEvaluation, solverModified] = await Promise.all([
    readEvidenceSummary(resolve(current, 'research/evidence.jsonl'), 12),
    readEvidenceSummary(resolve(current, 'evaluation/evidence.jsonl'), 12),
    readJsonSafe(resolve(current, 'summary.json')),
    readJsonSafe(resolve(current, 'evaluation/solver_evaluation.json')),
    fileModified(resolve(current, 'solver/solver.py')),
  ])
  const solverArchived = Boolean(solverModified)
  const latestEvaluation = evaluations.at(-1) || {}
  const phase = Object.keys(summary).length ? 'evaluated'
    : Object.keys(solverEvaluation).length ? 'finishing_evaluation'
      : fresh.events ? 'fresh_evaluation'
        : solverArchived ? 'starting_fresh_evaluation'
          : research.events ? 'research'
            : currentId ? 'pending' : 'initializing'

  const activityPaths = [
    resolve(root, 'evolution_config.json'), resolve(root, 'lineage.json'),
    resolve(root, 'optimizer_analysis/conversation.jsonl'), resolve(current, 'summary.json'),
    resolve(current, 'research/evidence.jsonl'), resolve(current, 'research/analysis/conversation.jsonl'),
    resolve(current, 'evaluation/evidence.jsonl'), resolve(current, 'solver/solver.py'),
  ]
  const modified = await Promise.all(activityPaths.map(fileModified))
  const lastActivityMs = Math.max(0, ...modified)
  const candidates = await Promise.all(candidateEntries.map(async (entry) => {
    const candidateId = entry.candidate_id
    const evaluation = evaluations.find((item) => item?.candidate_id === candidateId) || {}
    const [candidateSummary, candidateResearch, candidateEvaluation] = await Promise.all([
      readJsonSafe(resolve(root, candidateId, 'summary.json')),
      candidateId === currentId ? research : readEvidenceSummary(resolve(root, candidateId, 'research/evidence.jsonl')),
      candidateId === currentId ? fresh : readEvidenceSummary(resolve(root, candidateId, 'evaluation/evidence.jsonl')),
    ])
    return {
      candidate_id: candidateId,
      parent_ids: entry.parent_ids || entry.parents || [],
      evaluated: Boolean(Object.keys(candidateSummary).length || Object.keys(evaluation).length),
      fitness: evaluation.fitness ?? candidateSummary.fitness ?? null,
      success: evaluation.success ?? candidateSummary.success ?? null,
      win_levels: evaluationLevels(evaluation) ?? candidateEvaluation.last_transition?.payload?.after?.progress?.win_levels ?? null,
      research: {
        actions: candidateResearch.actions,
        levels: candidateResearch.levels,
        last_activity: candidateResearch.last_transition?.recorded_at || null,
        revision: candidateResearch.last_transition?.sequence ?? 0,
        fallback_frame: candidateResearch.last_transition?.payload?.after?.payload?.frame || [],
      },
      evaluation: {
        actions: candidateEvaluation.actions,
        levels: candidateEvaluation.levels,
        last_activity: candidateEvaluation.last_transition?.recorded_at || null,
        revision: candidateEvaluation.last_transition?.sequence ?? 0,
        fallback_frame: candidateEvaluation.last_transition?.payload?.after?.payload?.frame || [],
      },
    }
  }))
  const recentActivity = [...research.recent, ...fresh.recent]
    .sort((left, right) => String(left.recorded_at || '').localeCompare(String(right.recorded_at || '')))
    .slice(-12)
    .map((event) => ({
      type: event.type,
      recorded_at: event.recorded_at,
      action: event?.payload?.action?.id,
      title: event.type === 'transition' ? event?.payload?.action?.id : String(event.type || '').replaceAll('_', ' '),
      detail: event.type === 'transition'
        ? `${event?.payload?.after?.status || 'state'} · level ${event?.payload?.after?.progress?.levels_completed ?? 0}`
        : `event ${event.sequence ?? ''}`.trim(),
    }))
  const lastTransition = [research.last_transition, fresh.last_transition]
    .filter(Boolean)
    .sort((left, right) => String(left.recorded_at || '').localeCompare(String(right.recorded_at || '')))
    .at(-1) || null
  const catalog = await catalogRequest
  const canonicalId = root.slice(repoRoot.length + 1).split(sep).join('/')
  const runRecord = catalog.find(item => item.run_id === canonicalId)
  const [finalSummary, worldModelModified] = await Promise.all([readJsonSafe(resolve(root, 'evolution_summary.json')), fileModified(resolve(root, 'world_model.md'))])
  return {
    run_id: runId,
    game_id: config?.profile_settings?.game_id || '',
    agent_backend: config.agent_backend === 'opencode' ? 'opencode' : 'codex',
    player_model: config.player?.model || '',
    optimizer_model: config.optimizer_model || '',
    current: currentId || null,
    phase,
    active: runRecord?.status === 'running',
    process_status: runRecord?.status || 'unconfirmed',
    can_resume: Boolean(runRecord?.can_resume),
    resumed_as: runRecord?.resumed_as || null,
    finalized: Boolean(Object.keys(finalSummary).length),
    world_model_available: Boolean(worldModelModified),
    hypotheses_registered: candidateIds.length,
    hypotheses_evaluated: evaluations.length,
    max_hypotheses: config.max_evaluations ?? null,
    win_levels: evaluationLevels(latestEvaluation) ?? lastTransition?.payload?.after?.progress?.win_levels ?? config?.initial_observation?.progress?.win_levels ?? null,
    research: { actions: research.actions, levels: research.levels, events: research.events, last_event: research.last_event, last_transition: research.last_transition, budget: config?.player?.max_environment_steps ?? null },
    fresh_evaluation: { actions: fresh.actions, levels: fresh.levels, events: fresh.events, last_event: fresh.last_event, last_transition: fresh.last_transition, budget: config.fresh_solver_max_environment_steps ?? null },
    last_transition: lastTransition ? { sequence: lastTransition.sequence, action: lastTransition.payload?.action, after: lastTransition.payload?.after } : null,
    latest_fitness: latestEvaluation.fitness ?? null,
    latest_success: latestEvaluation.success ?? null,
    last_activity: lastActivityMs ? new Date(lastActivityMs).toISOString() : null,
    candidates,
    frame_sessions: candidates.flatMap((candidate) => [
      candidate.research.actions ? {
        candidate_id: candidate.candidate_id,
        phase: 'research',
        actions: candidate.research.actions,
        levels: candidate.research.levels,
        last_activity: candidate.research.last_activity,
        revision: candidate.research.revision,
        fallback_frame: candidate.research.fallback_frame,
      } : null,
      candidate.evaluation.actions ? {
        candidate_id: candidate.candidate_id,
        phase: 'evaluation',
        actions: candidate.evaluation.actions,
        levels: candidate.evaluation.levels,
        last_activity: candidate.evaluation.last_activity,
        revision: candidate.evaluation.revision,
        fallback_frame: candidate.evaluation.fallback_frame,
      } : null,
    ]).filter(Boolean),
    recent_activity: recentActivity,
  }
}

function finalGrid(frame) {
  return Array.isArray(frame) && Array.isArray(frame.at(-1)) ? frame.at(-1) : null
}

function replayResponse(session, includeRenderedFrame = true) {
  return {
    frame: [session.renderIntGrid()],
    rendered_frame: includeRenderedFrame ? puzzlescriptRuntime.renderSessionFrame(session) : null,
    state: session.handler.won ? 'WIN' : 'PLAYING',
  }
}

async function replayAction(session, action) {
  return puzzlescriptRuntime.executeAction(session, action, {
    silent: true,
    captureFrames: false,
    includeRenderedFrame: false,
  })
}

async function buildAvoRenderedFrame(runId, candidateId, phase, step = null, retried = false) {
  const root = directAvoRunPath(runId)
  if (!root || !/^x_\d+$/.test(String(candidateId || '')) || !['research', 'evaluation'].includes(phase)) {
    throw Object.assign(new Error('Invalid AVO frame session'), { statusCode: 400 })
  }
  const config = await readJsonSafe(resolve(root, 'evolution_config.json'))
  const gameId = String(config?.profile_settings?.game_id || '')
  if (!gameId) throw Object.assign(new Error('Run does not identify a PuzzleScript game'), { statusCode: 422 })
  const evidencePath = resolve(root, candidateId, phase, 'evidence.jsonl')
  const events = await readJsonLinesSafe(evidencePath)
  const selected = selectEvidenceFrame(events, step)
  const conversation = phase === 'research'
    ? await readJsonLinesSafe(resolve(root, candidateId, 'research/analysis/conversation.jsonl'))
    : []
  const reasoning = reasoningAtAction(events, conversation, step, phase)
  const storedTransition = { sequence: selected.transition.sequence, recorded_at: selected.transition.recorded_at,
    payload: { after: selected.observation, action: selected.transition.action, episode: selected.transition.episode } }
  const position = { step: selected.step, total_actions: selected.total_actions }

  const phaseRoot = resolve(root, candidateId, phase)
  const storedRenderedFrame = storedTransition?.payload?.after?.metadata?.rendered_frame
  const storedFramePath = storedRenderedFrame?.artifact_path
    ? resolve(phaseRoot, storedRenderedFrame.artifact_path)
    : storedRenderedFrame?.path ? resolve(storedRenderedFrame.path) : null
  if (storedFramePath && (storedFramePath === phaseRoot || storedFramePath.startsWith(phaseRoot + sep))) {
    try {
      const png = await fsp.readFile(storedFramePath)
      if (png.subarray(0, 8).equals(Buffer.from('\x89PNG\r\n\x1a\n', 'binary'))) {
        return {
          candidate_id: candidateId,
          phase,
          ...position,
          reasoning,
          replay_exact: true,
          source: 'stored_observation_png',
          rendered_frame: {
            data_url: `data:image/png;base64,${png.toString('base64')}`,
            mime_type: 'image/png',
            width: storedRenderedFrame.width ?? null,
            height: storedRenderedFrame.height ?? null,
          },
          fallback_frame: storedTransition?.payload?.after?.payload?.frame || [],
          transition: {
            sequence: storedTransition.sequence,
            recorded_at: storedTransition.recorded_at,
            action: storedTransition?.payload?.action || null,
            status: storedTransition?.payload?.after?.status || '',
            progress: storedTransition?.payload?.after?.progress || {},
            episode: storedTransition?.payload?.episode ?? null,
          },
        }
      }
    } catch {
      // Older or partially-written traces fall back to isolated replay below.
    }
  }

  // Historical playback uses saved observations only; it never drives a live game.
  if (step !== null) return {
    candidate_id: candidateId, phase, ...position, reasoning, replay_exact: true,
    source: 'stored_observation_grid', rendered_frame: null,
    fallback_frame: selected.observation?.payload?.frame || [], transition: selected.transition,
  }

  const cacheKey = `${runId}/${candidateId}/${phase}`
  let replay = avoFrameReplayCache.get(cacheKey)
  const prefixChanged = replay && replay.processedEvents > 0
    && events[replay.processedEvents - 1]?.sequence !== replay.lastEventSequence
  if (!replay || replay.gameId !== gameId || replay.processedEvents > events.length || prefixChanged) {
    const gameSource = puzzlescriptRuntime.loadGameSourceByName(gameId)
    if (!gameSource) throw Object.assign(new Error(`PuzzleScript game "${gameId}" was not found`), { statusCode: 404 })
    const initialized = puzzlescriptRuntime.createSessionFromSource(gameSource)
    replay = {
      gameId,
      session: initialized.session,
      processedEvents: 0,
      lastEventSequence: null,
      lastResponse: replayResponse(initialized.session, false),
      checkpoints: new Map(),
    }
  }

  for (let index = replay.processedEvents; index < events.length; index += 1) {
    const event = events[index]
    const payload = event.payload || {}
    if (event.type === 'episode_started' && Number(payload.episode || 1) > 1) {
      replay.lastResponse = await replayAction(replay.session, 'RESET')
    } else if (event.type === 'checkpoint_saved') {
      replay.checkpoints.set(String(payload.checkpoint_id), {
        levelIndex: replay.session.engine.currentLevelNum,
        actions: [...replay.session.levelActionHistory],
      })
    } else if (event.type === 'checkpoint_restored') {
      const checkpoint = replay.checkpoints.get(String(payload.checkpoint_id))
      if (!checkpoint) throw new Error(`Replay is missing ${payload.checkpoint_id}`)
      replay.session.engine.setLevel(checkpoint.levelIndex)
      replay.session.levelActionHistory = []
      for (const action of checkpoint.actions) await replayAction(replay.session, action)
      replay.lastResponse = replayResponse(replay.session, false)
    } else if (event.type === 'transition' && payload?.action?.id) {
      replay.lastResponse = await replayAction(replay.session, payload.action.id)
    }
    replay.processedEvents = index + 1
    replay.lastEventSequence = event.sequence
  }
  avoFrameReplayCache.set(cacheKey, replay)
  replay.lastResponse = replayResponse(replay.session)

  const storedFrame = storedTransition?.payload?.after?.payload?.frame
  const replayExact = JSON.stringify(finalGrid(replay.lastResponse?.frame)) === JSON.stringify(finalGrid(storedFrame))
  if (!replayExact && !retried) {
    avoFrameReplayCache.delete(cacheKey)
    return buildAvoRenderedFrame(runId, candidateId, phase, step, true)
  }
  return {
    candidate_id: candidateId,
    phase,
    ...position,
    reasoning,
    replay_exact: replayExact,
    source: 'isolated_runtime_replay',
    rendered_frame: replayExact ? replay.lastResponse?.rendered_frame || null : null,
    fallback_frame: storedFrame || [],
    transition: {
      sequence: storedTransition.sequence,
      recorded_at: storedTransition.recorded_at,
      action: storedTransition?.payload?.action || null,
      status: storedTransition?.payload?.after?.status || '',
      progress: storedTransition?.payload?.after?.progress || {},
      episode: storedTransition?.payload?.episode ?? null,
    },
  }
}

// Every run snapshot needs the catalog status; share one fetch between concurrent
// pollers and briefly reuse it (the API itself refreshes every few seconds).
let avoRunsCache = { at: 0, promise: null }
function listAvoRuns() {
  if (avoRunsCache.promise && Date.now() - avoRunsCache.at < 1500) return avoRunsCache.promise
  const promise = fetchAvoRuns()
  avoRunsCache = { at: Date.now(), promise }
  promise.catch(() => { if (avoRunsCache.promise === promise) avoRunsCache = { at: 0, promise: null } })
  return promise
}

async function fetchAvoRuns() {
  const response = await fetch(`http://127.0.0.1:${workbenchApiPort}/api/workbench/catalog`, { signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error('Workbench run catalog unavailable')
  const data = await response.json()
  return data.runs.filter(run => run.kind === 'avo' && directAvoRunPath(run.id)).map(run => ({
    run_id: run.id, modified: run.modified, status: run.status,
    can_resume: run.can_resume, resumed_as: run.resumed_as,
    label: `${run.game_id || 'AVO'} · ${run.batch} · ${run.id.split('/').slice(-2).join('/')}`,
  }))
}

function textFromContent(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(textFromContent).filter(Boolean).join('\n')
  if (!value || typeof value !== 'object') return ''
  if (typeof value.text === 'string') return value.text
  if (typeof value.content === 'string') return value.content
  return ''
}

function normalizeConversationEvent(event, index, actor) {
  const item = event?.item && typeof event.item === 'object' ? event.item : {}
  const kind = String(event.type || item.type || 'conversation')
  const role = String(event.role || 'unknown')
  if (kind === 'commandExecution') {
    const actionCommands = Array.isArray(item.commandActions)
      ? item.commandActions.map((action) => String(action?.command || '')).filter(Boolean).join('\n')
      : ''
    const command = actionCommands || textFromContent(item.command) || String(item.command || 'Command execution')
    const commandLine = command.split(/\r?\n/)[0]
    const avoTool = commandLine.match(/avo_tool\.py\s+([A-Za-z0-9_-]+)/i)
    return {
      id: `${actor}-conversation-${index}`,
      actor, role: 'tool', turn: event.turn ?? null, recorded_at: event.recorded_at,
      category: 'tools', kind, title: avoTool ? `avo_tool · ${avoTool[1]}` : 'Command',
      summary: commandLine.slice(0, 240),
      meta: [item.status, item.exitCode == null ? '' : `exit ${item.exitCode}`, item.durationMs == null ? '' : `${item.durationMs} ms`].filter(Boolean).join(' · '),
      input: command,
      body: String(item.aggregatedOutput || ''), raw: event,
    }
  }
  if (kind === 'fileChange') {
    const changes = item.changes ?? item.content ?? []
    const body = typeof changes === 'string' ? changes : JSON.stringify(changes, null, 2)
    return {
      id: `${actor}-conversation-${index}`,
      actor, role: 'tool', turn: event.turn ?? null, recorded_at: event.recorded_at,
      category: 'tools', kind, title: 'File changes',
      summary: item.status || 'Workspace updated', meta: item.status || '',
      body, raw: event,
    }
  }
  const category = kind === 'reasoning' || role === 'assistant_reasoning' ? 'reasoning' : 'conversation'
  const body = textFromContent(event.content) || textFromContent(item.content) || textFromContent(item.summary) || textFromContent(item)
  const title = category === 'reasoning' ? 'Model reasoning'
    : role === 'user' ? 'Instruction to agent'
      : role === 'assistant' ? 'Agent response' : `${role} message`
  return {
    id: `${actor}-conversation-${index}`,
    actor, role, turn: event.turn ?? null, recorded_at: event.recorded_at,
    category, kind, title, summary: body.split(/\r?\n/).find(Boolean)?.slice(0, 180) || kind,
    body, raw: event,
  }
}

function normalizeConversationEvents(events, actor) {
  const seenUserMessages = new Set()
  return events.map((event, index) => normalizeConversationEvent(event, index, actor)).filter((entry) => {
    if (entry.category === 'reasoning' && !entry.body.trim()) return false
    if (entry.category !== 'conversation' || entry.role !== 'user') return true
    const key = `${entry.turn ?? ''}:${entry.body.trim()}`
    if (seenUserMessages.has(key)) return false
    seenUserMessages.add(key)
    return true
  })
}

function normalizeWorkspaceEvent(event, index, actor) {
  const added = Object.keys(event.added || {})
  const modified = Object.keys(event.modified || {})
  const deleted = Array.isArray(event.deleted) ? event.deleted : []
  const names = [...added, ...modified, ...deleted]
  return {
    id: `${actor}-workspace-${index}`,
    actor, turn: null, recorded_at: event.recorded_at,
    category: 'workspace', kind: 'workspace_snapshot', title: event.cause || 'Workspace snapshot',
    summary: `${added.length} added · ${modified.length} modified · ${deleted.length} deleted`,
    body: names.join('\n'), raw: event,
  }
}

function normalizeEvidenceEvent(event, index, actor, phase) {
  const type = String(event.type || 'evidence')
  const payload = event.payload || {}
  const transition = type === 'transition'
  const action = payload?.action?.id || payload?.requested_action?.id || ''
  const after = payload.after || payload.observation || {}
  const level = after?.progress?.levels_completed
  return {
    id: `${actor}-${phase}-${index}`,
    actor, turn: null, recorded_at: event.recorded_at,
    category: 'environment', kind: type,
    title: transition ? `${action || 'Action'} → ${after.status || 'observation'}` : type.replaceAll('_', ' '),
    summary: transition ? [`${phase} #${event.sequence ?? index + 1}`, level == null ? '' : `level ${level}`].filter(Boolean).join(' · ') : `${phase} evidence #${event.sequence ?? index + 1}`,
    body: transition ? JSON.stringify({ action: payload.action, status: after.status, progress: after.progress, metadata: after.metadata }, null, 2) : '',
    raw: event,
  }
}

function normalizeRawEvent(event, index, actor) {
  const method = String(event.method || 'SDK event')
  const itemType = event?.payload?.item?.type
  return {
    id: `${actor}-raw-${index}`,
    actor, turn: event.turn ?? null, recorded_at: event.recorded_at,
    category: 'raw', kind: method, title: method,
    summary: itemType ? `item: ${itemType}` : event.turn_id ? `turn ${event.turn_id}` : 'App-server notification',
    body: '', raw: event,
  }
}

function normalizeRequestEvent(event, index, actor, filename, size, modified) {
  const request = event.request || {}
  const effort = request?.reasoning?.effort
  const toolCount = Array.isArray(request.tools) ? request.tools.length : Array.isArray(request.input) ? request.input.filter((item) => item?.type === 'function_call').length : 0
  return {
    id: `${actor}-request-${index}`,
    actor, turn: null, recorded_at: event.recorded_at || (modified ? new Date(modified).toISOString() : null),
    category: 'requests', kind: 'model_request', title: `${request.model || 'model'} request #${event.sequence ?? index + 1}`,
    summary: [effort ? `reasoning ${effort}` : '', `${size} bytes`, toolCount ? `${toolCount} tool items` : ''].filter(Boolean).join(' · '),
    body: filename,
    raw: { ...event, raw_body_base64: '[recorded on disk; omitted from duplicate UI view]' },
  }
}

async function requestEvents(path, actor) {
  let files = []
  try { files = (await fsp.readdir(path, { withFileTypes: true })).filter((entry) => entry.isFile() && /^request-.*\.json$/.test(entry.name)) } catch { return [] }
  return Promise.all(files.sort((left, right) => left.name.localeCompare(right.name)).map(async (entry, index) => {
    const filePath = resolve(path, entry.name)
    const stat = await fsp.stat(filePath)
    const event = await readJsonSafe(filePath)
    return normalizeRequestEvent(event, index, actor, entry.name, stat.size, stat.mtimeMs)
  }))
}

async function buildAvoLogs(runId, scope, stream, page, limit, search) {
  const runRoot = directAvoRunPath(runId)
  if (!runRoot) throw Object.assign(new Error('Invalid AVO run'), { statusCode: 400 })
  const candidateScope = typeof scope === 'string' && /^x_\d+$/.test(scope) ? scope : null
  if (scope !== 'outer' && !candidateScope) throw Object.assign(new Error('Invalid trace actor'), { statusCode: 400 })
  const actor = scope === 'outer' ? 'Outer optimizer' : candidateScope
  const analysisRoot = scope === 'outer' ? resolve(runRoot, 'optimizer_analysis') : resolve(runRoot, candidateScope, 'research/analysis')
  const candidateRoot = candidateScope ? resolve(runRoot, candidateScope) : null
  const selected = stream || 'session'
  const session = await readJsonSafe(resolve(analysisRoot, 'session.json'))
  const openCode = session.backend === 'opencode'
  let entries = []

  if (selected === 'all' || selected === 'session' || ['conversation', 'reasoning', 'tools'].includes(selected)) {
    const events = await readJsonLinesSafe(resolve(analysisRoot, 'conversation.jsonl'))
    const conversation = openCode
      ? [...events.filter(event => event.source === 'client_turn_input'), ...openCodeConversation(await readJsonLinesSafe(resolve(analysisRoot, 'opencode_events.jsonl')))]
      : events
    entries.push(...normalizeConversationEvents(conversation, actor))
  }
  if (selected === 'all' || selected === 'workspace') {
    const events = await readJsonLinesSafe(resolve(analysisRoot, 'workspace_changes.jsonl'))
    entries.push(...events.map((event, index) => normalizeWorkspaceEvent(event, index, actor)))
  }
  if (candidateRoot && (selected === 'all' || selected === 'environment')) {
    const research = await readJsonLinesSafe(resolve(candidateRoot, 'research/evidence.jsonl'))
    const evaluation = await readJsonLinesSafe(resolve(candidateRoot, 'evaluation/evidence.jsonl'))
    entries.push(...research.map((event, index) => normalizeEvidenceEvent(event, index, actor, 'research')))
    entries.push(...evaluation.map((event, index) => normalizeEvidenceEvent(event, index, actor, 'fresh evaluation')))
  }
  if (selected === 'all' || selected === 'requests') {
    entries.push(...await requestEvents(resolve(analysisRoot, 'model_requests'), actor))
  }
  if (selected === 'raw') {
    const events = await readJsonLinesSafe(resolve(analysisRoot, openCode ? 'opencode_events.jsonl' : 'app_server_events.jsonl'))
    entries.push(...events.map((event, index) => normalizeRawEvent(event, index, actor)))
  }
  if (selected === 'session') {
    entries = entries.filter((entry) => entry.category === 'conversation' || entry.category === 'tools')
  } else if (['conversation', 'reasoning', 'tools', 'workspace', 'environment', 'requests'].includes(selected)) {
    entries = entries.filter((entry) => entry.category === selected)
  }
  const needle = String(search || '').trim().toLowerCase()
  if (needle) entries = entries.filter((entry) => `${entry.title} ${entry.summary} ${entry.meta || ''} ${entry.input || ''} ${entry.body} ${entry.kind}`.toLowerCase().includes(needle))
  entries.sort((left, right) => String(left.recorded_at || '').localeCompare(String(right.recorded_at || '')) || left.id.localeCompare(right.id))
  const safeLimit = Math.max(10, Math.min(Number(limit) || 60, 120))
  const safePage = Math.max(0, Number(page) || 0)
  const end = Math.max(0, entries.length - safePage * safeLimit)
  const start = Math.max(0, end - safeLimit)
  return { actor, stream: selected, page: safePage, total: entries.length, has_more: start > 0, entries: entries.slice(start, end) }
}

const skippedArtifactParts = new Set(['.sandboxes', '.avo_rpc', '__pycache__', 'model_requests', 'workspace_blobs'])
const readableArtifactExtensions = new Set(['.json', '.jsonl', '.md', '.txt', '.py', '.toml', '.yaml', '.yml', '.log'])

function artifactRole(relativePath) {
  const parts = relativePath.split('/')
  if (parts[0] === 'optimizer_analysis') return 'Outer optimizer'
  if (!/^x_\d+$/.test(parts[0])) return 'Run record'
  if (parts.length === 2 && parts[1] === 'summary.json') return 'Summary'
  if (parts[1] === 'solver') return 'Completed solver'
  if (parts[1] === 'evaluation') return 'Fresh evaluation'
  if (parts[1] === 'research' && parts[2] === 'self_check') return 'Self-checks'
  if (parts[1] === 'research') return 'Research'
  return 'Strategy and seed'
}

async function walkArtifacts(root, current = root, result = []) {
  let entries = []
  try { entries = await fsp.readdir(current, { withFileTypes: true }) } catch { return result }
  for (const entry of entries) {
    if (skippedArtifactParts.has(entry.name)) continue
    const path = resolve(current, entry.name)
    if (entry.isDirectory()) {
      await walkArtifacts(root, path, result)
      continue
    }
    if (!entry.isFile() || !readableArtifactExtensions.has(extname(entry.name).toLowerCase())) continue
    const stat = await fsp.stat(path)
    const relativePath = path.slice(root.length + 1).split(sep).join('/')
    result.push({ path: relativePath, name: entry.name, role: artifactRole(relativePath), size: stat.size, modified: stat.mtime.toISOString() })
  }
  return result
}

async function listAvoArtifacts(runId) {
  const root = directAvoRunPath(runId)
  if (!root) throw Object.assign(new Error('Invalid AVO run'), { statusCode: 400 })
  try { if (!(await fsp.stat(root)).isDirectory()) throw new Error('missing') } catch { throw Object.assign(new Error('AVO run not found'), { statusCode: 404 }) }
  return (await walkArtifacts(root)).sort((left, right) => left.path.localeCompare(right.path))
}

async function readAvoArtifact(runId, relativePath) {
  const root = directAvoRunPath(runId)
  if (!root || typeof relativePath !== 'string') throw Object.assign(new Error('Invalid artifact path'), { statusCode: 400 })
  const path = safeResolve(root, relativePath)
  if (!path || path.split(sep).some((part) => skippedArtifactParts.has(part)) || !readableArtifactExtensions.has(extname(path).toLowerCase())) {
    throw Object.assign(new Error('Artifact is not readable here'), { statusCode: 403 })
  }
  let stat
  try { stat = await fsp.stat(path) } catch { throw Object.assign(new Error('Artifact not found'), { statusCode: 404 }) }
  if (!stat.isFile()) throw Object.assign(new Error('Artifact not found'), { statusCode: 404 })
  const handle = await fsp.open(path, 'r')
  try {
    const length = Math.min(stat.size, maxAvoArtifactBytes)
    const buffer = Buffer.alloc(length)
    await handle.read(buffer, 0, length, 0)
    return { path: relativePath, size: stat.size, truncated: stat.size > length, content: buffer.toString('utf8') }
  } finally {
    await handle.close()
  }
}

async function copySourceRoutes(outDir) {
  await Promise.all(
    sourceRoutes.map(async ({ source, buildTarget }) => {
      const target = resolve(outDir, buildTarget)
      await fsp.rm(target, { recursive: true, force: true })
      await fsp.mkdir(dirname(target), { recursive: true })
      await fsp.cp(source, target, { recursive: true })
    }),
  )
}

function experimentSourceRoutes() {
  let outDir = ''
  let command = 'serve'

  return {
    name: 'experiment-source-routes',
    configResolved(config) {
      outDir = isAbsolute(config.build.outDir)
        ? config.build.outDir
        : resolve(config.root, config.build.outDir)
      command = config.command
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = (req.url || '').split('?')[0]

        if (pathname === pseudocodeSaveRoute) {
          if (req.method !== 'POST') {
            res.setHeader('Allow', 'POST')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }

          readJsonBody(req)
            .then(async (payload) => {
              await savePseudocodeMarkdown(payload)
              sendJson(res, 200, { saved: true, file: payload.file })
            })
            .catch((error) => {
              sendJson(res, error.statusCode || 500, { error: error.message || 'Could not save Markdown' })
            })
          return
        }

        if (pathname === notesSaveRoute) {
          if (req.method !== 'POST') {
            res.setHeader('Allow', 'POST')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }

          readJsonBody(req)
            .then(async (payload) => {
              await saveNotesMarkdown(payload)
              sendJson(res, 200, { saved: true })
            })
            .catch((error) => {
              sendJson(res, error.statusCode || 500, { error: error.message || 'Could not save notes' })
            })
          return
        }

        if (pathname === avoRunsRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          listAvoRuns().then((runs) => sendJson(res, 200, { runs })).catch((error) => sendJson(res, 500, { error: error.message || 'Could not list AVO runs' }))
          return
        }

        if (pathname === avoRunRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          const requestUrl = new URL(req.url || '', 'http://127.0.0.1')
          buildAvoSnapshot(requestUrl.searchParams.get('run'))
            .then((snapshot) => sendJson(res, 200, snapshot))
            .catch((error) => sendJson(res, error.statusCode || 500, { error: error.message || 'Could not read AVO run' }))
          return
        }

        if (pathname === avoFrameRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          const requestUrl = new URL(req.url || '', 'http://127.0.0.1')
          buildAvoRenderedFrame(
            requestUrl.searchParams.get('run'),
            requestUrl.searchParams.get('candidate'),
            requestUrl.searchParams.get('phase'),
            requestUrl.searchParams.get('step'),
          )
            .then((frame) => sendJson(res, 200, frame))
            .catch((error) => sendJson(res, error.statusCode || 500, { error: error.message || 'Could not render AVO frame' }))
          return
        }

        if (pathname === avoLogsRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          const requestUrl = new URL(req.url || '', 'http://127.0.0.1')
          buildAvoLogs(
            requestUrl.searchParams.get('run'),
            requestUrl.searchParams.get('scope'),
            requestUrl.searchParams.get('stream'),
            requestUrl.searchParams.get('page'),
            requestUrl.searchParams.get('limit'),
            requestUrl.searchParams.get('search'),
          )
            .then((logs) => sendJson(res, 200, logs))
            .catch((error) => sendJson(res, error.statusCode || 500, { error: error.message || 'Could not read AVO logs' }))
          return
        }

        if (pathname === avoArtifactsRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          const requestUrl = new URL(req.url || '', 'http://127.0.0.1')
          listAvoArtifacts(requestUrl.searchParams.get('run'))
            .then((artifacts) => sendJson(res, 200, { artifacts }))
            .catch((error) => sendJson(res, error.statusCode || 500, { error: error.message || 'Could not list AVO artifacts' }))
          return
        }

        if (pathname === avoArtifactRoute) {
          if (req.method !== 'GET') {
            res.setHeader('Allow', 'GET')
            sendJson(res, 405, { error: 'Method not allowed' })
            return
          }
          const requestUrl = new URL(req.url || '', 'http://127.0.0.1')
          readAvoArtifact(requestUrl.searchParams.get('run'), requestUrl.searchParams.get('path'))
            .then((artifact) => sendJson(res, 200, artifact))
            .catch((error) => sendJson(res, error.statusCode || 500, { error: error.message || 'Could not read AVO artifact' }))
          return
        }

        const mapping = sourceRoutes.find(({ route }) => pathname.startsWith(route))
        if (!mapping) {
          next()
          return
        }

        const suffix = pathname.slice(mapping.route.length)
        const filePath = safeResolve(mapping.source, suffix)
        if (!filePath) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }

        fs.stat(filePath, (error, stat) => {
          if (error || !stat.isFile()) {
            res.statusCode = 404
            res.end('Not found')
            return
          }
          res.setHeader(
            'Content-Type',
            contentTypes[extname(filePath).toLowerCase()] || 'application/octet-stream',
          )
          fs.createReadStream(filePath).pipe(res)
        })
      })
    },
    async closeBundle() {
      if (command === 'build') {
        await copySourceRoutes(outDir)
      }
    },
  }
}

export default defineConfig({
  root: 'website',
  plugins: [experimentSourceRoutes(), gameLibraryPlugin(repoRoot)],
  resolve: {
    alias: {
      '@goal-recognition': goalRecognitionSource,
    },
  },
  server: {
    allowedHosts,
    proxy: {
      '/api/workbench': `http://127.0.0.1:${workbenchApiPort}`,
      '/api/optimal-path': `http://127.0.0.1:${workbenchApiPort}`,
    },
    fs: {
      allow: [repoRoot],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        newCampaign: resolve(__dirname, 'runs/new.html'),
        comparison: resolve(__dirname, 'runs/compare.html'),
        submission: resolve(__dirname, 'runs/submission.html'),
        avoLaunch: resolve(__dirname, 'runs/avo.html'),
        codexLaunch: resolve(__dirname, 'runs/codex.html'),
        results: resolve(__dirname, 'runs/results.html'),
        mechanics: resolve(__dirname, 'runs/mechanics.html'),
        runDetail: resolve(__dirname, 'runs/detail.html'),
        ruleAgent: resolve(__dirname, 'experiments/rule-agent.html'),
        oldContinuation: resolve(__dirname, 'experiments/avo-three-live.html'),
        notes: resolve(__dirname, 'notes.html'),
        experiments: resolve(__dirname, 'experiments/index.html'),
        goalRecognition: resolve(__dirname, 'experiments/goal-recognition.html'),
        goalRecognitionViewer: resolve(__dirname, 'experiments/goal-recognition/index.html'),
        thinkingComparison: resolve(__dirname, 'experiments/thinking-comparison.html'),
        liveFramework: resolve(__dirname, 'experiments/live-framework.html'),
        avoLab: resolve(__dirname, 'experiments/avo-lab.html'),
        paperInvestigation: resolve(__dirname, 'experiments/paper-investigation.html'),
        optimalPath: resolve(__dirname, 'experiments/optimal-path.html'),
        games: resolve(__dirname, 'games/index.html'),
        sokobanBasic: resolve(__dirname, 'games/sokoban-basic.html'),
        architecture: resolve(__dirname, 'docs/architecture.html'),
        api: resolve(__dirname, 'docs/api.html'),
      },
    },
  },
})
