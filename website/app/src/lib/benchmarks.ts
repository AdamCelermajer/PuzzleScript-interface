import type { BenchmarkGame } from '../api/types'

export interface BenchmarkFilters {
  tier: string
  /** Every listed tag is required (same semantics as GET /benchmarks?tag=). */
  tags: string[]
  collection: string
  /** 'playable' | 'excluded' | 'any' */
  status: string
  /** tags_status: 'draft' (review queue) | 'reviewed' | 'none' | '' */
  review: string
  q: string
}

export function benchmarkMatches(game: BenchmarkGame, f: BenchmarkFilters): boolean {
  if (f.tier && (game.tier ?? 'none') !== f.tier) return false
  const tags = new Set([...game.tags.mechanics, ...game.tags.properties])
  if (f.tags.some((t) => !tags.has(t))) return false
  if (f.collection && !game.collections.includes(f.collection)) return false
  if (f.status && f.status !== 'any' && game.status !== f.status) return false
  if (f.review && game.tags_status !== f.review) return false
  const needle = f.q.trim().toLowerCase()
  if (needle && !`${game.game_id} ${game.title} ${game.author ?? ''} ${game.summary} ${game.notes} ${[...tags].join(' ')}`.toLowerCase().includes(needle)) return false
  return true
}

export function solveRateText(game: Pick<BenchmarkGame, 'measured'>): string {
  const m = game.measured
  return m.runs ? `${m.solved_runs}/${m.runs} runs solved` : 'no runs'
}
