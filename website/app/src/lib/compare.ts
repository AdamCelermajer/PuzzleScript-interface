import type { EvaluationInput } from '../api/types'

/** Best fresh fitness so far after each completed evaluation (x = evaluation number, from 1). */
export function bestSoFar(evaluations: Pick<EvaluationInput, 'fitness'>[]): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = []
  let best = -Infinity
  evaluations.forEach((e, i) => {
    if (typeof e.fitness !== 'number' || !Number.isFinite(e.fitness)) return
    best = Math.max(best, e.fitness)
    points.push({ x: i + 1, y: best })
  })
  return points
}

/**
 * Levels completed against actions from a direct-player `transitions.jsonl`.
 * Only change points are kept (plus the start and the final action) so long runs stay light.
 */
export function levelCurve(jsonl: string): { points: { x: number; y: number }[]; total: number | null } {
  const points: { x: number; y: number }[] = [{ x: 0, y: 0 }]
  let total: number | null = null
  let last = 0
  let lastX = 0
  for (const line of jsonl.split('\n')) {
    if (!line.trim()) continue
    let row: { action_index?: number; after?: { levels_completed?: number; win_levels?: number } }
    try {
      row = JSON.parse(line)
    } catch {
      continue
    }
    const x = row.action_index
    const y = row.after?.levels_completed
    if (typeof row.after?.win_levels === 'number') total = row.after.win_levels
    if (typeof x !== 'number' || typeof y !== 'number') continue
    lastX = x
    if (y !== last) {
      points.push({ x, y })
      last = y
    }
  }
  if (lastX > (points.at(-1)?.x ?? 0)) points.push({ x: lastX, y: last })
  return { points, total }
}

/** First evaluation number that solved, or null. */
export function firstSuccess(evaluations: Pick<EvaluationInput, 'success'>[]): number | null {
  const index = evaluations.findIndex((e) => e.success === true)
  return index < 0 ? null : index + 1
}
