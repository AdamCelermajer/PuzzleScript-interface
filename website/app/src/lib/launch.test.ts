import { describe, expect, it } from 'vitest'
import type { Framework, Harness, PreviewRun } from '../api/types'
import {
  DEFAULT_FORM, budgetText, buildRunRequest, estimateRuns, formProblems, frameworkChoices, groupPreview, modelFitsHarness,
  modelProvider, withFrameworks, type LaunchForm,
} from './launch'

const harnesses: Harness[] = [
  { id: 'codex', label: 'Codex CLI', providers: ['openai'], models: [{ id: 'gpt-5.6-sol', label: 'gpt-5.6-sol', provider: 'openai' }], efforts: ['low'], ready: true, missing: [] },
  { id: 'opencode', label: 'OpenCode', providers: ['openrouter', 'nanogpt'], models: [], efforts: ['low'], ready: true, missing: [] },
]
const option = (name: string, kind: 'int' | 'str' | 'bool', value: number | string | boolean, choices: string[] = []) =>
  ({ name, flag: `--${name}`, kind, default: value, help: '', choices, minimum: null, maximum: null })
// Mirrors frameworks/registry.py list_frameworks().
const frameworks: Framework[] = [
  { id: 'baseline', label: 'Baseline', description: '', optimizer: false, artifact: '', restart: 'continue',
    options: [option('max_steps', 'int', 200), option('notes', 'bool', false)] },
  { id: 'avo', label: 'AVO', description: '', optimizer: true, artifact: 'campaign', restart: 'resume',
    options: [option('max_evaluations', 'int', 8), option('world_model_mode', 'str', 'final-only', ['final-only', 'between-hypotheses'])] },
]
const form = (over: Partial<LaunchForm> = {}, on: Record<string, Record<string, unknown>> = { baseline: {} }): LaunchForm => {
  const base = withFrameworks({ ...DEFAULT_FORM, frameworks: { baseline: { on: false, values: {} } } }, frameworks)
  for (const [id, values] of Object.entries(on)) base.frameworks[id] = { on: true, values: { ...base.frameworks[id].values, ...values } as never }
  return { ...base, harnesses: ['codex'], models: ['gpt-5.6-sol'], games: ['ps_modality-v1'], ...over }
}

describe('framework choices', () => {
  it('turns on the first framework in a fresh form and fills option defaults', () => {
    const fresh = withFrameworks(DEFAULT_FORM, frameworks)
    expect(fresh.frameworks.baseline).toEqual({ on: true, values: { max_steps: 200, notes: [false] } })
    expect(fresh.frameworks.avo.on).toBe(false)
  })

  it('expands multi-valued options into matched entries', () => {
    const choices = frameworkChoices(form({}, { baseline: { notes: [false, true] }, avo: { world_model_mode: ['final-only', 'between-hypotheses'] } }), frameworks)
    expect(choices).toEqual([
      { id: 'baseline', options: { max_steps: 200, notes: false } },
      { id: 'baseline', options: { max_steps: 200, notes: true } },
      { id: 'avo', options: { max_evaluations: 8, world_model_mode: 'final-only' } },
      { id: 'avo', options: { max_evaluations: 8, world_model_mode: 'between-hypotheses' } },
    ])
  })
})

describe('buildRunRequest', () => {
  it('omits optimizer fields when no selected framework has an optimizer (API returns 400 otherwise)', () => {
    const request = buildRunRequest(form({ optimizerModel: 'gpt-6-astra' }), frameworks)
    expect(request.optimizer_model).toBeUndefined()
    expect(request.frameworks).toEqual([{ id: 'baseline', options: { max_steps: 200, notes: false } }])
    expect(buildRunRequest(form({ optimizerModel: 'gpt-6-astra' }, { avo: {} }), frameworks).optimizer_model).toBe('gpt-6-astra')
  })

  it('sends 0 for unlimited wall time and seconds otherwise', () => {
    expect(buildRunRequest(form({ unlimitedWall: true }), frameworks).max_wall_seconds).toBe(0)
    expect(buildRunRequest(form({ unlimitedWall: false, wallHours: 1.5 }), frameworks).max_wall_seconds).toBe(5400)
  })

  it('only pins a provider for OpenRouter models on opencode/bare', () => {
    expect(buildRunRequest(form({ provider: 'deepinfra' }), frameworks).provider).toBeUndefined()
    const pinned = buildRunRequest(form({ harnesses: ['opencode'], models: ['openrouter/qwen/qwen3.8-27b'], provider: ' deepinfra ' }), frameworks)
    expect(pinned.provider).toBe('deepinfra')
  })
})

describe('matrix preview helpers', () => {
  it('estimates games × framework choices × fitting pairs × efforts × repeats', () => {
    const f = form({ harnesses: ['codex', 'opencode'], models: ['gpt-5.6-sol', 'openrouter/qwen/qwen3.8-27b'], efforts: ['low', 'high'], repeats: 2, games: ['a', 'b'] },
      { baseline: {}, avo: { world_model_mode: ['final-only', 'between-hypotheses'] } })
    // 2 games × (1 + 2) × 2 fitting pairs × 2 efforts × 2 repeats
    expect(estimateRuns(f, harnesses, frameworks)).toBe(48)
  })

  it('mirrors the API model/provider membership check', () => {
    expect(modelProvider('claude-sonnet-5-5')).toBe('anthropic')
    expect(modelProvider('gemini-3.8-flash-high')).toBe('google')
    expect(modelProvider('nanogpt/qwen/x')).toBe('nanogpt')
    expect(modelFitsHarness(harnesses[0], 'openrouter/qwen/qwen3.8-27b')).toBe(false)
    expect(modelFitsHarness(harnesses[1], 'nanogpt/qwen/qwen3.8-27b')).toBe(true)
  })

  it('reports missing selections before calling the API', () => {
    expect(formProblems(withFrameworks(DEFAULT_FORM, frameworks), frameworks)).toEqual(['Choose at least one harness', 'Choose at least one model', 'Choose at least one game'])
    expect(formProblems(form({}, { avo: { world_model_mode: [] } }), frameworks)).toContain('Choose at least one AVO world model mode')
    expect(formProblems({ ...form(), frameworks: {} }, frameworks)).toContain('Choose at least one framework')
  })

  it('groups preview rows by game and describes options', () => {
    const row = (game: string, framework: string): PreviewRun => ({
      framework, variant: framework, harness: 'codex', model: 'm', optimizer_model: null, effort: 'low', optimizer_effort: null, game_id: game,
      repeat: 1, match_id: 'match-0001', backend_url: '', command: [],
      options: framework === 'avo' ? { max_evaluations: 8, world_model_mode: 'final-only' } : { max_steps: 200, notes: true },
      max_wall_seconds: framework === 'avo' ? 7200 : 0,
    })
    const groups = groupPreview([row('a', 'baseline'), row('b', 'avo'), row('a', 'avo')])
    expect(groups.map(([g, rows]) => [g, rows.length])).toEqual([['a', 2], ['b', 1]])
    expect(budgetText(row('a', 'baseline'))).toBe('max steps 200 · notes · unlimited wall')
    expect(budgetText(row('a', 'avo'))).toBe('max evaluations 8 · world model mode final-only · 2h wall')
  })
})
