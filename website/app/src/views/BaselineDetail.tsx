import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, q } from '../api/client'
import { usePinActions, usePins } from '../api/hooks'
import type { RunRecord, Transition } from '../api/types'
import { GridCanvas, PixelImage } from '../components/Frame'
import { Markdown } from '../components/Markdown'
import { PinList } from '../components/Pins'
import { Timeline } from '../components/Timeline'
import { Button, Card, Empty, ErrorBox, KeyValues, Loading, Pre, Tabs } from '../components/ui'
import { fromAgentEvent, fromLegacyTranscript, pinKey, pinText, type TimelineItem } from '../lib/events'

const fileUrl = (run: string, file: string) => `/api/workbench/record/file${q({ run, file })}`
const frameFile = (index: number) => `frames/${String(index).padStart(3, '0')}.png`

type Tab = 'events' | 'pinned' | 'notes' | 'result' | 'files'

/** Baseline and baseline+ runs: replay of recorded transitions, agent events, notes, artifacts. */
export function BaselineDetail({ runId, live, notes: withNotes = true }: { runId: string; live?: boolean; notes?: boolean }) {
  const [eventsLimit, setEventsLimit] = useState(500)
  const record = useQuery({
    queryKey: ['record', runId, eventsLimit],
    queryFn: ({ signal }) => api.get<RunRecord>(`/record${q({ run: runId, events_limit: eventsLimit })}`, signal),
    refetchInterval: live ? 5000 : false,
    placeholderData: keepPreviousData,
  })
  const [tab, setTab] = useState<Tab>('events')
  const pins = usePins(runId)

  if (record.isLoading) return <Loading label="Reading run record…" />
  if (record.error) return <ErrorBox error={record.error} retry={() => record.refetch()} />
  const data = record.data!
  const notes = data.files.filter((f) => f.startsWith('workspace/') && f.endsWith('.md'))
  return (
    <div className="flex flex-col gap-4">
      <Replay runId={runId} record={data} live={live} />
      <div className="flex flex-col gap-3">
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'events', label: 'Agent timeline' },
            { id: 'pinned', label: `Pinned${pins.data?.length ? ` (${pins.data.length})` : ''}` },
            { id: 'notes', label: `Notes${notes.length ? ` (${notes.length})` : ''}`, hidden: !withNotes && !notes.length },
            { id: 'result', label: 'Result & spec' },
            { id: 'files', label: `Files (${data.files.length})` },
          ]}
        />
        {tab === 'events' && <Events runId={runId} record={data} onMore={() => setEventsLimit(5000)} />}
        {tab === 'pinned' && (pins.error ? <ErrorBox error={pins.error} /> : <PinList pins={pins.data ?? []} />)}
        {tab === 'notes' && <Notes runId={runId} files={notes} />}
        {tab === 'result' && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card title="Result"><Pre>{JSON.stringify(Object.keys(data.result).length ? data.result : 'No final result yet', null, 2)}</Pre></Card>
            <Card title="Run spec"><Pre>{JSON.stringify(data.run_spec ?? { normalized_from_legacy_config: data.normalized }, null, 2)}</Pre></Card>
            {Object.keys(data.error).length > 0 && <Card title="Error"><Pre>{JSON.stringify(data.error, null, 2)}</Pre></Card>}
          </div>
        )}
        {tab === 'files' && (
          <Card>
            {data.files.length ? (
              <ul className="flex flex-col gap-1 font-mono text-[12px]">
                {data.files.map((f) => <li key={f}><a href={fileUrl(runId, f)} target="_blank" rel="noreferrer">{f}</a></li>)}
              </ul>
            ) : <Empty title="No artifacts saved" />}
          </Card>
        )}
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

function Replay({ runId, record, live }: { runId: string; record: RunRecord; live?: boolean }) {
  const total = record.latest_transition?.action_index ?? 0
  const recordedActions = Number(record.result.action_count ?? 0)
  // null = follow the latest transition.
  const [index, setIndex] = useState<number | null>(null)
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
  }, [position, total])

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
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_auto_auto_minmax(0,1fr)]">
          <FramePicture src={fileUrl(runId, frameFile(Math.max(0, decision - 1)))} caption={`Before ${current.action} (shown to the agent)`} />
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
      return events.map((event, i) => fromAgentEvent(event, first + i))
    }
    return legacy.data ? fromLegacyTranscript(legacy.data) : []
  }, [record.agent_events, legacy.data])
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

function Notes({ runId, files }: { runId: string; files: string[] }) {
  const [file, setFile] = useState(files[0] ?? '')
  const content = useQuery({
    queryKey: ['note', runId, file],
    enabled: Boolean(file),
    queryFn: ({ signal }) => api.text(fileUrl(runId, file), signal),
  })
  if (!files.length) return <Empty title="No notes saved">Baseline+ runs keep markdown notes in workspace/notes/.</Empty>
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
