import type { AgentEvent, AvoLogEntry, SessionPrompts } from '../api/types'

export type EventKind = 'message' | 'prompt' | 'reasoning' | 'command' | 'file_change' | 'tool' | 'image' | 'usage' | 'error' | 'turn_end' | 'environment' | 'other'

/** One timeline item, whatever log it came from (agent-event-v1, AVO console, legacy transcript). */
export interface TimelineItem {
  id: string
  kind: EventKind
  title: string
  summary: string
  input?: string
  body?: string
  meta?: string
  turn: number | null
  at: string | null
  role?: string | null
  /** File edits: unified diff, and a note when it is partial. */
  diff?: string
  diffNote?: string
}

const KNOWN: EventKind[] = ['message', 'reasoning', 'command', 'file_change', 'tool', 'image', 'usage', 'error', 'turn_end']
const firstLine = (text: string, limit = 200) => (text.split('\n').find((l) => l.trim()) ?? '').slice(0, limit)
/** A prompt's most telling line: the first that is not a bare heading such as "Transition feedback:". */
const promptLine = (text: string) => (text.split('\n').find((l) => l.trim() && !l.trim().endsWith(':')) ?? firstLine(text)).slice(0, 200)

export function fromAgentEvent(event: AgentEvent, index: number): TimelineItem {
  const kind = (KNOWN as string[]).includes(event.type) ? (event.type as EventKind) : 'other'
  const text = event.text ?? ''
  const output = event.output ?? ''
  const usage = event.usage
  const titles: Record<string, string> = {
    message: event.role === 'optimizer' ? 'Optimizer message' : 'Agent message',
    reasoning: 'Reasoning',
    command: 'Command',
    file_change: 'File change',
    tool: `Tool · ${event.tool || 'tool'}`,
    image: 'Image',
    usage: 'Token usage',
    error: 'Error',
    turn_end: 'Turn end',
  }
  const usageText = usage ? `in ${usage.input ?? 0} · out ${usage.output ?? 0} · reasoning ${usage.reasoning ?? 0} · cached ${usage.cached ?? 0}` : ''
  return {
    id: `ev-${index}`,
    kind,
    title: titles[kind] ?? event.type,
    summary: kind === 'usage' ? usageText : firstLine(text || output),
    input: kind === 'command' || kind === 'tool' || kind === 'file_change' ? text : undefined,
    body: kind === 'command' || kind === 'tool' || kind === 'file_change' ? output : text,
    meta: event.exit_code === null || event.exit_code === undefined ? undefined : `exit ${event.exit_code}`,
    turn: event.turn ?? null,
    at: event.t ?? null,
    role: event.role,
    diff: kind === 'file_change' && event.diff ? event.diff : undefined,
    diffNote: kind === 'file_change' && event.diff_note ? event.diff_note : undefined,
  }
}

/**
 * The prompts we sent, placed in the timeline: the system prompt (and mission) before everything,
 * and each turn's message just before that turn's first event. Collapsed like any other item.
 */
export function withPrompts(items: TimelineItem[], prompts: SessionPrompts | null | undefined, context = 'session'): TimelineItem[] {
  if (!prompts) return items
  const out: TimelineItem[] = []
  const firstTurn = items.find((i) => i.turn !== null)?.turn ?? 1
  const opening = (id: string, title: string, text: string) => out.push({ id, kind: 'prompt', title, summary: firstLine(text), body: text, turn: firstTurn, at: items[0]?.at ?? null, role: 'user' })
  if (prompts.system) opening(`${context}-system`, 'System prompt', prompts.system)
  if (prompts.mission) opening(`${context}-mission`, 'Mission', prompts.mission)
  const placed = new Set<string>()
  for (const item of items) {
    const key = item.turn === null ? '' : String(item.turn)
    if (key && !placed.has(key)) {
      placed.add(key)
      const text = prompts.turns[key]
      if (text) out.push({ id: `${context}-turn-${key}`, kind: 'prompt', title: 'Prompt to agent', summary: promptLine(text), body: text, turn: item.turn, at: item.at, role: 'user' })
    }
    out.push(item)
  }
  return out
}

/** One line of a unified diff, classified for colouring. */
export type DiffLine = { kind: 'add' | 'del' | 'hunk' | 'head' | 'same'; text: string }

export function diffLines(diff: string): DiffLine[] {
  return diff.split('\n').map((text) => ({
    kind: text.startsWith('+++') || text.startsWith('---') ? 'head'
      : text.startsWith('@@') ? 'hunk'
        : text.startsWith('+') ? 'add'
          : text.startsWith('-') ? 'del' : 'same',
    text,
  }))
}

export function fromAvoLog(entry: AvoLogEntry): TimelineItem {
  const kind: EventKind =
    entry.category === 'reasoning' ? 'reasoning'
      : entry.category === 'environment' ? 'environment'
        : entry.category === 'tools' ? (entry.kind === 'file_change' || entry.title === 'File changes' ? 'file_change' : entry.title.startsWith('Tool') ? 'tool' : 'command')
          : entry.kind === 'error' ? 'error'
            : entry.role === 'user' ? 'prompt'
              : entry.kind === 'image' ? 'image'
                : entry.category === 'conversation' ? 'message' : 'other'
  return {
    id: entry.id,
    kind,
    title: entry.title,
    summary: entry.summary,
    input: entry.input,
    body: entry.body,
    meta: entry.meta,
    turn: entry.turn,
    at: entry.recorded_at,
    role: entry.role,
  }
}

interface LegacyTranscriptLine {
  timestamp?: string
  decision?: number
  prompt?: string
  response?: unknown
  result?: unknown
}

const asText = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value, null, 2))

/** Older direct-player runs have no agent_events.jsonl; `transcript.jsonl` holds prompt/response per decision. */
export function fromLegacyTranscript(text: string): TimelineItem[] {
  const items: TimelineItem[] = []
  text.split('\n').forEach((line, index) => {
    if (!line.trim()) return
    let row: LegacyTranscriptLine
    try {
      row = JSON.parse(line)
    } catch {
      return
    }
    const turn = row.decision ?? index + 1
    if (row.prompt) items.push({ id: `tr-${index}-p`, kind: 'prompt', title: 'Prompt to agent', summary: firstLine(row.prompt), body: row.prompt, turn, at: row.timestamp ?? null, role: 'user' })
    const response = asText(row.response)
    if (response) items.push({ id: `tr-${index}-r`, kind: 'message', title: 'Agent response', summary: firstLine(response), body: response, turn, at: row.timestamp ?? null, role: 'assistant' })
    const result = asText(row.result)
    if (result) items.push({ id: `tr-${index}-x`, kind: 'environment', title: 'Environment result', summary: firstLine(result), body: result, turn, at: row.timestamp ?? null })
  })
  return items
}

export const KIND_LABEL: Record<EventKind, string> = {
  message: 'message', prompt: 'prompt', reasoning: 'reasoning', command: 'command', file_change: 'file change', tool: 'tool',
  image: 'image', usage: 'usage', error: 'error', turn_end: 'turn end', environment: 'environment', other: 'other',
}

/** Identity of a timeline event for pinning: stable across reloads and event windows. */
export const pinKey = (item: TimelineItem, context = '') =>
  [context, item.turn ?? '', item.kind, item.at ?? '', item.summary.slice(0, 120)].join('|')

/** The text a pin keeps: the event's input and body, or its summary. */
export const pinText = (item: TimelineItem) => [item.input, item.body].filter(Boolean).join('\n\n') || item.summary
