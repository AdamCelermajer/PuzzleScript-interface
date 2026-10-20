import type { Effort, Framework, FrameworkOption, FrameworkOptions, Harness, HarnessId, PreviewRun, RunRequest } from '../api/types'
import { optionsText } from './runs'

/**
 * One framework in the form. Choice and bool options hold a list: picking several values
 * launches one matched run per value (notes off + on = Baseline and Baseline+).
 */
export type OptionField = number | string | (string | boolean)[]
export interface FrameworkForm {
  on: boolean
  values: Record<string, OptionField>
}

export interface LaunchForm {
  /** Keyed by framework id (frameworks/registry.py). */
  frameworks: Record<string, FrameworkForm>
  harnesses: HarnessId[]
  models: string[]
  efforts: Effort[]
  games: string[]
  /** '' = same as the player model. */
  optimizerModel: string
  /** '' = same as the player effort. */
  optimizerEffort: Effort | ''
  repeats: number
  parallel: number
  unlimitedWall: boolean
  wallHours: number
  provider: string
  label: string
}

export const DEFAULT_FORM: LaunchForm = {
  frameworks: {},
  harnesses: [],
  models: [],
  efforts: ['medium'],
  games: [],
  optimizerModel: '',
  optimizerEffort: '',
  repeats: 1,
  parallel: 1,
  unlimitedWall: true,
  wallHours: 4,
  provider: '',
  label: '',
}

export const isMulti = (option: FrameworkOption) => option.kind === 'bool' || option.choices.length > 0

function frameworkForm(framework: Framework, saved: FrameworkForm | undefined): FrameworkForm {
  const values: Record<string, OptionField> = {}
  for (const option of framework.options) {
    const kept = saved?.values[option.name]
    const fits = kept !== undefined && Array.isArray(kept) === isMulti(option)
    values[option.name] = fits ? kept : isMulti(option) ? [option.default as string | boolean] : (option.default as number | string)
  }
  return { on: saved?.on ?? false, values }
}

/** The saved form with every registered framework: new ones off (the first one on in a fresh form), removed ones dropped. */
export function withFrameworks(form: LaunchForm, frameworks: Framework[]): LaunchForm {
  const fresh = !Object.keys(form.frameworks).length
  return {
    ...form,
    frameworks: Object.fromEntries(frameworks.map((framework, index) => {
      const entry = frameworkForm(framework, form.frameworks[framework.id])
      return [framework.id, fresh && index === 0 ? { ...entry, on: true } : entry]
    })),
  }
}

/** Enabled frameworks, one request entry per combination of multi-valued options. */
export function frameworkChoices(form: LaunchForm, frameworks: Framework[]): RunRequest['frameworks'] {
  const choices: RunRequest['frameworks'] = []
  for (const framework of frameworks) {
    const entry = form.frameworks[framework.id]
    if (!entry?.on) continue
    let combos: FrameworkOptions[] = [{}]
    for (const option of framework.options) {
      const value = entry.values[option.name] ?? option.default
      const values = Array.isArray(value) ? value : [value]
      combos = combos.flatMap((combo) => values.map((v) => ({ ...combo, [option.name]: v })))
    }
    choices.push(...combos.map((options) => ({ id: framework.id, options })))
  }
  return choices
}

export const usesOptimizer = (form: LaunchForm, frameworks: Framework[]) =>
  frameworks.some((framework) => framework.optimizer && form.frameworks[framework.id]?.on)

/** Provider pinning only applies to OpenRouter models on opencode/bare (workbench/runs.py validate_request). */
export function providerPinApplies(f: Pick<LaunchForm, 'harnesses' | 'models'>): boolean {
  return f.harnesses.length > 0 && f.harnesses.every((h) => h === 'opencode' || h === 'bare') && f.models.length > 0 && f.models.every((m) => m.startsWith('openrouter/'))
}

/** Build the RunRequest. The API rejects optimizer fields when no selected framework has an optimizer, so they are omitted. */
export function buildRunRequest(f: LaunchForm, frameworks: Framework[]): RunRequest {
  const request: RunRequest = {
    frameworks: frameworkChoices(f, frameworks),
    harnesses: [...f.harnesses],
    models: [...f.models],
    efforts: [...f.efforts],
    games: [...f.games],
    repeats: f.repeats,
    parallel: f.parallel,
    max_wall_seconds: f.unlimitedWall ? 0 : Math.max(1, Math.round(f.wallHours * 3600)),
  }
  if (usesOptimizer(f, frameworks)) {
    if (f.optimizerModel) request.optimizer_model = f.optimizerModel
    if (f.optimizerEffort) request.optimizer_effort = f.optimizerEffort
  }
  if (f.provider.trim() && providerPinApplies(f)) request.provider = f.provider.trim()
  if (f.label.trim()) request.label = f.label.trim()
  return request
}

/** Problems the user can fix before asking the API for a preview. */
export function formProblems(f: LaunchForm, frameworks: Framework[]): string[] {
  const problems: string[] = []
  const on = frameworks.filter((framework) => f.frameworks[framework.id]?.on)
  if (!on.length) problems.push('Choose at least one framework')
  for (const framework of on) {
    for (const option of framework.options) {
      const value = f.frameworks[framework.id].values[option.name]
      if (Array.isArray(value) && !value.length) problems.push(`Choose at least one ${framework.label} ${option.name.replaceAll('_', ' ')}`)
    }
  }
  if (!f.harnesses.length) problems.push('Choose at least one harness')
  if (!f.models.length) problems.push('Choose at least one model')
  if (!f.efforts.length) problems.push('Choose at least one effort')
  if (!f.games.length) problems.push('Choose at least one game')
  if (!f.unlimitedWall && !(f.wallHours > 0)) problems.push('Wall time must be positive, or switch on unlimited')
  return problems
}

/**
 * Upper bound of the matrix size before the API drops incompatible harness × model pairs:
 * games × framework choices × harness-model pairs × efforts × repeats.
 */
export function estimateRuns(f: LaunchForm, harnesses: Harness[], frameworks: Framework[]): number {
  const known = new Map(harnesses.map((h) => [h.id, h]))
  let pairs = 0
  for (const harness of f.harnesses) {
    const entry = known.get(harness)
    for (const model of f.models) if (!entry || modelFitsHarness(entry, model)) pairs += 1
  }
  return f.games.length * frameworkChoices(f, frameworks).length * pairs * f.efforts.length * f.repeats
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

/** Human summary of a preview row's options and wall budget. */
export const budgetText = (row: Pick<PreviewRun, 'options' | 'max_wall_seconds'>) => optionsText(row.options, row.max_wall_seconds)
