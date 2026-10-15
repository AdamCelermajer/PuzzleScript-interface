import { describe, expect, it } from 'vitest'
import { bullets, cardText, countdownText, daysUntil, normalizeRating, oneLine, parseScorecard } from './board'

describe('board helpers', () => {
  it('counts calendar days to the meeting', () => {
    const today = new Date(2026, 9, 15, 23, 30)
    expect(daysUntil('2026-10-22', today)).toBe(7)
    expect(countdownText('2026-10-22', today)).toBe('in 7 days')
    expect(countdownText('2026-10-22', new Date(2026, 9, 22, 9))).toBe('today')
    expect(countdownText('2026-10-22', new Date(2026, 9, 21))).toBe('tomorrow')
    expect(countdownText('2026-10-22', new Date(2026, 9, 24))).toBe('2 days ago')
  })

  it('splits sections into bullets and one-line previews', () => {
    expect(bullets('- a\n  continued\n- b\n\nplain')).toEqual(['a continued', 'b', 'plain'])
    expect(bullets('-')).toEqual([])
    expect(oneLine('In progress — scorecard over seven capabilities.', 20)).toBe('In progress — score…')
  })

  it('writes the card file the API parses', () => {
    const text = cardText({
      title: 'Real-time: what has been done?', status: 'in-progress', order: 4, due: null, threads: ['qwen-harness'],
      links: [{ label: 'Notes', path_or_url: 'docs/research/x.md' }], runs: [], artifact: 'docs/research/x.json', body: '## Question\nQ\n',
    })
    expect(text.split('\n').slice(0, 10)).toEqual([
      '---', 'title: "Real-time: what has been done?"', 'status: in-progress', 'order: 4', 'threads: [qwen-harness]',
      'links:', '  - "Notes | docs/research/x.md"', 'runs: []', 'artifact: docs/research/x.json', '---',
    ])
  })

  it('reads the capability scorecard defensively', () => {
    expect(parseScorecard(null)).toBeNull()
    expect(parseScorecard({ models: [] })).toBeNull()
    const card = parseScorecard({
      capabilities: ['Perception', { name: 'Planning' }], models: ['Max', 'Flash'],
      cells: { 'Max|Perception': { rating: 'strong', evidence: ['solved 4/4'], sources: ['audit.md'] }, 'Flash|Planning': { rating: 'Partial' } },
    })!
    expect(card.capabilities).toEqual(['Perception', 'Planning'])
    expect(card.cell('Max', 'Perception')).toEqual({ rating: 'strong', evidence: ['solved 4/4'], sources: ['audit.md'] })
    expect(card.cell('Flash', 'Planning').rating).toBe('partial')
    expect(card.cell('Flash', 'Perception').rating).toBe('no evidence')
    expect(normalizeRating('no_evidence')).toBe('no evidence')
    expect(normalizeRating('weak')).toBe('weak')
  })
})
