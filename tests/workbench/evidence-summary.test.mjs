import assert from 'node:assert/strict'
import { mkdtemp, writeFile, appendFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { readEvidenceSummary } from '../../website/evidence-summary.mjs'

test('evidence summary retains counts, final transition and recent activity as a file grows', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'workbench-evidence-'))
  const path = join(dir, 'evidence.jsonl')
  const events = [
    { type: 'episode_started', recorded_at: '2026-01-01T00:00:00Z' },
    { type: 'transition', sequence: 2, recorded_at: '2026-01-01T00:00:01Z', payload: { after: { progress: { levels_completed: 1 } } } },
    { type: 'transition', sequence: 3, recorded_at: '2026-01-01T00:00:02Z', payload: { after: { progress: { levels_completed: 3 } } } },
    { type: 'checkpoint_saved', sequence: 4, recorded_at: '2026-01-01T00:00:03Z' },
  ]
  try {
    await writeFile(path, events.map(event => JSON.stringify(event)).join('\n') + '\ninvalid json\n')
    const first = await readEvidenceSummary(path, 2)
    assert.equal(first.events, 4)
    assert.equal(first.actions, 2)
    assert.equal(first.levels, 3)
    assert.equal(first.last_event, 'checkpoint_saved')
    assert.equal(first.last_transition.sequence, 3)
    assert.deepEqual(first.recent.map(event => event.sequence), [3, 4])
    assert.equal(await readEvidenceSummary(path, 2), first)

    await appendFile(path, JSON.stringify({ type: 'transition', sequence: 5, recorded_at: '2026-01-01T00:00:04Z', payload: { after: { progress: { levels_completed: 2 } } } }) + '\n')
    const updated = await readEvidenceSummary(path, 2)
    assert.equal(updated.events, 5)
    assert.equal(updated.actions, 3)
    assert.equal(updated.levels, 3)
    assert.equal(updated.last_transition.sequence, 5)
    assert.deepEqual(updated.recent.map(event => event.sequence), [4, 5])
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
})
