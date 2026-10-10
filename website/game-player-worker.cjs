const { parentPort, workerData } = require('node:worker_threads')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { Parser } = require('puzzlescript')
const runtime = require('../puzzlescript_interface/runtime/server.js')
const source = readFileSync(resolve(workerData.root, 'puzzlescript_interface/games', workerData.game, 'script.txt'), 'utf8').replace(/\r\n?/g, '\n')
let data, session
parentPort.on('message', async ({ level, action }) => {
  try {
    if (!data) data = Parser.parse(source).data
    const levels = data.levels.flatMap((l, index) => l.type === 'LEVEL_MAP' ? [index] : [])
    if (!session || level != null) {
      const ordinal = level ?? 0
      if (!Number.isInteger(ordinal) || ordinal < 0 || ordinal >= levels.length) throw new Error('Unknown playable level')
      session = new runtime.Session('manual-library', data, levels[ordinal])
    }
    if (action) {
      if (![...session.availableActions, 'RESET'].includes(action)) throw new Error('This action is unavailable in this game')
      await runtime.executeAction(session, action, { silent: true, captureFrames: false, includeRenderedFrame: false })
    }
    parentPort.postMessage({ image: runtime.renderSessionFrame(session), state: session.handler.won ? 'WIN' : 'PLAYING',
      level: levels.indexOf(session.engine.currentLevelNum), levels: levels.length, available_actions: session.availableActions })
  } catch (err) { parentPort.postMessage({ error: err.message }) }
})
