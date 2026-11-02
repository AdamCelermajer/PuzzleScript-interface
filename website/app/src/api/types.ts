// Shapes returned by workbench/*.py (read from the Python source, revamp contract §4).

export type HarnessId = 'codex' | 'claude-code' | 'opencode' | 'antigravity' | 'bare'
export type Effort = 'low' | 'medium' | 'high' | 'xhigh' | 'max'
/** Framework option values, keyed by option name (frameworks/base.py Option). */
export type FrameworkOptions = Record<string, number | string | boolean>

/** One framework from `GET /frameworks` (frameworks/registry.py list_frameworks). */
export interface FrameworkOption {
  name: string
  flag: string
  kind: 'int' | 'str' | 'bool'
  default: number | string | boolean
  help: string
  choices: string[]
  minimum: number | null
  maximum: number | null
}

export interface Framework {
  id: string
  label: string
  description: string
  options: FrameworkOption[]
  optimizer: boolean
  artifact: string
  restart: 'resume' | 'continue'
}

export interface EvaluationInput {
  candidate_id: string | null
  fitness: number
  success: boolean | null
  environment_steps: number | null
  finish_reason: string | null
  score: {
    win_levels: number | null
    environment_task: { score: { win_levels: number | null } }
    research_score: { win_levels: number | null }
    research_environment_actions: number | null
    search_session_elapsed_seconds: number | null
  }
}

/** One row of `GET /catalog` → runs (workbench/catalog.py snapshot). Queued children lack most fields. */
export interface CatalogRun {
  id: string
  kind: 'avo' | 'codex'
  batch?: string
  framework?: string | null
  /** Display name for the framework and its options, e.g. `Baseline+`. */
  variant?: string | null
  options?: FrameworkOptions | null
  max_wall_seconds?: number | null
  harness?: string | null
  agent_backend?: string
  model?: string | null
  model_provider?: string
  optimizer_model?: string | null
  effort?: string | null
  optimizer_effort?: string | null
  provider?: string | null
  spec_source?: 'run_spec' | 'legacy' | null
  continued_from?: string | null
  resumable?: boolean
  /** Moved to the archive by the user (output/workbench/archived.json). */
  archived?: boolean
  /** Harness²: finished and planned rollouts, and the one playing now. */
  rollouts?: { done: number; total: number | null; current: string | null; current_actions: number | null } | null
  log_href?: string | null
  /** The run's folder in its batch (`run-0001`), the key of `POST /experiments/stop-run`. */
  job_run?: string | null
  /** An active run of a live batch that can be stopped on its own. */
  can_stop?: boolean
  game_id?: string | null
  condition?: string | null
  world_model_mode?: string | null
  status: string
  status_source?: string
  container?: string | null
  needs_assistance?: boolean
  failure_reason?: string | null
  can_resume?: boolean
  can_continue?: boolean
  resumed_as?: string | null
  resumed_from?: string | null
  solved?: boolean
  has_result?: boolean
  best_fitness?: number | null
  levels?: number | null
  actions?: number | null
  evaluated?: number
  budget?: number | null
  candidate?: string | null
  modified?: number
  started_at?: number
  repeat?: number
  pair_id?: string | null
  match_id?: string | null
  recorded_win_levels?: number | null
  /** Direct play: the level the game opened at, the level of a one-level task, and that level's score. */
  start_level?: number | null
  level?: number | null
  level_score?: { solved: boolean | null; moves: number | null; shortest: number | null; ratio: number | null } | null
  config?: Record<string, unknown>
  result_inputs?: { config: Record<string, unknown>; evaluations: EvaluationInput[]; finalized: boolean }
}

export interface CatalogJob {
  id: string
  kind: string | null
  status: string
  status_source?: string
  comparison: boolean
  created_at: string | null
  parallel: number | null
  error: string | null
  runs: Partial<CatalogRun>[]
  can_pause: boolean
  can_stop: boolean
  can_resume: boolean
  can_dismiss: boolean
  dismissed_from_runs_at: string | null
  recovery_of: string | null
  resumed_as: string | null
  needs_assistance?: boolean
}

export interface Catalog {
  runs: CatalogRun[]
  jobs: CatalogJob[]
  warnings: string[]
  checked_at: number
}

export interface HarnessModel {
  id: string
  label: string
  provider: string
  free?: boolean
  context?: number | null
  input_price?: number | null
  output_price?: number | null
}

export interface Harness {
  id: HarnessId
  label: string
  providers: string[]
  models: HarnessModel[]
  efforts: Effort[]
  ready: boolean
  missing: string[]
  ready_providers?: string[]
  manual_model_ids?: boolean
  provider_pin?: boolean
  model_catalogs?: { provider: string; available: boolean; stale?: boolean; warning?: string | null }[]
}

export interface RunRequest {
  frameworks: { id: string; options: FrameworkOptions }[]
  harnesses: HarnessId[]
  models: string[]
  optimizer_model?: string
  optimizer_effort?: Effort
  efforts: Effort[]
  games: string[]
  repeats: number
  parallel: number
  max_wall_seconds: number
  provider?: string
  label?: string
}

export interface PreviewRun {
  framework: string
  options: FrameworkOptions
  variant: string
  harness: HarnessId
  model: string
  optimizer_model: string | null
  effort: Effort
  optimizer_effort: Effort | null
  game_id: string
  repeat: number
  match_id: string
  backend_url: string
  max_wall_seconds: number
  command: string[]
}

export interface Preview {
  runs: PreviewRun[]
  warnings: string[]
  count: number
  parallel: number
}

export interface LaunchResult {
  job_id: string
  id: string
  count: number
  warnings: string[]
}

export interface ResumeResult {
  job_id: string
  run_id: string
  runs: string[]
  count: number
  skipped: string[]
}

// ---- direct-player record (/record)

export interface AgentEvent {
  schema?: string
  t?: string | null
  session?: string | null
  role?: string | null
  turn?: number | null
  type: string
  text?: string | null
  output?: string | null
  exit_code?: number | null
  tool?: string | null
  usage?: { input?: number; output?: number; reasoning?: number; cached?: number } | null
  harness?: string | null
  model?: string | null
  /** File edits: a unified diff derived from the harness's raw turn record, and why it is partial. */
  diff?: string | null
  diff_note?: string | null
}

/** What our program sent a session: its system prompt, a mission file, each turn's message when recorded. */
export interface SessionPrompts {
  system: string | null
  mission: string | null
  turns: Record<string, string>
  turns_recorded: boolean
}

export interface GridFrame {
  grid?: number[][]
  state?: string
  levels_completed?: number
  win_levels?: number
}

export interface Transition {
  id?: string
  timestamp?: string
  decision?: number
  action_index?: number
  action?: string
  before?: GridFrame
  after?: GridFrame
  changed?: boolean
  changed_cells?: { row: number; col: number; before: number; after: number }[]
  note?: string
}

/** notes/ after one harness turn (notes_history/turn-NNNN/); action_index is the move that turn played. */
export interface NotesHistoryTurn {
  turn: number
  kind: string | null
  timestamp: string | null
  action_index: number | null
  files: string[]
}

/** One turn's notes, and a unified diff of each file changed since the previous saved turn. */
export interface NotesTurn {
  turn: number
  previous: number | null
  files: Record<string, string>
  diffs: Record<string, string>
}

export interface RunRecord {
  id: string
  /** calls/ holds every model request and response (harnesses/recorder.py). */
  has_calls?: boolean
  config: Record<string, unknown>
  run_spec: Record<string, unknown> | null
  normalized: {
    framework: string | null
    variant: string | null
    options: FrameworkOptions
    harness: string | null
    model: string | null
    effort: string | null
    game_id: string | null
    backend_url: string | null
    max_wall_seconds: number | null
    provider: string | null
    continued_from: string | null
    created_at: string | null
    spec_source: string
  }
  result: Record<string, unknown>
  error: Record<string, unknown>
  latest_transition: Transition
  agent_events: { total: number; invalid_lines: number; truncated: boolean; events: AgentEvent[] } | null
  prompts?: SessionPrompts | null
  files: string[]
  /** Harness²: one direct-player run per rollout, in start order. */
  rollouts?: { label: string; result: Record<string, unknown> | null; latest_transition: Transition }[]
  adoption?: { adopted_label?: string; base_levels?: (number | null)[]; best_of_pool_levels?: number } | null
  /** Harness²: the coach's sessions (INV, DOM, compose…) and the harness files each stage wrote. */
  coach_sessions?: CoachSession[]
  harness_edits?: Record<string, Record<string, string>>
  /** Per stage, a unified diff of each harness file that differs from the starting harness. */
  harness_diffs?: Record<string, Record<string, string>>
  /** Harness² per level: each level's rounds at a growing budget, and the harness it kept. */
  levels?: Harness2Level[]
}

export interface Harness2Rollout {
  label: string
  /** "R2/inv1": the same harness was already played at this budget; its result is shown. */
  reused?: string | null
  result: Record<string, unknown> | null
  latest_transition: Transition
}

export interface Harness2Round {
  round: string
  budget: number | null
  kept?: string
  solved?: boolean
  action_count?: number
  fell_back?: string[]
  rollouts: Harness2Rollout[]
  coach_sessions: CoachSession[]
  harness_edits: Record<string, Record<string, string>>
  harness_diffs: Record<string, Record<string, string>>
}

export interface Harness2Level {
  level: number
  status?: 'completed' | 'error'
  solved?: boolean
  kept?: string | null
  budget?: number | null
  action_count?: number | null
  error?: string
  rounds: Harness2Round[]
  /** The harness this level kept; the next level starts from it. */
  kept_files: Record<string, string>
}

// ---- AVO console (/avo/*)

export interface AvoSide {
  actions: number
  levels: number
  last_activity: string | null
  revision: number
  fallback_frame: unknown
}

export interface AvoCandidate {
  candidate_id: string
  parent_ids: string[]
  evaluated: boolean
  fitness: number | null
  /** Research score only: the action that first reached the candidate's levels (fewer wins a tie). */
  actions_to_best?: number | null
  /** AVO3: the research moves this attempt had (budget schedule). */
  research_budget?: number | null
  success: boolean | null
  win_levels: number | null
  research: AvoSide
  evaluation: AvoSide
}

export interface AvoSnapshot {
  run_id: string
  game_id: string
  harness: string | null
  variant: string | null
  /** What scores a candidate: its solver's fresh run, or its own research session (no solver). */
  score: 'solver' | 'research'
  player_model: string
  optimizer_model: string
  current: string | null
  phase: string
  active: boolean
  process_status: string
  can_resume: boolean
  resumed_as: string | null
  finalized: boolean
  world_model_available: boolean
  hypotheses_registered: number
  hypotheses_evaluated: number
  max_hypotheses: number | null
  win_levels: number | null
  research: { actions: number; levels: number; events: number; budget: number | null }
  fresh_evaluation: { actions: number; levels: number; events: number; budget: number | null }
  /** AVO3: research moves per attempt, in order (empty without a schedule). */
  research_schedule?: number[]
  /** AVO3: the solver written after the last attempt, played once for information (not the score). */
  final_solver?: { status?: string; source_candidate?: string; solver_present?: boolean; levels_completed?: number | null;
    win_levels?: number | null; environment_steps?: number; max_steps?: number; error?: string } | null
  latest_fitness: number | null
  latest_success: boolean | null
  last_activity: string | null
  candidates: AvoCandidate[]
  frame_sessions: { candidate_id: string; phase: 'research' | 'evaluation'; actions: number; levels: number; revision: number }[]
  recent_activity: { type: string; recorded_at: string; action: string | null; title: string; detail: string }[]
}

export interface AvoFrame {
  candidate_id: string
  phase: string
  step: number
  total_actions: number
  reasoning?: { status: string; text?: string }
  replay_exact: boolean
  source: string
  rendered_frame: { data_url: string; width?: number; height?: number } | null
  fallback_frame: unknown
  transition: { action?: { id?: string } | null; status?: string; progress?: { levels_completed?: number; win_levels?: number } }
}

export interface AvoLogEntry {
  id: string
  actor: string
  turn: number | null
  recorded_at: string | null
  role?: string
  category: string
  kind: string
  title: string
  summary: string
  meta?: string
  input?: string
  body?: string
}

export interface AvoLogs {
  actor: string
  stream: string
  page: number
  total: number
  has_more: boolean
  entries: AvoLogEntry[]
}

export interface AvoArtifact {
  path: string
  name: string
  role: string
  size: number
  modified: string
}

export interface Submission {
  id: string
  selection: 'best' | 'candidate'
  game_id: string | null
  model: string | null
  optimizer_model: string | null
  mode: string
  finalized: boolean
  best: (EvaluationInput & { evaluation_id?: string }) | null
  evaluations: EvaluationInput[]
  files: { name: string; path: string; size: number }[]
  evaluations_to_success: number | null
  seconds_to_success: number | null
  solver_present: boolean
  world_model: string | null
  world_model_record: { provenance?: string } & Record<string, unknown>
}

// ---- comparisons (/comparison?job=)

export interface ComparisonRun {
  id: string
  status: string
  finalized: boolean
  best_fitness: number | null
  solved: boolean
  evaluated: number
  first_success_evaluation: number | null
  seconds_to_success: number | null
  search_seconds: number | null
  history: { candidate: string; fitness: number }[]
}

export interface JobComparison {
  id: string
  created_at: string | null
  pairs: { id: string; game_id: string; model: string; effort: string | null; repeat: number; runs: Record<string, ComparisonRun> }[]
}

// ---- benchmarks

export interface Measured {
  runs: number
  solved_runs: number
  best_levels: number | null
  by_harness: Record<string, { runs: number; solved_runs: number; best_levels: number | null }>
}

export interface BenchmarkGame {
  game_id: string
  title: string
  author?: string
  homepage?: string
  status: 'playable' | 'excluded'
  exclusion_reasons: string[]
  arc_catalog?: boolean
  collections: string[]
  tier: 'easy' | 'medium' | 'hard' | null
  tier_source: string | null
  levels: number | null
  structure?: { objects: number; rule_groups: number; max_area: number }
  bfs: { solved: boolean; depth: number | null } | null
  tags: { mechanics: string[]; properties: string[] }
  tags_status: 'draft' | 'reviewed' | 'none'
  tags_model?: string
  summary: string
  notes: string
  measured: Measured
}

export interface BenchmarkList {
  tag_vocabulary: { mechanics: string[]; properties: string[] }
  tag_definitions: Record<string, string>
  count: number
  games: BenchmarkGame[]
  measured_at: number
  warnings: string[]
}

export interface BenchmarkDetail extends BenchmarkGame {
  tag_definitions: Record<string, string>
  readme: string | null
  runs: Partial<CatalogRun>[]
  bfs_searches: { source: string; level: number; status: string; solved: boolean; depth: number | null; expanded_states: number | null }[]
  reference: { artifact_status?: string; levels: { level: number; solution_actions: unknown; replay_verified: boolean }[] } | null
  reviewed_rules: string[]
  rules_source: string
  level_annotations: { methodology?: string; levels?: Record<string, unknown>[] }
  rule_archives: { id: string; model: string | null }[]
  goal_studies: { id: string; source: string; answers: number }[]
}

export interface PlayFrame {
  session: string
  game_id: string
  level: number | null
  state: string
  levels_completed: number
  win_levels: number
  available_actions: (string | number)[]
  frame: unknown
  rendered_frame?: { data_url?: string; width?: number; height?: number } | null
}

// ---- diary

export interface DiaryRunLink {
  id: string
  linked: 'explicit' | 'date'
  found: boolean
  date?: string | null
  variant?: string
  harness?: string | null
  model?: string | null
  game?: string | null
  status?: string
  solved?: boolean
  outcome?: string
  // Summed over the run's sessions; input includes cached, output includes reasoning, total = input + output.
  tokens?: { input: number; output: number; reasoning: number; cached: number; total: number } | null
}

export interface DiaryEntry {
  slug: string
  date: string
  title: string
  threads: string[]
  reconstructed: boolean
  /** Minor entry: present mode folds it into the month's "also done" slide. */
  brief: boolean
  commits: string[]
  docs: string[]
  sections: { did: string; found: string; decided: string; next: string }
  warnings: string[]
  explicit_runs: string[]
  runs: DiaryRunLink[]
  body?: string
}

export interface DiaryThread {
  id: string
  description: string
  status: string
  entries: number
  first: string | null
  last: string | null
}

// ---- Pins (/pins): moments of a run the user kept, with the event text copied.

export interface Pin {
  id: string
  run: string
  /** Stable identity of the pinned event inside its run, so a second click finds the same pin. */
  key: string
  /** Where in the run, e.g. an AVO candidate scope. */
  context: string
  turn: number | null
  kind: string
  title: string
  text: string
  at: string | null
  note: string
  created_at: string
}

export interface CoachSession {
  id: string
  stage: 'INV' | 'DOM' | 'compose' | 'reflect' | 'select' | null
  model: string | null
  started_at: string | null
  finished: boolean
  file_changes: number
  events: number
  length_cap: boolean
}
