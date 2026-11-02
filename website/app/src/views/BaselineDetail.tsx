import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, q } from '../api/client'
import { usePinActions, usePins } from '../api/hooks'
import type { NotesHistoryTurn, NotesTurn, RunRecord, Transition } from '../api/types'
import { DiffView } from '../components/Diff'
import { GridCanvas, PixelImage } from '../components/Frame'
import { Markdown } from '../components/Markdown'
import { PinList } from '../components/Pins'
import { Timeline } from '../components/Timeline'
import { Button, Card, Empty, ErrorBox, KeyValues, Loading, Pre, Select, Tabs } from '../components/ui'
import { fromAgentEvent, fromLegacyTranscript, pinKey, pinText, withPrompts, type TimelineItem } from '../lib/events'
import { FileViewer } from '../components/FileViewer'
import { Calls } from './Calls'

const fileUrl = (run: string, file: string) => `/api/workbench/record/file${q({ run, file })}`
const frameFile = (index: number) => `frames/${String(index).padStart(3, '0')}.png`

type Tab = 'events' | 'calls' | 'pinned' | 'notes' | 'result' | 'files'

/** Baseline runs: replay of recorded transitions, agent events, notes, artifacts. */
export function BaselineDetail({ runId, live, notes: withNotes = true }: { runId: string; live?: boolean; notes?: boolean }) {
  const [eventsLimit, setEventsLimit] = useState(500)
  const record = useQuery({
    queryKey: ['record', runId, eventsLimit],
    queryFn: ({ signal }) => api.get<RunRecord>(`/record${q({ run: runId, events_limit: eventsLimit })}`, signal),
    refetchInterval: live ? 5000 : false,
    placeholderData: keepPreviousData,
  })
  const [tab, setTab] = useState<Tab>('events')
  // The replay's action index; null = follow the latest transition. The Notes tab follows it too.
  const [step, setStep] = useState<number | null>(null)
  const pins = usePins(runId)

  if (record.isLoading) return <Loading label="Reading run record…" />
  if (record.error) return <ErrorBox error={record.error} retry={() => record.refetch()} />
  const data = record.data!
  const notes = data.files.filter((f) => f.startsWith('workspace/') && f.endsWith('.md'))
  return (
    <div className="flex flex-col gap-4">
      <Replay runId={runId} record={data} live={live} index={step} setIndex={setStep} />
      <div className="flex flex-col gap-3">
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'events', label: 'Agent timeline' },
            { id: 'calls', label: 'Model calls (exact)', hidden: !data.has_calls },
            { id: 'pinned', label: `Pinned${pins.data?.length ? ` (${pins.data.length})` : ''}` },
            { id: 'notes', label: `Notes${notes.length ? ` (${notes.length})` : ''}`, hidden: !withNotes && !notes.length },
            { id: 'result', label: 'Result & spec' },
            { id: 'files', label: `Files (${data.files.length})` },
          ]}
        />
        {tab === 'events' && <Events runId={runId} record={data} onMore={() => setEventsLimit(5000)} />}
        {tab === 'calls' && <Calls runId={runId} live={live} />}
        {tab === 'pinned' && (pins.error ? <ErrorBox error={pins.error} /> : <PinList pins={pins.data ?? []} />)}
        {tab === 'notes' && <Notes runId={runId} files={notes} live={live} step={step} />}
        {tab === 'result' && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card title="Result"><Pre>{JSON.stringify(Object.keys(data.result).length ? data.result : 'No final result yet', null, 2)}</Pre></Card>
            <Card title="Run spec"><Pre>{JSON.stringify(data.run_spec ?? { normalized_from_legacy_config: data.normalized }, null, 2)}</Pre></Card>
            {Object.keys(data.error).length > 0 && <Card title="Error"><Pre>{JSON.stringify(data.error, null, 2)}</Pre></Card>}
          </div>
        )}
        {tab === 'files' && (data.files.length ? <FileViewer files={data.files} url={(f) => fileUrl(runId, f)} /> : <Card><Empty title="No artifacts saved" /></Card>)}
      </div>
    </div>
  )
}

/** "1 / 4 · now on level 2"; a level completed by this very action is called out. */
function levelsText(t: Transition): string {
  const done = t.after?.levels_completed, total = t.after?.win_levels
  if (done === undefined || total === undefined) return '—'
  const justNow = (t.before?.levels_completed ?? done) < done ? ' · completed by this action' : ''
  return `${done} / ${total}${done < total ? ` · now on level ${done + 1}` : ''}${justNow}`
}

function FramePicture({ src, caption }: { src: string; caption: string }) {
  const [missing, setMissing] = useState(false)
  useEffect(() => setMissing(false), [src])
  return (
    <figure className="flex flex-col gap-1">
      <figcaption className="text-[11.5px] text-muted">{caption}</figcaption>
      {missing ? <div className="flex h-40 w-60 items-center justify-center rounded-md bg-sunken text-[12px] text-faint">No PNG saved</div> : <PixelImage src={src} alt={caption} onError={() => setMissing(true)} className="max-h-[300px] w-auto" />}
    </figure>
  )
}

function Replay({ runId, record, live, index, setIndex }: { runId: string; record: RunRecord; live?: boolean; index: number | null; setIndex: (index: number | null) => void }) {
  const total = record.latest_transition?.action_index ?? 0
  const recordedActions = Number(record.result.action_count ?? 0)
  const position = index ?? total
  const transition = useQuery({
    queryKey: ['timeline', runId, index],
    enabled: index !== null && index >= 1,
    queryFn: async ({ signal }): Promise<Transition> => (await api.get<{ transition: Transition }>(`/record/timeline${q({ run: runId, index: index! })}`, signal)).transition,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
  const current: Transition | undefined = index === null ? record.latest_transition : transition.data
  const decision = current?.decision ?? position

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === 'ArrowLeft') setIndex(Math.max(1, position - 1))
      if (event.key === 'ArrowRight') setIndex(position + 1 >= total ? null : position + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [position, total, setIndex])

  if (!total) {
    return (
      <Card title="Replay">
        <Empty title="No transitions recorded">
          {recordedActions ? `This older run saved ${recordedActions} actions without transitions.jsonl; see the agent timeline and files.` : live ? 'The run has not taken an action yet.' : 'Nothing to replay.'}
        </Empty>
      </Card>
    )
  }
  return (
    <Card
      title="Replay"
      actions={
        <div className="flex items-center gap-1.5">
          <Button size="sm" onClick={() => setIndex(1)} disabled={position <= 1}>⏮</Button>
          <Button size="sm" onClick={() => setIndex(Math.max(1, position - 1))} disabled={position <= 1}>← Prev</Button>
          <span className="w-28 text-center text-[12.5px] font-medium tabular-nums">{position} / {total}</span>
          <Button size="sm" onClick={() => setIndex(position + 1 >= total ? null : position + 1)} disabled={position >= total}>Next →</Button>
          <Button size="sm" variant={index === null ? 'primary' : 'default'} onClick={() => setIndex(null)}>{live ? 'Follow live' : 'Latest'}</Button>
        </div>
      }
    >
      <input type="range" min={1} max={total} value={position} onChange={(e) => { const v = Number(e.target.value); setIndex(v >= total ? null : v) }} className="mb-3 w-full accent-[var(--accent)]" />
      {transition.error && <ErrorBox error={transition.error} />}
      {current && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_auto_minmax(0,1fr)]">
          <FramePicture src={fileUrl(runId, frameFile(decision))} caption={`After ${current.action}`} />
          <figure className="flex flex-col gap-1">
            <figcaption className="text-[11.5px] text-muted">Grid after {current.action} · changed cells outlined</figcaption>
            <GridCanvas grid={current.after?.grid} highlight={current.changed_cells} maxSize={360} />
          </figure>
          <div className="flex min-w-0 flex-col gap-2">
            <KeyValues
              items={[
                ['Action', <span className="font-mono">{current.action}</span>],
                ['State', `${current.before?.state ?? '—'} → ${current.after?.state ?? '—'}`],
                ['Levels completed', levelsText(current)],
                ['Changed', current.changed ? `${current.changed_cells?.length ?? 0} cells` : 'no change'],
                ['Time', current.timestamp ?? '—'],
              ]}
            />
            {current.note && (
              <div>
                <div className="text-[11px] text-faint">Agent note</div>
                <div className="rounded-md bg-sunken p-2 text-[12.5px] whitespace-pre-wrap">{current.note}</div>
              </div>
            )}
            <div className="text-[11px] text-faint">Arrow keys step through actions.</div>
          </div>
        </div>
      )}
    </Card>
  )
}

function Events({ runId, record, onMore }: { runId: string; record: RunRecord; onMore: () => void }) {
  const legacyFile = record.agent_events ? null : record.files.includes('transcript.jsonl') ? 'transcript.jsonl' : null
  const legacy = useQuery({
    queryKey: ['transcript', runId],
    enabled: Boolean(legacyFile),
    queryFn: ({ signal }) => api.text(fileUrl(runId, legacyFile!), signal),
    staleTime: 30_000,
  })
  const items = useMemo(() => {
    if (record.agent_events) {
      // The API returns the newest events; index them from the start of the file so a row
      // keeps its React key (and expanded state) when newer events arrive on the next poll.
      const { events, total } = record.agent_events
      const first = total - events.length
      return withPrompts(events.map((event, i) => fromAgentEvent(event, first + i)), record.prompts)
    }
    return legacy.data ? fromLegacyTranscript(legacy.data) : []
  }, [record.agent_events, record.prompts, legacy.data])
  if (legacyFile && legacy.isLoading) return <Loading label="Reading transcript…" />
  if (legacy.error) return <ErrorBox error={legacy.error} />
  const events = record.agent_events
  const pins = usePins(runId)
  const actions = usePinActions()
  const keys = new Map((pins.data ?? []).map((p) => [p.key, p.id]))
  const togglePin = (item: TimelineItem) => {
    const existing = keys.get(pinKey(item))
    if (existing) actions.remove.mutate(existing)
    else actions.add.mutate({ run: runId, key: pinKey(item), turn: item.turn, kind: item.kind, title: item.title, text: pinText(item), at: item.at })
  }
  return (
    <div className="flex flex-col gap-2">
      {!events && legacyFile && <div className="text-[12px] text-muted">Older run without agent_events.jsonl: showing the saved transcript (prompt / response per decision).</div>}
      {events && record.prompts && !record.prompts.turns_recorded && (
        <div className="text-[12px] text-muted">This session's per-turn messages are not recorded; the timeline shows its system prompt only.</div>
      )}
      {actions.add.error ? <ErrorBox error={actions.add.error} /> : null}
      <Timeline
        items={items}
        pinned={(item) => keys.has(pinKey(item))}
        onPin={togglePin}
        footer={events?.truncated ? (
          <div className="flex items-center justify-between text-[12px] text-muted">
            Showing the last {events.events.length} of {events.total} events.
            <Button size="sm" onClick={onMore}>Load up to 5000</Button>
          </div>
        ) : null}
      />
    </div>
  )
}

/** With notes_history/ (notes saved after every harness turn) the tab steps through turns; otherwise the latest notes. */
function Notes({ runId, files, live, step }: { runId: string; files: string[]; live?: boolean; step: number | null }) {
  const history = useQuery({
    queryKey: ['notes-history', runId],
    queryFn: ({ signal }) => api.get<{ turns: NotesHistoryTurn[] }>(`/record/notes_history${q({ run: runId })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  if (history.isLoading) return <Loading label="Reading notes history…" />
  const turns = history.data?.turns ?? []
  return turns.length ? <NotesHistory runId={runId} turns={turns} step={step} /> : <LatestNotes runId={runId} files={files} />
}

/** The turn that played replay step `step`, or the last turn with a move before it; null = the latest turn. */
function turnForStep(turns: NotesHistoryTurn[], step: number | null): number {
  if (step === null) return turns[turns.length - 1].turn
  const played = turns.filter((t) => t.action_index !== null && t.action_index <= step)
  return (played[played.length - 1] ?? turns[0]).turn
}

function turnLabel(t: NotesHistoryTurn): string {
  return `Turn ${t.turn} · ${t.action_index ? `move ${t.action_index}` : t.kind === 'final_world_model' ? 'final world model' : 'no move'}`
}

function NotesHistory({ runId, turns, step }: { runId: string; turns: NotesHistoryTurn[]; step: number | null }) {
  // null = follow the replay.
  const [picked, setPicked] = useState<number | null>(null)
  const [changes, setChanges] = useState(false)
  const [file, setFile] = useState('')
  const turn = picked ?? turnForStep(turns, step)
  const position = turns.findIndex((t) => t.turn === turn)
  const content = useQuery({
    queryKey: ['notes-turn', runId, turn],
    queryFn: ({ signal }) => api.get<NotesTurn>(`/record/notes_history/turn${q({ run: runId, turn })}`, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
  const data = content.data
  const names = data ? [...new Set([...Object.keys(data.files), ...(changes ? Object.keys(data.diffs) : [])])].sort() : []
  const shown = names.includes(file) ? file : names[0] ?? ''
  const text = data?.files[shown]
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button size="sm" onClick={() => setPicked(turns[position - 1].turn)} disabled={position <= 0}>← Prev turn</Button>
        <Select value={turn} onChange={(e) => setPicked(Number(e.target.value))} className="h-6 text-[12px]">
          {turns.map((t) => <option key={t.turn} value={t.turn}>{turnLabel(t)}</option>)}
        </Select>
        <Button size="sm" onClick={() => setPicked(turns[position + 1].turn)} disabled={position < 0 || position >= turns.length - 1}>Next turn →</Button>
        <Button size="sm" variant={picked === null ? 'primary' : 'default'} onClick={() => setPicked(null)}>Follow the replay</Button>
        <Button size="sm" variant={changes ? 'primary' : 'default'} onClick={() => setChanges(!changes)}>Changes vs previous turn</Button>
        <span className="text-[11.5px] text-faint">notes/ saved after turn {turn}{turns[position]?.timestamp ? ` · ${turns[position].timestamp}` : ''}</span>
      </div>
      {content.error ? <ErrorBox error={content.error} /> : !data ? <Loading /> : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex flex-col gap-0.5">
            {names.map((f) => (
              <button key={f} type="button" onClick={() => setFile(f)} className={`truncate rounded px-2 py-1 text-left font-mono text-[12px] ${f === shown ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-sunken'}`}>
                {f}{data.diffs[f] ? ' •' : ''}
              </button>
            ))}
            <div className="mt-1 px-2 text-[11px] text-faint">• changed since {data.previous ? `turn ${data.previous}` : 'the start'}</div>
          </div>
          <Card>
            {!shown ? <Empty title="No notes files in this turn" /> : changes ? (
              data.diffs[shown] ? <DiffView diff={data.diffs[shown]} note={data.previous ? `vs turn ${data.previous}` : 'first saved turn'} /> : <div className="text-[12.5px] text-muted">Unchanged since turn {data.previous}.</div>
            ) : text === undefined ? <div className="text-[12.5px] text-muted">Deleted in this turn.</div> : shown.endsWith('.md') ? <Markdown>{text}</Markdown> : <Pre>{text}</Pre>}
          </Card>
        </div>
      )}
    </div>
  )
}

function LatestNotes({ runId, files }: { runId: string; files: string[] }) {
  const [file, setFile] = useState(files[0] ?? '')
  const content = useQuery({
    queryKey: ['note', runId, file],
    enabled: Boolean(file),
    queryFn: ({ signal }) => api.text(fileUrl(runId, file), signal),
  })
  if (!files.length) return <Empty title="No notes saved">Baseline runs keep markdown notes in workspace/notes/.</Empty>
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
      <div className="flex flex-col gap-0.5">
        {files.map((f) => (
          <button key={f} type="button" onClick={() => setFile(f)} className={`truncate rounded px-2 py-1 text-left font-mono text-[12px] ${f === file ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-sunken'}`}>
            {f.replace(/^workspace\//, '')}
          </button>
        ))}
      </div>
      <Card>{content.isLoading ? <Loading /> : content.error ? <ErrorBox error={content.error} /> : <Markdown>{content.data ?? ''}</Markdown>}</Card>
    </div>
  )
}
