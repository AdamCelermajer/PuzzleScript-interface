import test from 'node:test'
import assert from 'node:assert/strict'
import { promises as fs } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { readNotebook, saveNotebook, notebookProjection } from '../../website/game-notebook-store.mjs'

const source = resolve(import.meta.dirname, '../../output/game-selection-20')
async function fixture(t) {
  const root = await fs.mkdtemp(resolve(tmpdir(), 'game-notebook-test-'))
  const dir = resolve(root, 'output/game-selection-20')
  await fs.mkdir(dir, { recursive: true })
  for (const file of ['selection.json', 'level-annotations.mjs', 'level-inventory.json', 'level-annotation-detail.json']) await fs.copyFile(resolve(source, file), resolve(dir, file))
  t.after(async () => { assert.equal(dirname(root), resolve(tmpdir())); assert.ok(root.includes('game-notebook-test-')); await fs.rm(root, { recursive: true, force: true }) })
  return root
}

test('reviewed rule saves to the original selection file and stale edits cannot overwrite it', async t => {
  const root = await fixture(t), initial = await readNotebook(root), game = 'ps_feeling_like_filling-v1'
  const before = initial.selection.games.find(g => g.id === game).rules[1]
  await saveNotebook(root, { game, kind: 'rule', index: 1, before, value: before })
  assert.deepEqual((await readNotebook(root)).texts, initial.texts)
  const result = await saveNotebook(root, { game, kind: 'rule', index: 1, before, value: 'Moving away duplicates the crate.' })
  assert.equal(result.saved, '2. Moving away duplicates the crate.')
  const stored = JSON.parse(await fs.readFile(resolve(root, result.file), 'utf8'))
  assert.equal(stored.games.find(g => g.id === game).rules[1], result.saved)
  assert.deepEqual(stored.games.filter(g => g.id !== game), initial.selection.games.filter(g => g.id !== game))
  await assert.rejects(saveNotebook(root, { game, kind: 'rule', index: 1, before, value: 'Stale edit' }), e => e.statusCode === 409)
  assert.equal((await readNotebook(root)).selection.games.find(g => g.id === game).rules[1], result.saved)
})

test('shared mechanic edits persist in the original module and regenerate every affected level', async t => {
  const root = await fixture(t), initial = await readNotebook(root), game = 'ps_feeling_like_filling-v1'
  const before = initial.annotations[game][1], evidence = 'A player\'s "copy" stays behind.\nLiteral ${data}; `notes`.'
  const result = await saveNotebook(root, { game, kind: 'mechanic', index: 1, before, value: { ...before, evidence } })
  const reloaded = await readNotebook(root)
  assert.equal(reloaded.annotations[game][1].evidence, evidence)
  assert.ok(result.annotations.every(l => l.mechanics.find(m => m.source_index === 1).evidence === evidence))
  assert.deepEqual(reloaded.annotations['ps_modality-v1'], initial.annotations['ps_modality-v1'])
  const projection = JSON.parse(await fs.readFile(resolve(root, 'output/game-selection-20/level-annotation-detail.json'), 'utf8'))
  assert.deepEqual(projection, notebookProjection(reloaded))
  await saveNotebook(root, { game, kind: 'mechanic', index: 1, before: reloaded.annotations[game][1], value: { ...reloaded.annotations[game][1], levels: '2' } })
  const changed = notebookProjection(await readNotebook(root), true).levels.filter(l => l.game_id === game)
  assert.deepEqual(changed.filter(l => l.mechanics.some(m => m.source_index === 1)).map(l => l.level), [2])
})

test('invalid fields and level ranges leave original files unchanged', async t => {
  const root = await fixture(t), initial = await readNotebook(root), game = 'ps_modality-v1', before = initial.annotations[game][0]
  for (const levels of ['0', '3-2', '1-999', 'anything']) await assert.rejects(saveNotebook(root, { game, kind: 'mechanic', index: 0, before, value: { ...before, levels } }))
  await assert.rejects(saveNotebook(root, { game, kind: 'world_model', index: 0, before, value: 'Overwrite a report' }))
  await assert.rejects(saveNotebook(root, { game: '../.env', kind: 'rule', index: 0, before: '', value: 'x' }))
  assert.deepEqual((await readNotebook(root)).texts, initial.texts)
})

test('level focus updates its source and concurrent edits preserve both rule changes', async t => {
  const root = await fixture(t), initial = await readNotebook(root)
  await saveNotebook(root, { game: 'ps_midas-v1', kind: 'focus', index: 0, before: initial.midasFocus[0], value: 'A revised first-level observation.' })
  const reread = await readNotebook(root)
  assert.equal(reread.midasFocus[0], 'A revised first-level observation.')
  assert.deepEqual(reread.midasFocus.slice(1), initial.midasFocus.slice(1))
  const game = 'ps_modality-v1', rules = initial.selection.games.find(g => g.id === game).rules
  await Promise.all([0, 1].map(index => saveNotebook(root, { game, kind: 'rule', index, before: rules[index], value: `Edited rule ${index + 1}.` })))
  assert.deepEqual((await readNotebook(root)).selection.games.find(g => g.id === game).rules.slice(0, 2), ['1. Edited rule 1.', '2. Edited rule 2.'])
})
