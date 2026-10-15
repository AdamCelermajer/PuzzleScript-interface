import type { Effort, Harness, HarnessId, Mode, PreviewRun, RunRequest, WorldModelMode } from '../api/types'

export interface LaunchForm {
  modes: Mode[]
  harnesses: HarnessId[]
  models: string[]
  efforts: Effort[]
  games: string[]
  /** '' = same as the player model. */
  optimizerModel: string
  /** '' = same as the player effort. */
  optimizerEffort: Effort | ''
  worldModelModes: WorldModelMode[]
  repeats: number
  parallel: number
  unlimitedWall: boolean
  wallHours: number
  maxSteps: number
  maxEvaluations: number
  researchMoves: number
  solverMoves: number
  provider: string
  label: string
}

// Defaults mirror workbench/runs.py Budget.
export const DEFAULT_FORM: LaunchForm = {
  modes: ['baseline-plus'],
  harnesses: [],
  models: [],
  efforts: ['medium'],
  games: [],
  optimizerModel: '',
  optimizerEffort: '',
  worldModelModes: ['final-only'],
  repeats: 1,
  parallel: 1,
  unlimitedWall: true,
  wallHours: 4,
  maxSteps: 200,
  maxEvaluations: 8,
  researchMoves: 400,
  solverMoves: 400,
  provider: '',
  label: '',
}

export const usesCampaign = (f: Pick<LaunchForm, 'modes'>) => f.modes.includes('campaign')
export const usesBaseline = (f: Pick<LaunchForm, 'modes'>) => f.modes.some((m) => m !== 'campaign')

/** Provider pinning only applies to OpenRouter models on opencode/bare (workbench/runs.py validate_request). */
export function providerPinApplies(f: Pick<LaunchForm, 'harnesses' | 'models'>): boolean {
  return f.harnesses.length > 0 && f.harnesses.every((h) => h === 'opencode' || h === 'bare') && f.models.length > 0 && f.models.every((m) => m.startsWith('openrouter/'))
}

/**
 * Build the RunRequest. The API rejects fields that do not apply to the selected modes
 * (e.g. world_model_modes without campaign, budget.max_steps without a baseline mode),
 * so they are omitted rather than sent with defaults.
 */
export function buildRunRequest(f: LaunchForm): RunRequest {
  const campaign = usesCampaign(f)
  const baseline = usesBaseline(f)
  const budget: RunRequest['budget'] = { max_wall_seconds: f.unlimitedWall ? 0 : Math.max(1, Math.round(f.wallHours * 3600)) }
  if (baseline) budget.max_steps = f.maxSteps
  if (campaign) {
    budget.max_evaluations = f.maxEvaluations
    budget.research_moves = f.researchMoves
    budget.solver_moves = f.solverMoves
  }
  const request: RunRequest = {
    modes: [...f.modes],
    harnesses: [...f.harnesses],
    models: [...f.models],
    efforts: [...f.efforts],
    games: [...f.games],
    repeats: f.repeats,
    parallel: f.parallel,
    budget,
  }
  if (campaign) {
    request.world_model_modes = [...f.worldModelModes]
    if (f.optimizerModel) request.optimizer_model = f.optimizerModel
    if (f.optimizerEffort) request.optimizer_effort = f.optimizerEffort
  }
  if (f.provider.trim() && providerPinApplies(f)) request.provider = f.provider.trim()
  if (f.label.trim()) request.label = f.label.trim()
  return request
}

/** Problems the user can fix before asking the API for a preview. */
export function formProblems(f: LaunchForm): string[] {
  const problems: string[] = []
  if (!f.modes.length) problems.push('Choose at least one mode')
  if (!f.harnesses.length) problems.push('Choose at least one harness')
  if (!f.models.length) problems.push('Choose at least one model')
  if (!f.efforts.length) problems.push('Choose at least one effort')
  if (!f.games.length) problems.push('Choose at least one game')
  if (usesCampaign(f) && !f.worldModelModes.length) problems.push('Choose a world-model condition for AVO runs')
  if (!f.unlimitedWall && !(f.wallHours > 0)) problems.push('Wall time must be positive, or switch on unlimited')
  return problems
}

/**
 * Upper bound of the matrix size before the API drops incompatible harness × model pairs:
 * games × modes(campaign expands by world-model modes) × harness-model pairs × efforts × repeats.
 */
export function estimateRuns(f: LaunchForm, harnesses: Harness[]): number {
  const known = new Map(harnesses.map((h) => [h.id, h]))
  let pairs = 0
  for (const harness of f.harnesses) {
    const entry = known.get(harness)
    for (const model of f.models) if (!entry || modelFitsHarness(entry, model)) pairs += 1
  }
  const modeFactor = f.modes.reduce((sum, m) => sum + (m === 'campaign' ? Math.max(1, f.worldModelModes.length) : 1), 0)
  return f.games.length * modeFactor * pairs * f.efforts.length * f.repeats
}

/** Mirrors workbench/harness_catalog.py model_provider + model_error membership check. */
export function modelProvider(model: string): string {
  if (model.startsWith('openrouter/')) return 'openrouter'
  if (model.startsWith('nanogpt/')) return 'nanogpt'
  if (/^claude-[a-z]+-\d+(?:-\d+)*$/.test(model)) return 'anthropic'
  if (/^(?:gemini|claude|gpt-oss)-[a-z0-9.-]+-(?:low|medium|high)$/.test(model)) return 'google'
  return 'openai'
}

export function modelFitsHarness(harness: Pick<Harness, 'providers' | 'models'>, model: string): boolean {
  if (harness.models.some((m) => m.id === model)) return true
  return harness.providers.includes(modelProvider(model))
}

/** Stable key so the Launch button only enables for the request that was previewed. */
export const requestKey = (request: RunRequest) => JSON.stringify(request)

/** Group preview rows by game for display, keeping API order inside each game. */
export function groupPreview(rows: PreviewRun[]): [string, PreviewRun[]][] {
  const groups = new Map<string, PreviewRun[]>()
  for (const row of rows) groups.set(row.game_id, [...(groups.get(row.game_id) ?? []), row])
  return [...groups]
}

/** Human summary of a preview row's budget. */
export function budgetText(row: Pick<PreviewRun, 'mode' | 'budget'>): string {
  const b = row.budget
  const wall = !b.max_wall_seconds ? 'unlimited wall' : `${(b.max_wall_seconds / 3600).toFixed(b.max_wall_seconds % 3600 ? 1 : 0)}h wall`
  if (row.mode === 'campaign') return `${b.max_evaluations} evals · ${b.research_moves} research / ${b.solver_moves} solver moves · ${wall}`
  return `${b.max_steps} steps · ${wall}`
}
