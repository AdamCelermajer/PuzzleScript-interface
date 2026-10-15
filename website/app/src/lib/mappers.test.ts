import { describe, expect, it } from 'vitest'
import { bestSoFar, firstSuccess, levelCurve } from './compare'
import { entryText, newEntryText, previewParts, slugify } from './diary'
import { fromAgentEvent, fromAvoLog, fromLegacyTranscript } from './events'

describe('agent events', () => {
  it('maps agent-event-v1 commands with input, output and exit code', () => {
    const item = fromAgentEvent({ type: 'command', text: 'ls -la\necho', output: 'a\nb', exit_code: 2, turn: 3, t: '2026-10-15T09:00:00Z' }, 0)
    expect(item).toMatchObject({ kind: 'command', input: 'ls -la\necho', body: 'a\nb', meta: 'exit 2', turn: 3, summary: 'ls -la' })
  })

  it('summarizes usage events', () => {
    expect(fromAgentEvent({ type: 'usage', usage: { input: 10, output: 2 } }, 1).summary).toBe('in 10 · out 2 · reasoning 0 · cached 0')
  })

  it('maps unknown types to other', () => {
    expect(fromAgentEvent({ type: 'weird' }, 2).kind).toBe('other')
  })

  it('maps AVO console log entries by category', () => {
    const base = { id: 'x', actor: 'outer', turn: 1, recorded_at: null, kind: 'k', title: 'Tool · shell', summary: 's' }
    expect(fromAvoLog({ ...base, category: 'reasoning' }).kind).toBe('reasoning')
    expect(fromAvoLog({ ...base, category: 'tools' }).kind).toBe('tool')
    expect(fromAvoLog({ ...base, category: 'environment' }).kind).toBe('environment')
  })

  it('reads legacy transcript.jsonl prompt/response pairs', () => {
    const items = fromLegacyTranscript([JSON.stringify({ decision: 1, prompt: 'Frame…', response: { action: 'ACTION1' } }), 'not json', ''].join('\n'))
    expect(items.map((i) => i.kind)).toEqual(['prompt', 'message'])
    expect(items[1].body).toContain('ACTION1')
  })
})

describe('compare curves', () => {
  it('computes best fitness so far per evaluation', () => {
    expect(bestSoFar([{ fitness: 1 }, { fitness: 0 }, { fitness: 3 }])).toEqual([{ x: 1, y: 1 }, { x: 2, y: 1 }, { x: 3, y: 3 }])
    expect(firstSuccess([{ success: false }, { success: true }])).toBe(2)
  })

  it('keeps level change points from transitions.jsonl', () => {
    const lines = [1, 2, 3, 4].map((i) => JSON.stringify({ action_index: i, after: { levels_completed: i >= 3 ? 1 : 0, win_levels: 6 } }))
    expect(levelCurve(lines.join('\n'))).toEqual({ points: [{ x: 0, y: 0 }, { x: 3, y: 1 }, { x: 4, y: 1 }], total: 6 })
  })
})

describe('diary', () => {
  it('builds a template the API accepts (front matter + four sections)', () => {
    const text = newEntryText('2026-10-15', 'SPA: first look', ['workbench'])
    expect(text).toContain('title: "SPA: first look"')
    expect(text).toContain('threads: [workbench]')
    expect(text.match(/^## (Did|Found|Decided|Next)$/gm)).toEqual(['## Did', '## Found', '## Decided', '## Next'])
    expect(previewParts(text).title).toBe('SPA: first look')
  })

  it('round-trips an entry for the raw editor', () => {
    const text = entryText({ date: '2026-10-01', title: 'Plain', threads: ['a', 'b'], explicit_runs: ['output/x'], commits: ['abc1234'], docs: [], reconstructed: true, body: '## Did\n- x\n' })
    expect(text.split('\n').slice(0, 9)).toEqual(['---', 'date: 2026-10-01', 'title: Plain', 'threads: [a, b]', 'runs: [output/x]', 'commits: [abc1234]', 'docs: []', 'reconstructed: true', '---'])
  })

  it('slugifies titles', () => {
    expect(slugify('Qwen 3.8: Modality & more!')).toBe('qwen-3-8-modality-more')
  })
})
