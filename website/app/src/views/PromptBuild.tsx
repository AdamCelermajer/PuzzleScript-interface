import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api, q } from '../api/client'
import { ChipGroup, Empty, ErrorBox, Loading, PageHeader, Select } from '../components/ui'
import type { CallRecord, Part } from './Calls'

/** workbench/prompt_build.py `transcript`: one recorded session, one item per model call. */
interface Piece { source: 'ours' | 'harness' | 'unknown'; text: string }
/** Something new in a call's request: the system prompt, a message, a tool result, an earlier answer sent again. */
type Sent =
  | { who: 'system'; text: string }
  | { who: 'us'; role: string; pieces?: Piece[]; image?: string }
  | { who: 'result'; role: string; of: string; text: string; images: string[] }
  | { who: 'model'; added?: boolean; resent?: boolean; thinking: string; text: string; tool_calls: string[] }
interface Answer { thinking: string; text: string; tool_calls: string[]; error: string }
interface ModelCall {
  call: number; compaction: boolean; notes: string[]; sent: Sent[]; answer: Answer
  built_from: { part: string; content: string; source: string }[]  // after a compaction: where each part comes from
}

interface Transcript {
  session: { harness: string | null; model: string | null; role: string | null; game_tools: string[] | null }
  system: Piece[]
  system_role: string
  tools: { name: string; definition: unknown }[]
  calls: ModelCall[]
  key_calls: number[]  // the first three calls, then the first compaction and the call after it
}

interface RecordedRun {
  id: string
  mode: string
  harness: string | null
  model: string | null
  modified: number | null
  sessions: { folder: string; role: string | null; calls: number }[]
}

const HARNESS: Record<string, string> = { opencode: 'OpenCode', 'opencode-lean': 'OpenCode lean', codex: 'Codex', 'claude-code': 'Claude Code', bare: 'bare', antigravity: 'Antigravity' }
const harnessName = (id: string | null) => (id ? HARNESS[id] ?? id : 'harness')
const HARNESS_ORDER = ['opencode', 'opencode-lean', 'codex', 'claude-code', 'bare', 'antigravity']
const when = (r: RecordedRun) => (r.modified ? new Date(r.modified).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : r.id)

/** What the model was sent and what it did, as one conversation. */
export function PromptBuildView() {
  const runs = useQuery({
    queryKey: ['prompt-builds'],
    queryFn: ({ signal }) => api.get<{ runs: RecordedRun[] }>('/prompt-builds', signal),
  })
  const [harness, setHarness] = useState('opencode')
  const [mode, setMode] = useState('')
  const [folder, setFolder] = useState('')
  const list = runs.data?.runs ?? []  // framework mode first, newest first within it
  const harnesses = HARNESS_ORDER.filter((h) => list.some((r) => r.harness === h))
  const ofHarness = list.filter((r) => r.harness === harness)
  const modes = [...new Set(ofHarness.map((r) => r.mode))]
  const shownMode = modes.includes(mode) ? mode : modes[0]
  const run = ofHarness.find((r) => r.mode === shownMode)  // the latest recorded run of this framework and harness
  const session = run?.sessions.find((s) => s.folder === folder) ?? run?.sessions[0]
  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <PageHeader title="Prompt build" />
      {runs.isLoading ? <Loading /> : runs.error ? <ErrorBox error={runs.error} /> : (
        <>
          <ChipGroup options={harnesses} value={[harness]} single labels={HARNESS}
                     onChange={(v) => { setHarness(v[0]); setMode(''); setFolder('') }} />
          {!run || !session ? (
            <Empty title={`No recorded run with ${harnessName(harness)} yet`}>Runs started since 1 Nov 2026 appear here.</Empty>
          ) : <>
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <Select value={shownMode} onChange={(e) => { setMode(e.target.value); setFolder('') }}>
              {modes.map((m) => <option key={m} value={m}>{m}</option>)}
            </Select>

            {run.sessions.length > 1 && (
              <Select value={session.folder} onChange={(e) => setFolder(e.target.value)}>
                {run.sessions.map((s) => <option key={s.folder} value={s.folder}>{s.role ?? s.folder}</option>)}
              </Select>
            )}
          </div>
          <div className="text-[11.5px] text-faint">
            From the latest recorded run ({when(run)}), exactly as sent.
            After changing a prompt or the architecture, one short run of this framework refreshes it.
          </div>
          <Conversation key={`${run.id}|${session.folder}`} runId={run.id} folder={session.folder} />
          </>}
        </>
      )}
    </div>
  )
}

/** One recorded session, one row per model call; also the run page's Model calls tab (live, every call shown). */
export function Conversation({ runId, folder, live, full }: { runId: string; folder: string; live?: boolean; full?: boolean }) {
  const [everything, setEverything] = useState(full ?? false)
  const data = useQuery({
    queryKey: ['prompt-build', runId, folder],
    queryFn: ({ signal }) => api.get<Transcript>(`/prompt-builds/one${q({ run: runId, folder })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  if (data.isLoading) return <Loading />
  if (data.error) return <ErrorBox error={data.error} />
  const t = data.data!
  const harness = harnessName(t.session.harness)
  const ours = new Set(t.session.game_tools ?? [])
  const ourTools = t.tools.filter((tool) => ours.has(tool.name))
  const theirTools = t.tools.filter((tool) => !ours.has(tool.name))
  const seenOurs = t.system.findIndex((p) => p.source === 'ours')
  const image = (name: string) => `/api/workbench/record/calls/file${q({ run: runId, folder, name })}`
  return (
    <div className="flex flex-col gap-5 text-[13px]">
      <Section title="System prompt" role={t.system_role}>
        {t.system.map((p, i) => (
          <Fold key={i} label={`${p.source === 'ours' ? 'Our system prompt' : p.text.includes('<available_skills>') ? `${harness} skill list` : `${harness} system prompt${seenOurs >= 0 && i > seenOurs ? ', after ours' : ''}`} (${p.text.length.toLocaleString()} characters)`}>
            <Text>{p.text}</Text>
          </Fold>
        ))}
      </Section>

      <Section title="Tools" role="tools field (the provider writes them into the system part)">
        {theirTools.length > 0 && <Fold label={`${harness} tools (${theirTools.length}): ${theirTools.map((tool) => tool.name).join(', ')}`}>
          <Text>{JSON.stringify(theirTools.map((tool) => tool.definition), null, 2)}</Text>
        </Fold>}
        {ourTools.length > 0 && <Fold label={`Our tools (${ourTools.length}): ${ourTools.map((tool) => tool.name).join(', ')}`}>
          <Text>{JSON.stringify(ourTools.map((tool) => tool.definition), null, 2)}</Text>
        </Fold>}
      </Section>

      {t.session.harness?.startsWith('opencode') && <Section title="Compaction format (OpenCode 1.19.5)">
        <Fold label="what OpenCode sends when the context is full">
          <CompactionFormat />
        </Fold>
      </Section>}

      <Section title="Model calls">
        <div className="flex flex-col">
          {shortened(t.calls, everything ? undefined : t.key_calls).map((item, i) => 'gap' in item
            ? <button key={`gap-${i}`} onClick={() => setEverything(true)}
                      className="my-1 py-2 text-center text-faint hover:text-accent">
                * * *&nbsp;&nbsp;{item.gap === 1 ? '1 call' : `${item.gap} calls`} not shown (show everything)
              </button>
            : <CallRow key={item.call} item={item} harness={harness} image={image} runId={runId} folder={folder} />)}
        </div>
      </Section>
    </div>
  )
}

/** OpenCode's compaction as recorded on 3 Nov 2026 (OpenCode 1.19.5; agentic output/baseline/20261103T102907-7ceaca-ps_modality-v1
 * calls 13-14, turn-based output/baseline/20261103T113437-c92af0-ps_modality-v1 calls 28-29), and the
 * "What did we do so far?" text in its message builder. */
const COMPACTION: [string, [string, string, string][]][] = [
  ['1. The summary call (one request, no tools)', [
    ['system', 'OpenCode\'s summarizer prompt: "You are a context summarization agent… so another coding agent can continue the work." (630 characters)', 'OpenCode'],
    ['user', '"Here is the conversation so far: <conversation> …every message so far as text… </conversation>", then a summary template: Objective, Important Details, Work State (Completed / Active / Blocked), Next Move, Relevant Files', 'OpenCode, with the conversation inside'],
    ['answer', 'thinking + the filled template (the summary)', 'the model'],
  ]],
  ['2. Every call after it (the earlier messages are no longer sent)', [
    ['system + tools', 'the normal ones again', 'as before the compaction'],
    ['user', '"What did we do so far?"', 'OpenCode: its compaction marker written as a question'],
    ['assistant', 'thinking + summary, in one message', 'the model\'s answer in the summary call'],
    ['assistant', 'agentic run only: thinking + the last move (a tool call), in one message. The turn-based run kept no move here.', 'the model\'s answer in the call before the compaction'],
    ['tool', 'agentic run only: that move\'s result (the current grid)', 'our game'],
    ['user', '"Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed."', 'OpenCode'],
  ]],
]

function CompactionFormat() {
  return (
    <div className="flex flex-col gap-3 text-[12px]">
      {COMPACTION.map(([title, rows]) => (
        <div key={title}>
          <div className="mb-1 font-semibold text-muted">{title}</div>
          <table className="w-full border-collapse">
            <thead><tr className="text-left text-faint">
              <th className="border-b border-line py-1 pr-3 font-normal">message</th>
              <th className="border-b border-line py-1 pr-3 font-normal">content</th>
              <th className="border-b border-line py-1 font-normal">comes from</th>
            </tr></thead>
            <tbody>{rows.map(([part, content, source], i) => (
              <tr key={i} className="align-top">
                <td className="border-b border-line py-1 pr-3 whitespace-nowrap text-muted">{part}</td>
                <td className="border-b border-line py-1 pr-3">{content}</td>
                <td className="border-b border-line py-1">{source}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

/** The key calls in order, each run of other calls folded into one gap. */
function shortened(calls: ModelCall[], key?: number[]): (ModelCall | { gap: number })[] {
  const shown: (ModelCall | { gap: number })[] = []
  for (const c of calls) {
    const last = shown[shown.length - 1]
    if (!key || key.includes(c.call)) shown.push(c)
    else if (last && 'gap' in last) last.gap += 1
    else shown.push({ gap: 1 })
  }
  return shown
}

/** One model call: what was new in its request, then the model's answer. */
function CallRow({ item, harness, image, runId, folder }: { item: ModelCall; harness: string; image: (name: string) => string; runId: string; folder: string }) {
  const { answer } = item
  return (
    <div className={`grid grid-cols-[64px_1fr] gap-x-3 gap-y-1.5 border-b border-line px-2 py-3 ${item.compaction ? 'rounded bg-warn-soft' : ''}`}>
      <div className="font-semibold text-muted">call {item.call}</div>
      <div className="flex min-w-0 flex-col gap-1.5">
        {item.notes.map((note, i) => <div key={i} className="text-[12px] text-warn">{note}</div>)}
        <WholeRequest runId={runId} folder={folder} call={item.call} image={image} />
        {item.built_from.length > 0 && <details>
          <summary className="cursor-pointer text-[11.5px] text-accent">how this request is built</summary>
          <table className="mt-1 w-full border-collapse text-[12px]">
            <thead><tr className="text-left text-faint">
              <th className="border-b border-line py-1 pr-3 font-normal">part</th>
              <th className="border-b border-line py-1 pr-3 font-normal">content</th>
              <th className="border-b border-line py-1 font-normal">comes from</th>
            </tr></thead>
            <tbody>{item.built_from.map((row, i) => (
              <tr key={i} className="align-top">
                <td className="border-b border-line py-1 pr-3 whitespace-nowrap text-muted">{row.part}</td>
                <td className="border-b border-line py-1 pr-3 font-mono break-words whitespace-pre-wrap">{row.content}</td>
                <td className="border-b border-line py-1">{row.source}</td>
              </tr>
            ))}</tbody>
          </table>
        </details>}
      </div>
      {item.sent.length > 0 && <>
        <div className="pt-0.5 text-[11px] text-faint">new in the request</div>
        <div className="flex min-w-0 flex-col gap-2">{item.sent.map((s, i) => <SentItem key={i} sent={s} harness={harness} image={image} />)}</div>
      </>}
      <div className="pt-0.5 text-[11px] font-semibold text-accent">model answer</div>
      <div className="flex min-w-0 flex-col gap-1">
        {answer.thinking && <Fold label="thinking"><Text>{answer.thinking}</Text></Fold>}
        {answer.text && <Text>{answer.text}</Text>}
        {answer.tool_calls.map((c, i) => c.length > 200
          ? <Fold key={i} label={`${c.slice(0, 100)}…`}><Text>{c}</Text></Fold>
          : <div key={i} className="font-mono">{c}</div>)}
        {answer.error && <div className="text-bad">{answer.error}</div>}
        {!answer.text && !answer.tool_calls.length && !answer.error && <div className="text-faint">(empty)</div>}
      </div>
    </div>
  )
}

function SentItem({ sent, harness, image }: { sent: Sent; harness: string; image: (name: string) => string }) {
  if (sent.who === 'system') return (
    <div><Label>system prompt</Label>{sent.text.length > 1500
      ? <Fold label={`${sent.text.length.toLocaleString()} characters`}><Text>{sent.text}</Text></Fold>
      : <Text>{sent.text}</Text>}</div>
  )
  if (sent.who === 'result') return (
    <div className="flex flex-col gap-1">
      <div><Label>tool result{sent.of ? ` of ${sent.of}` : ''}</Label></div>
      {sent.text.length > 800 ? <Fold label={`${sent.text.slice(0, 120).replace(/\s+/g, ' ')}…`}><Text>{sent.text}</Text></Fold> : <Text>{sent.text}</Text>}
      {sent.images.map((name) => <img key={name} src={image(name)} alt="" className="max-h-[200px] self-start rounded border border-line" style={{ imageRendering: 'pixelated' }} />)}
    </div>
  )
  if (sent.who === 'model') return (
    <div className="flex flex-col gap-1">
      <div><Label>{sent.added ? `assistant message written by ${harness}` : 'an earlier answer of the model, sent again'}</Label></div>
      {sent.thinking && <Fold label="its thinking"><Text>{sent.thinking}</Text></Fold>}
      {sent.text && (sent.text.length > 800 ? <Fold label={`${sent.text.slice(0, 120).replace(/\s+/g, ' ')}…`}><Text>{sent.text}</Text></Fold> : <Text>{sent.text}</Text>)}
      {sent.tool_calls.map((c, i) => <div key={i} className="font-mono">{c}</div>)}
    </div>
  )
  if (sent.image) return <div><Label>image</Label><img src={image(sent.image)} alt="" className="max-h-[200px] rounded border border-line" style={{ imageRendering: 'pixelated' }} /></div>
  const pieces = withQuotes(sent.pieces ?? [])
  const byHarness = pieces.every((p) => p.source !== 'ours') || around(pieces, '<conversation>', '</conversation>')[1].length > 0
  const piece = (p: Piece, i: number) => <Text key={i}>{p.text}</Text>
  const [before, inside, after] = around(pieces, '<conversation>', '</conversation>')
  return (
    <div className="flex flex-col gap-1">
      <div><Label>{sent.role} message, written by {byHarness ? harness : 'us'}</Label></div>
      {before.map((p, i) => p.source === 'harness' && !byHarness
        ? <div key={i} className="text-faint"><span className="text-[11px]">added by {harness}: </span><Text inline>{p.text}</Text></div>
        : piece(p, i))}
      {inside.length > 0 && <Fold label={`the conversation (${inside.reduce((n, p) => n + p.text.length, 0).toLocaleString()} characters)`}>
        <div className="flex flex-col gap-1 border-l-2 border-line pl-2">{inside.map(piece)}</div>
      </Fold>}
      {after.map(piece)}
    </div>
  )
}

/** The pieces split at an opening and a closing tag (each kept outside): before, between, after. */
function around(pieces: Piece[], open: string, close: string): [Piece[], Piece[], Piece[]] {
  const parts: [Piece[], Piece[], Piece[]] = [[], [], []]
  let at = 0
  for (const p of pieces) {
    let text = p.text
    for (const [tag, next] of [[open, 1], [close, 2]] as const) {
      const cut = at === next - 1 ? text.indexOf(tag) : -1
      if (cut < 0) continue
      const end = next === 1 ? cut + tag.length : cut
      if (text.slice(0, end).trim()) parts[at].push({ ...p, text: text.slice(0, end) })
      text = text.slice(end)
      at = next
    }
    if (text.trim()) parts[at].push({ ...p, text })
  }
  return at === 2 ? parts : [pieces, [], []]
}

/** The quotes OpenCode puts around our message, kept as plain text in our piece instead of a labelled piece. */
function withQuotes(pieces: Piece[]): Piece[] {
  const quote = (p?: Piece) => p?.source === 'harness' && /^\s*"\s*$/.test(p.text)
  const folded = (i: number) => quote(pieces[i]) && (pieces[i - 1]?.source === 'ours' || pieces[i + 1]?.source === 'ours')
  return pieces.flatMap((p, i) => folded(i) ? [] : p.source !== 'ours' ? [p] : [{
    ...p, text: (quote(pieces[i - 1]) ? '"' : '') + p.text + (quote(pieces[i + 1]) ? '"' : ''),
  }])
}

/** The whole request behind one answer, as the model got it: the full history resent, not only what is new. */
function WholeRequest({ runId, folder, call, image }: { runId: string; folder: string; call: number; image: (name: string) => string }) {
  const [open, setOpen] = useState(false)
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-[11.5px] text-accent">model call</summary>
      {open && <WholeRequestBody runId={runId} folder={folder} call={call} image={image} />}
    </details>
  )
}

function WholeRequestBody({ runId, folder, call, image }: { runId: string; folder: string; call: number; image: (name: string) => string }) {
  const one = useQuery({
    queryKey: ['call', runId, folder, call],
    queryFn: ({ signal }) => api.get<CallRecord>(`/record/calls/one${q({ run: runId, folder, call })}`, signal),
    staleTime: Infinity,
  })
  if (one.isLoading) return <Loading />
  if (one.error) return <ErrorBox error={one.error} />
  const { view, unchanged_messages: kept, previous_messages: before, system_changed } = one.data!
  const rewritten = before !== null && kept < before
  const system = view.system.join('\n\n')
  return (
    <div className="mt-1 flex flex-col gap-1">
      <div className="text-[11.5px] text-faint">
        Request {call}, as one text: <span className="bg-warn-soft px-1 text-warn">highlighted</span> = new in this request, the rest was already sent before.
        {' '}<Label>gray tags</Label> are labels of this page, not sent; everything else is exactly what was sent.
        {rewritten && <span className="text-warn"> The context was rewritten here: only {kept} of the previous request's {before} messages were sent again.</span>}
        {system_changed && <span className="text-warn"> The system prompt changed here.</span>}
      </div>
      <div className="max-h-[70vh] overflow-auto rounded border border-line p-2 font-mono text-[12px] break-words whitespace-pre-wrap">
        <details className={before === null || system_changed ? 'border-l-2 border-warn bg-warn-soft pl-1.5 text-faint' : 'pl-2 text-faint'} open={system.length <= 1500}>
          <summary className="cursor-pointer"><Label>system prompt</Label> {system.length.toLocaleString()} characters, {system_changed ? 'changed in this request' : 'as in the previous request'} <Label>tools</Label> {view.tools.map((t) => t.name).join(', ')}</summary>
          {system}
        </details>
        {view.messages.map((m, i) => (
          <div key={i} className={before === null || i >= kept ? 'border-l-2 border-warn bg-warn-soft pl-1.5' : 'pl-2'}>
            <div className="mt-2"><Label>message {i + 1} · role: {m.role}</Label></div>
            {/* The same thinking in two fields (OpenRouter's reasoning and reasoning_details) reaches the model once. */}
            {m.parts.filter((p, j) => p.kind !== 'reasoning' || !m.parts.slice(0, j).some((o) => o.kind === 'reasoning' && o.text === p.text))
              .map((p, j) => <RequestPart key={j} part={p} image={image} />)}
          </div>
        ))}
      </div>
    </div>
  )
}

/** A label of this page inside the request text: never part of what was sent. */
function Label({ children }: { children: ReactNode }) {
  return <span className="rounded bg-line px-1 py-px font-sans text-[10.5px] whitespace-nowrap text-faint select-none">{children}</span>
}

function RequestPart({ part, image }: { part: Part; image: (name: string) => string }) {
  const picture = (name: string) => <img key={name} src={image(name)} alt="" className="my-1 block max-h-[160px] rounded border border-line" style={{ imageRendering: 'pixelated' }} />
  switch (part.kind) {
    case 'text': return <div>{part.text}</div>
    case 'image': return picture(part.file)
    case 'reasoning': return <div><Label>the model's earlier thinking</Label> <span className="text-muted">{part.text}</span></div>
    case 'tool_call': return <div><Label>tool call</Label> {part.name} {part.arguments ?? ''}</div>
    case 'tool_result': return <div><Label>tool result</Label> {part.text}{part.images.map(picture)}</div>
    default: return <div>{JSON.stringify(part.data)}</div>
  }
}

function Section({ title, role, children }: { title: string; role?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[11.5px] font-semibold tracking-wide text-faint uppercase">
        {title}
        {role && <span className="ml-2 font-mono text-[10.5px] font-normal tracking-normal normal-case" title="how the request carries it">role: {role}</span>}
      </div>
      {children}
    </div>
  )
}

function Fold({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details>
      <summary className="cursor-pointer truncate text-muted">{label}</summary>
      <div className="mt-1">{children}</div>
    </details>
  )
}

function Text({ children, inline }: { children: string; inline?: boolean }) {
  return inline
    ? <span className="font-mono text-[12px] whitespace-pre-wrap">{children}</span>
    : <div className="font-mono text-[12px] break-words whitespace-pre-wrap">{children}</div>
}
