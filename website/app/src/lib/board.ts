// Research board helpers (workbench/board.py shapes).

export type BoardStatus = 'todo' | 'in-progress' | 'done' | 'blocked'

export interface BoardLink {
  label: string
  path_or_url: string
}

export interface BoardCard {
  slug: string
  title: string
  status: BoardStatus
  order: number
  due: string | null
  threads: string[]
  links: BoardLink[]
  runs: string[]
  artifact: string | null
  artifact_exists: boolean
  sections: { question: string; current_answer: string; evidence: string; next: string }
  body: string
}

export const BOARD_STATUSES: BoardStatus[] = ['todo', 'in-progress', 'blocked', 'done']
export const STATUS_LABEL: Record<BoardStatus, string> = { todo: 'To do', 'in-progress': 'In progress', blocked: 'Blocked', done: 'Done' }
export const MEETING_DATE = '2026-10-22'

/** Whole days from `today` until `date` (YYYY-MM-DD), local calendar days. */
export function daysUntil(date: string, today = new Date()): number {
  const [y, m, d] = date.split('-').map(Number)
  const target = new Date(y, m - 1, d).getTime()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  return Math.round((target - start) / 86_400_000)
}

export function countdownText(date: string, today = new Date()): string {
  const days = daysUntil(date, today)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} ago`
  return `in ${days} days`
}

/** Top-level markdown bullets of a section ("- x"), continuation lines joined; plain text kept as one item. */
export function bullets(section: string): string[] {
  const items: string[] = []
  for (const line of section.split('\n')) {
    const match = /^\s{0,1}[-*]\s+(.*)$/.exec(line)
    if (match) items.push(match[1].trim())
    else if (line.trim() && items.length && /^\s{2,}/.test(line)) items[items.length - 1] += ` ${line.trim()}`
    else if (line.trim()) items.push(line.trim())
  }
  return items.filter((item) => item && item !== '-')
}

/** First sentence-ish line of a section for card previews. */
export function oneLine(section: string, limit = 160): string {
  const text = bullets(section).join(' · ').replace(/\s+/g, ' ').trim()
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}

const quote = (value: string) => (/[:#[\]{}"',&*!|>%@`]/.test(value) || value.trim() !== value ? `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"` : value)

/** Full card file for the raw editor; PUT /board/{slug} accepts it as {text}. */
export function cardText(card: Pick<BoardCard, 'title' | 'status' | 'order' | 'due' | 'threads' | 'links' | 'runs' | 'artifact' | 'body'>): string {
  const lines = ['---', `title: ${quote(card.title)}`, `status: ${card.status}`, `order: ${card.order}`]
  if (card.due) lines.push(`due: ${card.due}`)
  lines.push(`threads: [${card.threads.join(', ')}]`)
  if (card.links.length) {
    lines.push('links:')
    for (const link of card.links) lines.push(`  - ${quote(`${link.label} | ${link.path_or_url}`)}`)
  } else lines.push('links: []')
  lines.push(`runs: [${card.runs.join(', ')}]`)
  if (card.artifact) lines.push(`artifact: ${card.artifact}`)
  lines.push('---', card.body.trim(), '')
  return lines.join('\n')
}

export function newCardText(title: string, order: number): string {
  return cardText({
    title, status: 'todo', order, due: null, threads: [], links: [], runs: [], artifact: null,
    body: '## Question\n\n\n## Current answer\nNot started.\n\n## Evidence\n- \n\n## Next\n- ',
  })
}

export function slugify(title: string): string {
  return title.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'card'
}

export const isUrl = (value: string) => /^https?:\/\//.test(value)
export const fileUrl = (path: string) => `/api/workbench/board/file?path=${encodeURIComponent(path)}`

// ---- artifacts (written by other agents; tolerate partial or missing fields)

export type Rating = 'strong' | 'partial' | 'weak' | 'no evidence'

export function normalizeRating(value: unknown): Rating {
  const text = String(value ?? '').toLowerCase().replace(/[_-]+/g, ' ').trim()
  if (text.startsWith('strong')) return 'strong'
  if (text.startsWith('partial') || text.startsWith('mixed') || text.startsWith('moderate')) return 'partial'
  if (text.startsWith('weak') || text.startsWith('poor') || text.startsWith('absent')) return 'weak'
  return 'no evidence'
}

export interface ScorecardCell {
  rating: Rating
  evidence: string[]
  sources: string[]
}

export interface Scorecard {
  capabilities: string[]
  models: string[]
  cell: (model: string, capability: string) => ScorecardCell
  interventions: unknown[]
}

const asStrings = (value: unknown): string[] => (Array.isArray(value) ? value.map((v) => (typeof v === 'string' ? v : label(v))) : typeof value === 'string' ? [value] : [])

/** Human label for an item that may be a string or an object with a name/title/label. */
export function label(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value !== 'object') return String(value)
  const record = value as Record<string, unknown>
  for (const key of ['name', 'title', 'label', 'id', 'capability', 'model']) if (typeof record[key] === 'string') return record[key] as string
  return JSON.stringify(value)
}

export function parseScorecard(data: unknown): Scorecard | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  if (!Array.isArray(record.capabilities) || !Array.isArray(record.models)) return null
  const cells = (record.cells && typeof record.cells === 'object' ? record.cells : {}) as Record<string, Record<string, unknown>>
  return {
    capabilities: record.capabilities.map(label),
    models: record.models.map(label),
    interventions: Array.isArray(record.interventions) ? record.interventions : [],
    cell: (model, capability) => {
      const raw = cells[`${model}|${capability}`] ?? cells[`${capability}|${model}`] ?? {}
      return { rating: normalizeRating(raw.rating), evidence: asStrings(raw.evidence), sources: asStrings(raw.sources) }
    },
  }
}

export const isRealtime = (data: unknown): data is Record<string, unknown> =>
  Boolean(data && typeof data === 'object' && ('environments' in (data as object) || 'framework' in (data as object) || 'prior_work' in (data as object)))
