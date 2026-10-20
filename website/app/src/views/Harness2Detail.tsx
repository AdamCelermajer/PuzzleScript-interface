import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, q } from '../api/client'
import { usePinActions, usePins } from '../api/hooks'
import type { AgentEvent, CoachSession, RunRecord } from '../api/types'
import { Timeline } from '../components/Timeline'
import { Card, Collapsible, ErrorBox, Loading, Pre, cx } from '../components/ui'
import { fromAgentEvent, pinKey, pinText, type TimelineItem } from '../lib/events'
import { BaselineDetail } from './BaselineDetail'

const ROLE: Record<string, string> = { base: 'starting harness', inv: 'general edit', dom: 'game-specific edit', agg: 'composed', c: 'sequential step', final: 'fresh run of the adopted harness' }
const role = (label: string) => ROLE[label.replace(/\d+$/, '')] ?? ''
const STAGE: Record<string, string> = { INV: 'INV · general habits', DOM: 'DOM · game knowledge', compose: 'Composer', reflect: 'Lesson', select: 'Selector' }

type Picked = { kind: 'rollout' | 'coach'; id: string }

/** Harness²: the player's rollouts (each a full Baseline · agent run), the coach's sessions, and the harness each stage wrote. */
export function Harness2Detail({ runId, live }: { runId: string; live?: boolean }) {
  const record = useQuery({
    queryKey: ['record', runId, 0],
    queryFn: ({ signal }) => api.get<RunRecord>(`/record${q({ run: runId, events_limit: 0 })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  const [picked, setPicked] = useState<Picked | null>(null)
  if (record.isLoading) return <Loading label="Reading rollouts…" />
  if (record.error) return <ErrorBox error={record.error} retry={() => record.refetch()} />
  const rollouts = record.data?.rollouts ?? []
  const coach = record.data?.coach_sessions ?? []
  const edits = record.data?.harness_edits ?? {}
  const adoption = record.data?.adoption
  const current: Picked | null = picked ?? (rollouts.length ? { kind: 'rollout', id: rollouts.at(-1)!.label } : null)
  const isPicked = (kind: Picked['kind'], id: string) => current?.kind === kind && current.id === id
  const chip = (on: boolean) => cx('flex flex-col rounded-md border px-2.5 py-1 text-left', on ? 'border-accent bg-accent-soft' : 'border-line-strong hover:bg-sunken')
  return (
    <div className="flex flex-col gap-4">
      <Card title="Rollouts · the player" actions={adoption?.adopted_label ? <span className="text-[12px] text-muted">adopted {adoption.adopted_label} · best {adoption.best_of_pool_levels ?? '—'} levels</span> : undefined}>
        {rollouts.length ? (
          <div className="flex flex-wrap gap-1.5">
            {rollouts.map((r) => {
              const levels = r.result?.levels_completed ?? r.latest_transition?.after?.levels_completed
              const actions = r.result?.action_count ?? r.latest_transition?.action_index
              return (
                <button key={r.label} type="button" onClick={() => setPicked({ kind: 'rollout', id: r.label })} title={role(r.label)} className={chip(isPicked('rollout', r.label))}>
                  <span className={cx('font-mono text-[12px]', isPicked('rollout', r.label) && 'text-accent')}>{r.label}{r.label === adoption?.adopted_label ? ' ★' : ''}</span>
                  <span className="text-[11px] text-muted">{String(levels ?? 0)} levels · {String(actions ?? 0)} actions{r.result ? '' : ' · playing'}</span>
                </button>
              )
            })}
          </div>
        ) : <div className="text-[12px] text-faint">No rollout has started yet.</div>}
        <div className="mt-2 text-[11.5px] text-muted">base = starting harness · inv / dom = general and game-specific edits · agg = composed · final = fresh run of the adopted harness (the reported result).</div>
      </Card>

      <Card title="Coach sessions · the improver">
        {coach.length ? (
          <div className="flex flex-wrap gap-1.5">
            {coach.map((s) => (
              <button key={s.id} type="button" onClick={() => setPicked({ kind: 'coach', id: s.id })} title={`${s.model ?? ''} · ${s.id}`} className={chip(isPicked('coach', s.id))}>
                <span className={cx('text-[12px] font-medium', isPicked('coach', s.id) && 'text-accent')}>{s.stage ? STAGE[s.stage] : 'Coach session'}</span>
                <span className={cx('text-[11px]', s.length_cap ? 'text-bad' : 'text-muted')}>
                  {s.length_cap ? 'hit the reply length cap' : s.finished ? 'finished' : 'working'} · {s.file_changes} file edits · {s.events} events
                </span>
              </button>
            ))}
          </div>
        ) : <div className="text-[12px] text-faint">The coach starts after the base rollout ends.</div>}
        <div className="mt-2 text-[11.5px] text-muted">INV writes general playing habits, DOM writes knowledge about this game, the composer merges what helped. A session that writes no edit falls back to the empty harness.</div>
      </Card>

      {Object.keys(edits).length > 0 && (
        <Card title="Harness edits · what each stage wrote">
          <div className="flex flex-col gap-2">
            {Object.entries(edits).map(([label, files]) => (
              <Collapsible key={label} title={<span className="font-mono text-[12.5px]">{label} <span className="text-faint">· {role(label)} · {Object.keys(files).length ? `${Object.keys(files).length} files` : 'empty (fell back to the base harness)'}</span></span>}>
                <div className="flex flex-col gap-2">
                  {Object.entries(files).map(([name, text]) => (
                    <div key={name}>
                      <div className="font-mono text-[11.5px] text-muted">{name}</div>
                      <Pre>{text}</Pre>
                    </div>
                  ))}
                </div>
              </Collapsible>
            ))}
          </div>
        </Card>
      )}

      {current?.kind === 'rollout' && <BaselineDetail key={current.id} runId={`${runId}/rollouts/${current.id}`} live={live} notes={false} />}
      {current?.kind === 'coach' && <CoachTimeline key={current.id} runId={runId} session={coach.find((s) => s.id === current.id)} live={live} />}
    </div>
  )
}

function CoachTimeline({ runId, session, live }: { runId: string; session?: CoachSession; live?: boolean }) {
  const events = useQuery({
    queryKey: ['coach-session', runId, session?.id],
    enabled: Boolean(session),
    queryFn: ({ signal }) => api.get<{ agent_events: { total: number; events: AgentEvent[] } }>(`/harness2/session${q({ run: runId, session: session!.id })}`, signal),
    refetchInterval: live && !session?.finished ? 5000 : false,
    placeholderData: keepPreviousData,
  })
  const items = useMemo(() => {
    const data = events.data?.agent_events
    if (!data) return []
    const first = data.total - data.events.length
    return data.events.map((event, i) => fromAgentEvent(event, first + i))
  }, [events.data])
  const pins = usePins(runId)
  const actions = usePinActions()
  if (!session) return null
  const context = `coach ${session.stage ?? session.id}`
  const keys = new Map((pins.data ?? []).map((p) => [p.key, p.id]))
  const togglePin = (item: TimelineItem) => {
    const existing = keys.get(pinKey(item, context))
    if (existing) actions.remove.mutate(existing)
    else actions.add.mutate({ run: runId, key: pinKey(item, context), context, turn: item.turn, kind: item.kind, title: item.title, text: pinText(item), at: item.at })
  }
  return (
    <Card title={`${session.stage ? STAGE[session.stage] : 'Coach session'} · ${session.model ?? ''}`}>
      {events.isLoading ? <Loading label="Reading the coach session…" /> : events.error ? <ErrorBox error={events.error} /> : (
        <Timeline items={items} pinned={(item) => keys.has(pinKey(item, context))} onPin={togglePin} emptyText="No events yet" />
      )}
    </Card>
  )
}
