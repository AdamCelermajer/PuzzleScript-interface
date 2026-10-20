import { describe, expect, it } from 'vitest'
import { pinKey, pinText, type TimelineItem } from './events'

const item = (over: Partial<TimelineItem>): TimelineItem => ({ id: 'ev-3', kind: 'reasoning', title: 'Reasoning', summary: 'Level 1 is cleared!', turn: 58, at: '2026-10-20T08:25:37Z', ...over })

describe('pins', () => {
  it('keys an event by context, turn, kind, time and text, not by its list position', () => {
    expect(pinKey(item({ id: 'ev-3' }))).toBe(pinKey(item({ id: 'ev-499' })))
    expect(pinKey(item({}), 'x_0001 player')).not.toBe(pinKey(item({}), 'optimizer'))
  })
  it('keeps the full text: tool input and output, else the body, else the summary', () => {
    expect(pinText(item({ input: 'ls', body: 'a.txt' }))).toBe('ls\n\na.txt')
    expect(pinText(item({ body: 'long reasoning' }))).toBe('long reasoning')
    expect(pinText(item({}))).toBe('Level 1 is cleared!')
  })
})
