// Isolated PuzzleScript replay for the AVO console's live frame view.
// One JSON request per stdin line, one JSON reply per stdout line. It replays
// saved evidence only; it never drives a campaign session or a shared service.
'use strict'
// The runtime logs to stdout; keep stdout for the protocol.
console.log = (...args) => console.error(...args)

const fs = require('fs')
const path = require('path')
const readline = require('readline')
const runtime = require(path.resolve(__dirname, '../puzzlescript_interface/runtime/server.js'))

const cache = new Map()
const maxCached = 64

function readJsonLines(file) {
  try {
    return fs.readFileSync(file, 'utf8').split(/\r?\n/).flatMap((line) => {
      if (!line.trim()) return []
      try {
        const value = JSON.parse(line)
        return value && typeof value === 'object' ? [value] : []
      } catch { return [] }
    })
  } catch { return [] }
}

function replayResponse(session, includeRenderedFrame = true) {
  return {
    frame: [session.renderIntGrid()],
    rendered_frame: includeRenderedFrame ? runtime.renderSessionFrame(session) : null,
  }
}

function replayAction(session, action) {
  return runtime.executeAction(session, action, { silent: true, captureFrames: false, includeRenderedFrame: false })
}

async function replay({ game_id: gameId, key, evidence_path: evidencePath, reset }) {
  if (reset) cache.delete(key)
  const events = readJsonLines(evidencePath)
  let state = cache.get(key)
  const prefixChanged = state && state.processedEvents > 0
    && events[state.processedEvents - 1]?.sequence !== state.lastEventSequence
  if (!state || state.gameId !== gameId || state.processedEvents > events.length || prefixChanged) {
    const source = runtime.loadGameSourceByName(gameId)
    if (!source) throw Object.assign(new Error(`PuzzleScript game "${gameId}" was not found`), { statusCode: 404 })
    const initialized = runtime.createSessionFromSource(source)
    state = { gameId, session: initialized.session, processedEvents: 0, lastEventSequence: null, checkpoints: new Map() }
  }
  for (let index = state.processedEvents; index < events.length; index += 1) {
    const event = events[index]
    const payload = event.payload || {}
    if (event.type === 'episode_started' && Number(payload.episode || 1) > 1) {
      await replayAction(state.session, 'RESET')
    } else if (event.type === 'checkpoint_saved') {
      state.checkpoints.set(String(payload.checkpoint_id), {
        levelIndex: state.session.engine.currentLevelNum,
        actions: [...state.session.levelActionHistory],
      })
    } else if (event.type === 'checkpoint_restored') {
      const checkpoint = state.checkpoints.get(String(payload.checkpoint_id))
      if (!checkpoint) throw new Error(`Replay is missing ${payload.checkpoint_id}`)
      state.session.engine.setLevel(checkpoint.levelIndex)
      state.session.levelActionHistory = []
      for (const action of checkpoint.actions) await replayAction(state.session, action)
    } else if (event.type === 'transition' && payload?.action?.id) {
      await replayAction(state.session, payload.action.id)
    }
    state.processedEvents = index + 1
    state.lastEventSequence = event.sequence
  }
  cache.delete(key)
  cache.set(key, state)
  if (cache.size > maxCached) cache.delete(cache.keys().next().value)
  return replayResponse(state.session)
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })
let queue = Promise.resolve()
lines.on('line', (line) => {
  queue = queue.then(async () => {
    let request = {}
    try {
      request = JSON.parse(line)
      const result = await replay(request)
      process.stdout.write(JSON.stringify({ id: request.id, ok: true, ...result }) + '\n')
    } catch (error) {
      process.stdout.write(JSON.stringify({ id: request.id, ok: false, error: error.message || String(error), status: error.statusCode || 500 }) + '\n')
    }
  })
})
lines.on('close', () => process.exit(0))
