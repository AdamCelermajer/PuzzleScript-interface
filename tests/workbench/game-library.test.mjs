import test from 'node:test'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { libraryCatalog, libraryDetail, createPlayer } from '../../website/game-library-server.mjs'

const root = resolve(import.meta.dirname, '../..')

test('library retains all benchmark collections without duplicate game identities', async () => {
  const { games } = await libraryCatalog(root)
  assert.equal(games.filter(g => g.collections.includes('current')).length, 20)
  assert.equal(games.filter(g => g.collections.includes('curated')).length, 30)
  assert.equal(games.filter(g => g.collections.includes('reference')).length, 21)
  assert.equal(new Set(games.map(g => g.id)).size, games.length)
  assert.equal(games.find(g => g.id === 'ps_feeling_like_filling-v1').rules.some(r => r.includes('duplication')), true)
})

test('game notebook joins studies, reviewed rules and level evidence by exact game ID', async () => {
  const d = await libraryDetail(root, 'ps_2d_whale_world-v1')
  assert.equal(d.goals.studies.length, 2)
  assert.equal(d.goals.studies.reduce((n, s) => n + s.answers.length, 0), 16)
  assert.ok(d.goals.studies.every(s => s.answers.every(a => a.prediction.goal_guess)))
  assert.ok(d.goals.studies[1].answers.some(a => a.prediction.win_condition_guess))
  assert.equal(d.rules.length, 4)
  assert.ok(d.annotations.every(l => l.game_id === d.id))
  const archived = await libraryDetail(root, 'ps_slidings-v1')
  assert.ok(archived.legacy.some(r => r.natural.rules.length > 0))
  await assert.rejects(libraryDetail(root, '../.env'), /Unknown benchmark game/)
})

test('rule comparison exposes the actual PuzzleScript rules and win conditions', async () => {
  for (const [id, rule, win] of [
    ['ps_modality-v1', 'Player White | Black', 'All Crate on Target'],
    ['ps_knightoban-v1', 'normalcrate', 'All Target on crates'],
    ['ps_icecrates-v1', 'LEFT [ PlayerL | Crate ]', 'Some PlayerStill on Goal'],
  ]) {
    const game = await libraryDetail(root, id)
    assert.ok(game.rules.length)
    assert.ok(game.source_rules.rules.includes(rule))
    assert.ok(game.source_rules.winconditions.includes(win))
    assert.ok(game.source_rules.source.endsWith(`${id}/script.txt`))
  }
})

test('manual player keeps sessions independent and supports undo, restart and level selection', async () => {
  const player = createPlayer(root)
  try {
    const first = await player.request({ game: 'ps_modality-v1' })
    const second = await player.request({ game: 'ps_modality-v1' })
    assert.notEqual(first.session, second.session)
    assert.equal(first.image.data_url, second.image.data_url)
    await player.request({ session: first.session, action: 'ACTION3' })
    const undo = await player.request({ session: first.session, action: 'ACTION7' })
    assert.equal(undo.image.data_url, first.image.data_url)
    await player.request({ session: first.session, action: 'ACTION3' })
    const restart = await player.request({ session: first.session, action: 'RESET' })
    assert.equal(restart.image.data_url, first.image.data_url)
    const next = await player.request({ session: first.session, level: 1 })
    assert.equal(next.level, 1)
    assert.equal((await player.request({ session: second.session })).image.data_url, second.image.data_url)
    await player.remove(first.session)
    await assert.rejects(player.request({ session: first.session }), /expired/)
    await assert.rejects(player.request({ game: '../.env' }), /Unknown benchmark game/)
  } finally { await player.close() }
})
