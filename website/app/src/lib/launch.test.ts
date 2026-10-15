import { describe, expect, it } from 'vitest'
import type { Harness, PreviewRun } from '../api/types'
import { DEFAULT_FORM, budgetText, buildRunRequest, estimateRuns, formProblems, groupPreview, modelFitsHarness, modelProvider, type LaunchForm } from './launch'

const harnesses: Harness[] = [
  { id: 'codex', label: 'Codex CLI', providers: ['openai'], models: [{ id: 'gpt-5.6-sol', label: 'gpt-5.6-sol', provider: 'openai' }], efforts: ['low'], ready: true, missing: [] },
  { id: 'opencode', label: 'OpenCode', providers: ['openrouter', 'nanogpt'], models: [], efforts: ['low'], ready: true, missing: [] },
]
const form = (over: Partial<LaunchForm>): LaunchForm => ({ ...DEFAULT_FORM, harnesses: ['codex'], models: ['gpt-5.6-sol'], games: ['ps_modality-v1'], ...over })

describe('buildRunRequest', () => {
  it('omits campaign-only fields when no campaign mode is selected (API returns 400 otherwise)', () => {
    const request = buildRunRequest(form({ modes: ['baseline', 'baseline-plus'], optimizerModel: 'gpt-6-astra' }))
    expect(request.world_model_modes).toBeUndefined()
    expect(request.optimizer_model).toBeUndefined()
    expect(request.budget).toEqual({ max_wall_seconds: 0, max_steps: 200 })
  })

  it('omits max_steps for campaign-only requests and includes campaign budgets', () => {
    const request = buildRunRequest(form({ modes: ['campaign'], worldModelModes: ['final-only', 'between-hypotheses'] }))
    expect(request.budget).toEqual({ max_wall_seconds: 0, max_evaluations: 8, research_moves: 400, solver_moves: 400 })
    expect(request.world_model_modes).toEqual(['final-only', 'between-hypotheses'])
  })

  it('sends 0 for unlimited wall time and seconds otherwise', () => {
    expect(buildRunRequest(form({ unlimitedWall: true })).budget.max_wall_seconds).toBe(0)
    expect(buildRunRequest(form({ unlimitedWall: false, wallHours: 1.5 })).budget.max_wall_seconds).toBe(5400)
  })

  it('only pins a provider for OpenRouter models on opencode/bare', () => {
    expect(buildRunRequest(form({ provider: 'deepinfra' })).provider).toBeUndefined()
    const pinned = buildRunRequest(form({ harnesses: ['opencode'], models: ['openrouter/qwen/qwen3.8-27b'], provider: ' deepinfra ' }))
    expect(pinned.provider).toBe('deepinfra')
  })
})

describe('matrix preview helpers', () => {
  it('estimates games × modes(+world-model) × fitting pairs × efforts × repeats', () => {
    const f = form({ modes: ['baseline', 'campaign'], worldModelModes: ['final-only', 'between-hypotheses'], harnesses: ['codex', 'opencode'],
      models: ['gpt-5.6-sol', 'openrouter/qwen/qwen3.8-27b'], efforts: ['low', 'high'], repeats: 2, games: ['a', 'b'] })
    // 2 games × (1 + 2) × 2 fitting pairs × 2 efforts × 2 repeats
    expect(estimateRuns(f, harnesses)).toBe(48)
  })

  it('mirrors the API model/provider membership check', () => {
    expect(modelProvider('claude-sonnet-5-5')).toBe('anthropic')
    expect(modelProvider('gemini-3.8-flash-high')).toBe('google')
    expect(modelProvider('nanogpt/qwen/x')).toBe('nanogpt')
    expect(modelFitsHarness(harnesses[0], 'openrouter/qwen/qwen3.8-27b')).toBe(false)
    expect(modelFitsHarness(harnesses[1], 'nanogpt/qwen/qwen3.8-27b')).toBe(true)
  })

  it('reports missing selections before calling the API', () => {
    expect(formProblems({ ...DEFAULT_FORM })).toEqual(['Choose at least one harness', 'Choose at least one model', 'Choose at least one game'])
    expect(formProblems(form({ modes: ['campaign'], worldModelModes: [] }))).toContain('Choose a world-model condition for campaigns')
  })

  it('groups preview rows by game and describes budgets', () => {
    const row = (game: string, mode: PreviewRun['mode']): PreviewRun => ({
      mode, harness: 'codex', model: 'm', optimizer_model: null, effort: 'low', optimizer_effort: null, game_id: game, world_model_mode: null,
      repeat: 1, match_id: 'match-0001', backend_url: '', command: [],
      budget: mode === 'campaign' ? { max_wall_seconds: 7200, max_evaluations: 8, research_moves: 400, solver_moves: 400 } : { max_wall_seconds: 0, max_steps: 200 },
    })
    const groups = groupPreview([row('a', 'baseline'), row('b', 'campaign'), row('a', 'campaign')])
    expect(groups.map(([g, rows]) => [g, rows.length])).toEqual([['a', 2], ['b', 1]])
    expect(budgetText(row('a', 'baseline'))).toBe('200 steps · unlimited wall')
    expect(budgetText(row('a', 'campaign'))).toBe('8 evals · 400 research / 400 solver moves · 2h wall')
  })
})
