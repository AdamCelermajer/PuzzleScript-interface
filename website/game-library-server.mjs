import { promises as fs } from 'node:fs'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { Worker } from 'node:worker_threads'
import { readNotebook, notebookProjection, saveNotebook } from './game-notebook-store.mjs'

async function json(path, fallback = {}) {
  try { return JSON.parse((await fs.readFile(path, 'utf8')).replace(/^\uFEFF/, '')) }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error }
}
async function entries(path) {
  try { return await fs.readdir(path, { withFileTypes: true }) }
  catch (error) { if (error.code === 'ENOENT') return []; throw error }
}
const title = id => id.replace(/^ps_/, '').replace(/-v1$/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
const error = (message, status = 400) => Object.assign(new Error(message), { statusCode: status })

export async function libraryCatalog(root) {
  const [current, older, reference, inventory] = await Promise.all([
    json(resolve(root, 'output/game-selection-20/selection.json')),
    json(resolve(root, 'benchmark/vetting/selection-v0.json')),
    json(resolve(root, 'benchmark/games/index.json')),
    json(resolve(root, 'output/game-selection-20/level-inventory.json'), []),
  ])
  const games = new Map()
  for (const [collection, rows] of [['current', current.games || []], ['curated', older.selection || []], ['reference', reference.games || []]]) {
    for (const row of rows) {
      const id = row.id || row.game_id
      if (!/^ps_[a-z0-9_]+-v\d+$/.test(id)) continue
      if (!games.has(id)) games.set(id, { id, name: row.name || title(id), difficulty: row.difficulty || row.tier || 'Unrated', collections: [], rules: row.rules || [] })
      games.get(id).collections.push(collection)
    }
  }
  for (const game of games.values()) game.levels = inventory.find(r => r.id === game.id)?.maps.length ?? null
  return { games: [...games.values()], collections: [
    { id: 'current', name: 'Current benchmark' }, { id: 'curated', name: 'Earlier curated collection' }, { id: 'reference', name: 'Reference benchmark' },
  ] }
}

export async function goalStudy(root, gameId) {
  // The published matrix normalizes provider response formats; reuse that work.
  let published = { games: [] }
  try {
    const text = await fs.readFile(resolve(root, 'studies/goal_recognition/website/app-data.js'), 'utf8')
    published = JSON.parse(text.replace(/^\s*window\.GOAL_RECOGNITION_RESULTS\s*=\s*/, '').replace(/;\s*$/, ''))
  } catch (err) { if (err.code !== 'ENOENT') throw err }
  const game = published.games.find(g => g.game_id === gameId)
  const studies = []
  if (game) studies.push({ id: published.run_id, answers: game.llm_answers, errors: game.error_count, skips: game.skip_count })
  const base = resolve(root, 'studies/goal_recognition/experiment/artifacts')
  for (const dir of await entries(base)) {
    if (!dir.isDirectory() || dir.name === published.run_id) continue
    let text
    try { text = await fs.readFile(resolve(base, dir.name, 'predictions.jsonl'), 'utf8') }
    catch (err) { if (err.code === 'ENOENT') continue; throw err }
    const answers = text.split(/\r?\n/).flatMap(line => {
      if (!line.trim()) return []
      let row; try { row = JSON.parse(line) } catch { return [] }
      if (row.game_id !== gameId) return []
      return [{ model: row.model, evidence_mode: row.evidence_mode || row.variant, input_mode: row.input_mode || row.condition,
        prediction: { ...row.prediction,
          goal_guess: row.prediction?.goal_guess || row.raw_response?.likely_goal || row.raw_response?.goal || '',
          win_condition_guess: row.prediction?.win_condition_guess || row.raw_response?.success_condition || '' } }]
    })
    if (answers.length) studies.push({ id: dir.name, answers })
  }
  return { studies, human_answers: game?.human_answers || [], first_frame: game?.first_llm_frame || null,
    screenshot: game?.screenshot ? '/experiments/goal-recognition/' + game.screenshot : null }
}

async function archivedRules(root, gameId) {
  const records = [], base = resolve(root, 'client/rules', gameId)
  async function visit(path, label, depth) {
    const files = await entries(path)
    const names = files.filter(f => f.isFile()).map(f => f.name)
    if (names.includes('rules.json') || names.includes('natural_rules.json')) {
      const config = await json(resolve(path, 'run_config.json'))
      records.push({ id: label, config: { model: config.model },
        natural: await json(resolve(path, 'natural_rules.json'), null), rules: await json(resolve(path, 'rules.json'), null) })
    }
    if (depth) for (const dir of files.filter(f => f.isDirectory())) await visit(resolve(path, dir.name), `${label}/${dir.name}`, depth - 1)
  }
  await visit(base, `client/rules/${gameId}`, 3)
  return records
}

async function sourceRuleBlock(root, gameId) {
  const source = `puzzlescript_interface/games/${gameId}/script.txt`
  let lines
  try { lines = (await fs.readFile(resolve(root, source), 'utf8')).split(/\r?\n/) }
  catch (err) { if (err.code === 'ENOENT') return null; throw err }
  const heading = name => lines.findIndex(line => line.trim().toUpperCase() === name)
  const rules = heading('RULES'), win = heading('WINCONDITIONS'), levels = heading('LEVELS')
  if (rules < 0 || win <= rules) return null
  return { source, rules_line: rules + 1, rules: lines.slice(rules + 1, win).join('\n').trim(),
    win_line: win + 1, winconditions: lines.slice(win + 1, levels > win ? levels : undefined).join('\n').trim() }
}

export async function libraryDetail(root, gameId) {
  const game = (await libraryCatalog(root)).games.find(g => g.id === gameId)
  if (!game) throw error('Unknown benchmark game', 404)
  const [notebook, goals, legacy, source_rules] = await Promise.all([
    readNotebook(root), goalStudy(root, gameId), archivedRules(root, gameId), sourceRuleBlock(root, gameId),
  ])
  const annotations = notebookProjection(notebook, true)
  const searches = []
  const bfs = resolve(root, 'experiement/bfs_solver')
  for (const entry of await entries(bfs)) {
    if (!entry.isFile() || !/(?:^results|_results).*\.json$/.test(entry.name)) continue
    const data = await json(resolve(bfs, entry.name))
    for (const result of data.results || []) if (result.gameId === gameId) {
      searches.push({ source: `experiement/bfs_solver/${entry.name}`, date: data.generatedAt, solver: data.solver || 'BFS search', ...result })
    }
  }
  return { ...game, goals, legacy, searches, source_rules, rule_source: 'output/game-selection-20/selection.json',
    annotation_source: 'output/game-selection-20/level-annotations.mjs',
    mechanic_sources: (notebook.annotations[gameId] || []).map((item, source_index) => ({ ...item, source_index })),
    annotation_method: annotations.methodology, annotations: (annotations.levels || []).filter(l => l.game_id === gameId) }
}

// Each manual game owns a separate worker. It never shares an agent's session or logs.
export function createPlayer(root) {
  const sessions = new Map()
  async function remove(id) { const record = sessions.get(id); if (record) { sessions.delete(id); await record.worker.terminate() } }
  const cleanup = setInterval(() => { for (const [id, r] of sessions) if (Date.now() - r.touched > 30 * 60_000) void remove(id) }, 60_000)
  cleanup.unref()
  async function request(payload) {
    let record, id = payload.session
    if (!id) {
      const game = (await libraryCatalog(root)).games.find(g => g.id === payload.game)
      if (!game) throw error('Unknown benchmark game', 404)
      if (sessions.size >= 24) throw error('Too many open games. Close a play session first.', 429)
      id = randomUUID()
      record = { worker: new Worker(resolve(root, 'website/game-player-worker.cjs'), { workerData: { root, game: game.id } }), touched: Date.now(), busy: false }
      sessions.set(id, record)
    } else record = sessions.get(id)
    if (!record) throw error('This play session expired. Start the game again.', 404)
    if (record.busy) throw error('A move is already in progress.', 409)
    record.busy = true; record.touched = Date.now()
    try {
      return await new Promise((resolveRequest, reject) => {
        const clear = () => { clearTimeout(timer); record.worker.off('message', message); record.worker.off('error', fail); record.worker.off('exit', exited) }
        const fail = err => { clear(); reject(err) }
        const exited = () => fail(error('Play session closed.', 410))
        const message = result => { clear(); result.error ? reject(error(result.error)) : resolveRequest({ session: id, ...result }) }
        const timer = setTimeout(() => fail(error('The game took too long to respond. Start it again.', 504)), 15_000)
        record.worker.once('message', message); record.worker.once('error', fail); record.worker.once('exit', exited)
        record.worker.postMessage({ level: payload.level, action: payload.action })
      })
    } catch (err) { await remove(id); throw err } finally { record.busy = false }
  }
  return { request, remove, async close() { clearInterval(cleanup); await Promise.all([...sessions.keys()].map(remove)) } }
}

export function gameLibraryPlugin(root) {
  const player = createPlayer(root)
  const install = server => {
    server.middlewares.use(async (req, res, next) => {
      const url = new URL(req.url || '/', 'http://localhost')
      if (!url.pathname.startsWith('/__games/')) return next()
      res.setHeader('Content-Type', 'application/json; charset=utf-8'); res.setHeader('Cache-Control', 'no-store')
      try {
        let result
        if (url.pathname === '/__games/catalog' && req.method === 'GET') result = await libraryCatalog(root)
        else if (url.pathname === '/__games/detail' && req.method === 'GET') result = await libraryDetail(root, url.searchParams.get('game'))
        else if (url.pathname === '/__games/notes' && req.method === 'POST') {
          if (!req.headers['content-type']?.startsWith('application/json')) throw error('JSON is required.', 415)
          if (req.headers.origin && new URL(req.headers.origin).host !== req.headers.host) throw error('Save notes from this workbench page.', 403)
          let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 150000) throw error('Note is too large.', 413) }
          result = await saveNotebook(root, JSON.parse(body))
        }
        else if (url.pathname === '/__games/play' && req.method === 'DELETE') { await player.remove(url.searchParams.get('session')); result = { closed: true } }
        else if (url.pathname === '/__games/play' && req.method === 'POST') {
          let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 2048) throw error('Request too large', 413) }
          result = await player.request(JSON.parse(body))
        } else throw error('Unknown game library operation', 404)
        res.end(JSON.stringify(result))
      } catch (err) { res.statusCode = err.statusCode || 500; res.end(JSON.stringify({ error: err.message })) }
    })
    server.httpServer?.once('close', () => void player.close())
  }
  return { name: 'game-library', configureServer: install, configurePreviewServer: install }
}
