import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, q } from '../api/client'
import { Button, Card, Collapsible, Empty, ErrorBox, KeyValues, Loading, Pill, Pre, Select } from '../components/ui'

/** One row of /record/calls. */
interface CallRow {
  call: number
  turn: number
  started: string
  seconds: number
  method: string
  url: string
  status: number
  error: string | null
  messages: number
  images: number
  bytes: number
  usage: Record<string, unknown> | null
  tool_calls: string[]
  replied: boolean
}

/** A message part in the one shape harnesses/recorder.py `view` gives every API dialect. */
export type Part =
  | { kind: 'text'; text: string }
  | { kind: 'image'; file: string }
  | { kind: 'reasoning'; text: string; field?: string }
  | { kind: 'tool_call'; id?: string; name?: string; arguments?: string }
  | { kind: 'tool_result'; id?: string; text: string; images: string[] }
  | { kind: 'other'; data: unknown }

interface View {
  dialect: string
  system: string[]
  messages: { role: string; parts: Part[] }[]
  tools: { name: string; definition: unknown }[]
  settings: Record<string, unknown>
}

export interface CallRecord {
  call: number
  turn: number
  session: string
  started: string
  seconds: number
  method: string
  url: string
  status: number
  error: string | null
  headers: Record<string, string>
  request: unknown
  view: View
  images: string[]
  response: { reasoning?: string; content?: string; tool_calls?: { id: string; name: string; arguments: string }[]; finish_reason?: string | null; usage?: unknown; model?: string; provider?: string; error?: unknown }
  response_raw: string
  previous_messages: number | null
  unchanged_messages: number
  system_changed: boolean
}

const callFile = (run: string, folder: string, name: string) => `/api/workbench/record/calls/file${q({ run, folder, name })}`
const tokens = (usage: Record<string, unknown> | null | undefined, key: string) => (usage && typeof usage[key] === 'number' ? (usage[key] as number) : null)

function rowLabel(r: CallRow): string {
  if (r.method !== 'POST') return `Call ${r.call} · turn ${r.turn} · ${r.method} ${new URL(r.url).pathname} (not a model request)`
  const sent = tokens(r.usage, 'prompt_tokens') ?? tokens(r.usage, 'input_tokens')
  const did = r.tool_calls.length ? r.tool_calls.join(', ') : r.replied ? 'text reply' : r.error ? 'failed' : '—'
  return `Call ${r.call} · turn ${r.turn} · ${r.messages} messages${sent !== null ? ` · ${sent.toLocaleString()} tokens in` : ''} · ${did}`
}

/** Every model call of the run, any harness: exactly what was sent, and what came back. */
export function Calls({ runId, live }: { runId: string; live?: boolean }) {
  const folders = useQuery({
    queryKey: ['call-folders', runId],
    queryFn: ({ signal }) => api.get<{ folders: { folder: string; calls: number }[] }>(`/record/calls/folders${q({ run: runId })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  const [folder, setFolder] = useState('')
  if (folders.isLoading) return <Loading label="Finding recorded calls…" />
  if (folders.error) return <ErrorBox error={folders.error} />
  const list = folders.data?.folders ?? []
  if (!list.length) return <Empty title="No calls recorded">Runs record every model call in calls/ since 1 Nov 2026.</Empty>
  const shown = list.some((f) => f.folder === folder) ? folder : list[0].folder
  return (
    <div className="flex flex-col gap-3">
      {list.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
          Session:
          <Select value={shown} onChange={(e) => setFolder(e.target.value)} className="h-6 text-[12px]">
            {list.map((f) => <option key={f.folder} value={f.folder}>{f.folder.replace(/\/?calls$/, '') || 'player'} ({f.calls} calls)</option>)}
          </Select>
        </div>
      )}
      <CallList key={shown} runId={runId} folder={shown} live={live} />
    </div>
  )
}

function CallList({ runId, folder, live }: { runId: string; folder: string; live?: boolean }) {
  const list = useQuery({
    queryKey: ['calls', runId, folder],
    queryFn: ({ signal }) => api.get<{ calls: CallRow[] }>(`/record/calls${q({ run: runId, folder })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  const [picked, setPicked] = useState<number | null>(null)
  if (list.isLoading) return <Loading label="Reading recorded calls…" />
  if (list.error) return <ErrorBox error={list.error} />
  const rows = list.data?.calls ?? []
  if (!rows.length) return <Empty title="No calls in this session" />
  const call = picked ?? rows[rows.length - 1].call
  const position = rows.findIndex((r) => r.call === call)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" onClick={() => setPicked(rows[position - 1].call)} disabled={position <= 0}>← Prev call</Button>
        <Select value={call} onChange={(e) => setPicked(Number(e.target.value))} className="h-6 max-w-[600px] text-[12px]">
          {rows.map((r) => <option key={r.call} value={r.call}>{rowLabel(r)}</option>)}
        </Select>
        <Button size="sm" onClick={() => setPicked(rows[position + 1].call)} disabled={position < 0 || position >= rows.length - 1}>Next call →</Button>
        <span className="text-[11.5px] text-faint">{rows.length} calls · one call = one request the harness sent to the model API</span>
      </div>
      <CallView runId={runId} folder={folder} call={call} />
    </div>
  )
}

function CallView({ runId, folder, call }: { runId: string; folder: string; call: number }) {
  const [all, setAll] = useState(false)
  const one = useQuery({
    queryKey: ['call', runId, folder, call],
    queryFn: ({ signal }) => api.get<CallRecord>(`/record/calls/one${q({ run: runId, folder, call })}`, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
  if (one.error) return <ErrorBox error={one.error} />
  if (!one.data) return <Loading />
  const data = one.data
  const { system, messages, tools, settings, dialect } = data.view
  const rewritten = data.previous_messages !== null && data.unchanged_messages < data.previous_messages
  const reply = data.response
  const file = (name: string) => callFile(runId, folder, name)
  return (
    <div className="flex flex-col gap-3">
      <Card title={`Call ${data.call} · turn ${data.turn}`} actions={<a className="text-[12px] text-accent" href={file(data.response_raw)} target="_blank" rel="noreferrer">raw reply bytes</a>}>
        <KeyValues items={[
          ['Sent at', `${data.started} · answered in ${data.seconds} s · HTTP ${data.status}${data.error ? ` · ${data.error}` : ''}`],
          ['Request', `${data.method} ${data.url} · ${dialect}`],
          ['Session', data.session || '—'],
          ['Context', data.previous_messages === null ? `${messages.length} messages (first model request)` : rewritten
            ? <span className="text-warn">{messages.length} messages. The context was rewritten: only the first {data.unchanged_messages} of the previous request's {data.previous_messages} messages were sent again unchanged (new session or compaction).</span>
            : `${messages.length} messages: the previous request's ${data.previous_messages} unchanged, plus ${messages.length - data.unchanged_messages} new`],
          ['Served by', [reply.provider, reply.model].filter(Boolean).join(' · ') || '—'],
          ['Usage', reply.usage ? JSON.stringify(reply.usage) : '—'],
        ]} />
      </Card>
      {data.method === 'POST' && <>
        <Collapsible title={`Sent: settings (${Object.keys(settings).length})`}>
          <Pre>{JSON.stringify(settings, null, 2)}</Pre>
        </Collapsible>
        <Collapsible title={`Sent: system prompt (${system.reduce((n, s) => n + s.length, 0).toLocaleString()} chars)${data.system_changed ? ' · changed since the previous request' : ''}`}>
          {system.length ? system.map((s, i) => <Pre key={i}>{s}</Pre>) : <div className="text-[12.5px] text-muted">No separate system prompt: see the messages.</div>}
        </Collapsible>
        <Collapsible title={`Sent: tools offered (${tools.length}) · ${tools.map((t) => t.name).join(', ')}`}>
          <Pre>{JSON.stringify(tools.map((t) => t.definition), null, 2)}</Pre>
        </Collapsible>
        <Card title={`Sent: messages (${messages.length})`} actions={<Button size="sm" variant={all ? 'primary' : 'default'} onClick={() => setAll(!all)}>{all ? 'Collapse earlier messages' : 'Expand all'}</Button>}>
          <div className="flex flex-col gap-1.5">
            {messages.map((m, i) => (
              <Collapsible
                key={`${call}-${i}-${all}`}
                defaultOpen={all || i >= data.unchanged_messages}
                title={<span>#{i + 1} <span className="font-mono">{m.role}</span> <span className="text-faint">· {m.parts.map((p) => p.kind).join(', ')}</span></span>}
                right={<span className="flex items-center gap-2 text-[11.5px] text-faint">{i >= data.unchanged_messages && <Pill tone="accent">new in this call</Pill>}{JSON.stringify(m).length.toLocaleString()} chars</span>}
              >
                <div className="flex flex-col gap-1.5">{m.parts.map((p, j) => <PartView key={j} part={p} file={file} />)}</div>
              </Collapsible>
            ))}
          </div>
        </Card>
        <Collapsible title="Sent: the request body exactly as saved (JSON)">
          <Pre>{JSON.stringify(data.request, null, 2)}</Pre>
        </Collapsible>
        <Collapsible title={`Sent: headers (${Object.keys(data.headers ?? {}).length}, credentials removed)`}>
          <Pre>{JSON.stringify(data.headers ?? {}, null, 2)}</Pre>
        </Collapsible>
      </>}
      <Card title="Returned">
        <div className="flex flex-col gap-2">
          {reply.error !== undefined && <Labeled label="Error">{JSON.stringify(reply.error, null, 2)}</Labeled>}
          <Labeled label={`Reasoning (${(reply.reasoning ?? '').length.toLocaleString()} characters)`}>{reply.reasoning || '—'}</Labeled>
          <Labeled label="Text">{reply.content || '—'}</Labeled>
          {(reply.tool_calls ?? []).map((c, i) => <Labeled key={i} label={`Tool call: ${c.name}`}>{prettyJson(c.arguments)}</Labeled>)}
          <div className="text-[12px] text-muted">finish: {String(reply.finish_reason ?? '—')}</div>
        </div>
      </Card>
    </div>
  )
}

function Labeled({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <div className="mb-1 text-[12px] font-medium text-muted">{label}</div>
      <Pre>{children}</Pre>
    </div>
  )
}

function prettyJson(text: string | undefined): string {
  try {
    return JSON.stringify(JSON.parse(text ?? ''), null, 2)
  } catch {
    return text ?? ''
  }
}

function Picture({ name, file }: { name: string; file: (name: string) => string }) {
  return (
    <div>
      <div className="mb-1 text-[12px] text-muted">image · {name}</div>
      <img src={file(name)} alt={name} className="max-h-[320px] rounded border border-line" style={{ imageRendering: 'pixelated' }} />
    </div>
  )
}

function PartView({ part, file }: { part: Part; file: (name: string) => string }) {
  switch (part.kind) {
    case 'text': return <Pre>{part.text || '(empty)'}</Pre>
    case 'image': return <Picture name={part.file} file={file} />
    case 'reasoning': return <Labeled label={`Reasoning sent back to the model${part.field ? ` (${part.field})` : ''}`}>{part.text || '(empty)'}</Labeled>
    case 'tool_call': return <Labeled label={`Tool call: ${part.name ?? '?'}${part.id ? ` · ${part.id}` : ''}`}>{prettyJson(part.arguments)}</Labeled>
    case 'tool_result': return (
      <div className="flex flex-col gap-1">
        <Labeled label={`Tool result${part.id ? ` for ${part.id}` : ''}`}>{part.text || '(empty)'}</Labeled>
        {part.images.map((name) => <Picture key={name} name={name} file={file} />)}
      </div>
    )
    default: return <Labeled label="Other (as sent)">{JSON.stringify(part.data, null, 2)}</Labeled>
  }
}
