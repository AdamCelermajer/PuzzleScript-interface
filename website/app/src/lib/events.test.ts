import { describe, expect, it } from 'vitest'
import { diffLines, fromAgentEvent, withPrompts } from './events'
import { readableFile } from './files'

describe('run page extras', () => {
  const items = [
    fromAgentEvent({ type: 'reasoning', turn: 1, text: 'think' }, 0),
    fromAgentEvent({ type: 'file_change', turn: 1, text: '/w/a.md', diff: '--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y', diff_note: null }, 1),
    fromAgentEvent({ type: 'message', turn: 2, text: 'done' }, 2),
  ]

  it('puts the system prompt first and each turn message before that turn', () => {
    const out = withPrompts(items, { system: 'sys', mission: null, turns: { '1': 'turn one', '2': 'turn two' }, turns_recorded: true })
    expect(out.map((i) => i.title)).toEqual(['System prompt', 'Prompt to agent', 'Reasoning', 'File change', 'Prompt to agent', 'Agent message'])
    expect(out[1].body).toBe('turn one')
    expect(out[4].turn).toBe(2)
  })

  it('leaves the timeline as is without prompts', () => {
    expect(withPrompts(items, null)).toBe(items)
  })

  it('classifies diff lines for colouring', () => {
    expect(items[1].diff).toBeTruthy()
    expect(diffLines(items[1].diff!).map((l) => l.kind)).toEqual(['head', 'head', 'hunk', 'del', 'add'])
  })

  it('renders saved files readably', () => {
    expect(readableFile('a.md', '# x').kind).toBe('markdown')
    expect(readableFile('a.json', '{"a":1}').text).toBe('{\n  "a": 1\n}')
    const jsonl = readableFile('t.jsonl', '{"a":1}\n{"b":2}\n')
    expect(jsonl.text).toContain('#2\n{\n  "b": 2\n}')
    expect(jsonl.note).toBe('2 records.')
  })
})
