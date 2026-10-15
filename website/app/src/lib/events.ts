import type { AgentEvent, AvoLogEntry } from '../api/types'

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
}

const KNOWN: EventKind[] = ['message', 'reasoning', 'command', 'file_change', 'tool', 'image', 'usage', 'error', 'turn_end']
const firstLine = (text: string, limit = 200) => (text.split('\n').find((l) => l.trim()) ?? '').slice(0, limit)

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
  }
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
