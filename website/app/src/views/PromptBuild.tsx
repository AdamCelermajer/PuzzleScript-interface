import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api, q } from '../api/client'
import { ChipGroup, Empty, ErrorBox, Loading, PageHeader, Select } from '../components/ui'

/** workbench/prompt_build.py `transcript`: one recorded session, read top to bottom. */
interface Piece { source: 'ours' | 'harness' | 'unknown'; text: string }
type Entry =
  | { who: 'us'; pieces?: Piece[]; image?: string }
  | { who: 'model'; thinking: string; text: string; tool_calls: string[]; error: string }
  | { who: 'result'; of: string; text: string; images: string[] }
  | { who: 'note'; text: string }

interface Transcript {
  session: { harness: string | null; model: string | null; role: string | null; game_tools: string[] | null }
  system: Piece[]
  tools: { name: string; definition: unknown }[]
  entries: Entry[]
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
      <PageHeader title="Prompt build" subtitle="Exactly what the model was sent, and what it did, in order." />
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
            From the latest recorded run ({when(run)}); grids and cell changes are shown as &lt;grid&gt; and &lt;cells&gt;.
            After changing a prompt or the architecture, one short run of this framework refreshes it.
          </div>
          <Conversation key={`${run.id}|${session.folder}`} runId={run.id} folder={session.folder} />
          </>}
        </>
      )}
    </div>
  )
}

function Conversation({ runId, folder }: { runId: string; folder: string }) {
  const data = useQuery({
    queryKey: ['prompt-build', runId, folder],
    queryFn: ({ signal }) => api.get<Transcript>(`/prompt-builds/one${q({ run: runId, folder })}`, signal),
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
      <Section title="System prompt">
        {t.system.map((p, i) => (
          <Fold key={i} label={`${p.source === 'ours' ? 'Our system prompt' : p.text.includes('<available_skills>') ? `${harness} skill list` : `${harness} system prompt${seenOurs >= 0 && i > seenOurs ? ', after ours' : ''}`} (${p.text.length.toLocaleString()} characters)`}>
            <Text>{p.text}</Text>
          </Fold>
        ))}
      </Section>

      <Section title="Tools">
        {theirTools.length > 0 && <Fold label={`${harness} tools (${theirTools.length}): ${theirTools.map((tool) => tool.name).join(', ')}`}>
          <Text>{JSON.stringify(theirTools.map((tool) => tool.definition), null, 2)}</Text>
        </Fold>}
        {ourTools.length > 0 && <Fold label={`Our tools (${ourTools.length}): ${ourTools.map((tool) => tool.name).join(', ')}`}>
          <Text>{JSON.stringify(ourTools.map((tool) => tool.definition), null, 2)}</Text>
        </Fold>}
      </Section>

      <Section title="Conversation">
        <div className="flex flex-col">
          {t.entries.map((e, i) => <Row key={i} n={i + 1} entry={e} harness={harness} image={image} />)}
        </div>
      </Section>
    </div>
  )
}

const WHO = { us: 'US', model: 'MODEL', result: 'RESULT', note: '' }

function Row({ n, entry, harness, image }: { n: number; entry: Entry; harness: string; image: (name: string) => string }) {
  if (entry.who === 'note') return <div className="my-2 rounded bg-warn-soft px-3 py-1.5 text-[12px] text-warn">{entry.text}</div>
  return (
    <div className="grid grid-cols-[28px_64px_1fr] gap-2 border-b border-line py-2">
      <div className="text-faint">{n}</div>
      <div className={entry.who === 'model' ? 'font-semibold text-accent' : 'font-semibold text-muted'}>{WHO[entry.who]}</div>
      <div className="flex min-w-0 flex-col gap-1">
        {entry.who === 'us' && (entry.image
          ? <img src={image(entry.image)} alt="" className="max-h-[200px] self-start rounded border border-line" style={{ imageRendering: 'pixelated' }} />
          : entry.pieces?.map((p, i) => p.source === 'harness'
            ? <div key={i} className="text-faint"><span className="text-[11px]">added by {harness}: </span><Text inline>{p.text}</Text></div>
            : <Text key={i}>{p.text}</Text>))}
        {entry.who === 'model' && <>
          {entry.thinking && <Fold label="thinking"><Text>{entry.thinking}</Text></Fold>}
          {entry.text && <Text>{entry.text}</Text>}
          {entry.tool_calls.map((c, i) => c.length > 200
            ? <Fold key={i} label={`${c.slice(0, 100)}…`}><Text>{c}</Text></Fold>
            : <div key={i} className="font-mono">{c}</div>)}
          {entry.error && <div className="text-bad">{entry.error}</div>}
        </>}
        {entry.who === 'result' && <>
          {entry.of && <div className="font-mono text-[11.5px] text-faint">{entry.of}</div>}
          {entry.text.length > 800 ? <Fold label={`${entry.text.slice(0, 120).replace(/\s+/g, ' ')}…`}><Text>{entry.text}</Text></Fold> : <Text>{entry.text}</Text>}
          {entry.images.map((name) => <img key={name} src={image(name)} alt="" className="max-h-[200px] self-start rounded border border-line" style={{ imageRendering: 'pixelated' }} />)}
        </>}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-[11.5px] font-semibold tracking-wide text-faint uppercase">{title}</div>
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
