import { promises as fs } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createHash, randomUUID } from 'node:crypto'

const fail = (message, statusCode = 400) => Object.assign(new Error(message), { statusCode })
const parse = text => JSON.parse(text.replace(/^\uFEFF/, ''))
const stringify = (value, original) => JSON.stringify(value, null, 2).replaceAll('\n', original.includes('\r\n') ? '\r\n' : '\n') + (original.endsWith('\n') ? (original.includes('\r\n') ? '\r\n' : '\n') : '')
const base = root => resolve(root, 'output/game-selection-20')
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

export function annotationLevels(value, maximum) {
  if (value === 'none') return []
  if (typeof value !== 'string' || !/^\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*$/.test(value)) throw fail('Use levels such as 1-4, 6, or none.')
  const result = []
  for (const range of value.split(',')) {
    const [start, end = start] = range.trim().split('-').map(Number)
    if (start < 1 || end < start || end > maximum) throw fail(`Levels must be between 1 and ${maximum}.`)
    for (let n = start; n <= end; n++) result.push(n)
  }
  return [...new Set(result)]
}

export async function readNotebook(root) {
  const dir = base(root)
  const names = ['selection.json', 'level-annotations.mjs', 'level-inventory.json', 'level-annotation-detail.json']
  const texts = Object.fromEntries(await Promise.all(names.map(async name => [name, await fs.readFile(resolve(dir, name), 'utf8')])))
  const selection = parse(texts['selection.json']), inventory = parse(texts['level-inventory.json'])
  // Import only the existing, fixed annotation module. User text is written as quoted string data.
  const hash = createHash('sha256').update(texts['level-annotations.mjs']).digest('hex')
  const module = await import(pathToFileURL(resolve(dir, 'level-annotations.mjs')).href + `?revision=${hash}`)
  const annotations = structuredClone(module.annotations), midasFocus = [...module.midasFocus]
  const methodology = parse(texts['level-annotation-detail.json']).methodology
  return { dir, texts, selection, inventory, annotations, midasFocus, methodology }
}

export function notebookProjection(notebook, includeIds = false) {
  const levels = notebook.inventory.flatMap(game => game.maps.map((map, i) => ({
    game_id: game.id, level: i + 1, engine_index: map.engine_index, source_line: map.source_line,
    mechanics: (notebook.annotations[game.id] || []).flatMap((annotation, index) =>
      annotationLevels(annotation.levels, game.maps.length).includes(i + 1)
        ? [{ ...annotation, ...(includeIds ? { source_index: index } : {}) }] : []),
    focus: game.id === 'ps_midas-v1' ? notebook.midasFocus[i] || '' : '',
  })))
  return { methodology: notebook.methodology, levels }
}

function replaceAnnotation(source, gameId, index, item) {
  let game, position = 0, found = false
  const result = source.split(/(?<=\n)/).map(line => {
    const use = line.match(/^use\(['"]([a-z0-9_]+)['"]\);/)
    if (use) { game = `ps_${use[1]}-v1`; position = 0 }
    if (game === gameId && /^a\(/.test(line) && position++ === index) {
      found = true
      const ending = line.endsWith('\r\n') ? '\r\n' : line.endsWith('\n') ? '\n' : ''
      return `a(${[item.rule, item.mechanic, item.levels, item.introduction, item.evidence].map(v => JSON.stringify(v)).join(',')});${ending}`
    }
    return line
  }).join('')
  if (!found) throw fail('The annotation source layout changed. Reload before editing.', 409)
  return result
}

function replaceFocus(source, index, value) {
  const start = source.indexOf('export const midasFocus = [')
  if (start < 0) throw fail('The level-note source layout changed.', 409)
  const lines = source.slice(start).split(/(?<=\n)/)
  if (!/^\s*['"]/.test(lines[index + 1] || '')) throw fail('The level-note source layout changed.', 409)
  const previous = lines[index + 1], ending = previous.endsWith('\r\n') ? '\r\n' : previous.endsWith('\n') ? '\n' : ''
  lines[index + 1] = ` ${JSON.stringify(value)}${previous.trimEnd().endsWith(',') ? ',' : ''}${ending}`
  return source.slice(0, start) + lines.join('')
}

async function commitFiles(dir, originals, changes) {
  const staged = [], applied = []
  try {
    for (const [name, text] of Object.entries(changes)) {
      const path = resolve(dir, name), temp = `${path}.${randomUUID()}.tmp`
      await fs.writeFile(temp, text, 'utf8'); staged.push({ name, path, temp })
    }
    for (const { name, path } of staged) if (await fs.readFile(path, 'utf8') !== originals[name]) throw fail('The source file changed while saving. Reload and try again.', 409)
    for (const row of staged) { await fs.rename(row.temp, row.path); applied.push(row) }
  } catch (error) {
    for (const row of applied.reverse()) { await fs.writeFile(row.temp, originals[row.name], 'utf8'); await fs.rename(row.temp, row.path) }
    throw error
  } finally { await Promise.all(staged.map(row => fs.rm(row.temp, { force: true }))) }
}

let writes = Promise.resolve()
export function saveNotebook(root, payload) {
  const result = writes.then(() => save(root, payload))
  writes = result.catch(() => {})
  return result
}

async function save(root, { game, kind, index, before, value }) {
  if (!/^ps_[a-z0-9_]+-v\d+$/.test(game || '') || !Number.isInteger(index) || index < 0) throw fail('Invalid notebook entry.')
  const notebook = await readNotebook(root)
  const selected = notebook.selection.games.find(g => g.id === game)
  if (!selected) throw fail('This game has no editable source notebook.', 404)
  const changes = {}, text = v => {
    if (typeof v !== 'string' || !v.trim() || v.length > 16000) throw fail('Enter between 1 and 16,000 characters.')
    return v.trim()
  }
  const conflict = () => { throw fail('This note changed since you opened it. Your draft is kept. Cancel and reopen the editor to load the current note.', 409) }
  let saved, file
  if (kind === 'rule') {
    const original = selected.rules[index]
    if (original == null) throw fail('Unknown reviewed rule.', 404)
    if (before !== original) conflict()
    saved = (original.match(/^\d+\.\s*/)?.[0] || '') + text(value).replace(/^\d+\.\s*/, '')
    selected.rules[index] = saved; file = 'selection.json'
    if (saved !== original) changes[file] = stringify(notebook.selection, notebook.texts[file])
  } else if (kind === 'mechanic') {
    const original = notebook.annotations[game]?.[index]
    if (!original) throw fail('Unknown mechanic annotation.', 404)
    if (!same(before, original)) conflict()
    saved = { rule: original.rule, mechanic: text(value?.mechanic), levels: text(value?.levels), introduction: text(value?.introduction), evidence: text(value?.evidence) }
    annotationLevels(saved.levels, notebook.inventory.find(g => g.id === game).maps.length)
    notebook.annotations[game][index] = saved; file = 'level-annotations.mjs'
    if (!same(saved, original)) changes[file] = replaceAnnotation(notebook.texts[file], game, index, saved)
  } else if (kind === 'focus' && game === 'ps_midas-v1') {
    const original = notebook.midasFocus[index]
    if (original == null) throw fail('Unknown level note.', 404)
    if (before !== original) conflict()
    saved = text(value); notebook.midasFocus[index] = saved; file = 'level-annotations.mjs'
    if (saved !== original) changes[file] = replaceFocus(notebook.texts[file], index, saved)
  } else throw fail('Only reviewed rules and source-derived level notes are editable.')
  if (kind !== 'rule' && changes[file]) changes['level-annotation-detail.json'] = stringify(notebookProjection(notebook), notebook.texts['level-annotation-detail.json'])
  await commitFiles(notebook.dir, notebook.texts, changes)
  return { saved, file: `output/game-selection-20/${file}`, rules: selected.rules,
    annotations: notebookProjection(notebook, true).levels.filter(l => l.game_id === game),
    mechanic_sources: notebook.annotations[game].map((item, source_index) => ({ ...item, source_index })) }
}
