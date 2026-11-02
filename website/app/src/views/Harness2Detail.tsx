import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, q } from '../api/client'
import { usePinActions, usePins } from '../api/hooks'
import type { AgentEvent, CoachSession, Harness2Level, Harness2Rollout, RunRecord, SessionPrompts } from '../api/types'
import { DiffView } from '../components/Diff'
import { Timeline } from '../components/Timeline'
import { Card, Collapsible, ErrorBox, Loading, Pre, cx } from '../components/ui'
import { fromAgentEvent, pinKey, pinText, withPrompts, type TimelineItem } from '../lib/events'
import { BaselineDetail } from './BaselineDetail'

const ROLE: Record<string, string> = { base: 'starting harness', inv: 'general edit', dom: 'game-specific edit', agg: 'composed', c: 'sequential step', final: 'fresh run of the adopted harness' }
const role = (label: string) => ROLE[label.replace(/\d+$/, '')] ?? ''
const STAGE: Record<string, string> = { INV: 'INV · general habits', DOM: 'DOM · game knowledge', compose: 'Composer', reflect: 'Lesson', select: 'Selector' }

type Picked = { kind: 'rollout' | 'coach'; id: string }
type StageRollout = Harness2Rollout
const chip = (on: boolean) => cx('flex flex-col rounded-md border px-2.5 py-1 text-left', on ? 'border-accent bg-accent-soft' : 'border-line-strong hover:bg-sunken')

/** Harness²: the player's rollouts (each a full Baseline · agent run), the coach's sessions, and the harness each stage wrote. */
export function Harness2Detail({ runId, live }: { runId: string; live?: boolean }) {
  const record = useQuery({
    queryKey: ['record', runId, 0],
    queryFn: ({ signal }) => api.get<RunRecord>(`/record${q({ run: runId, events_limit: 0 })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  if (record.isLoading) return <Loading label="Reading rollouts…" />
  if (record.error) return <ErrorBox error={record.error} retry={() => record.refetch()} />
  if (record.data?.levels) return <LevelsView runId={runId} levels={record.data.levels} live={live} />
  const adoption = record.data?.adoption
  return (
    <Stages runId={runId} rollouts={record.data?.rollouts ?? []} coach={record.data?.coach_sessions ?? []}
      edits={record.data?.harness_edits ?? {}} diffs={record.data?.harness_diffs ?? {}} live={live} kept={adoption?.adopted_label}
      keptNote={adoption?.adopted_label ? `adopted ${adoption.adopted_label} · best ${adoption.best_of_pool_levels ?? '—'} levels` : undefined}
      rolloutPath={(r) => `${runId}/rollouts/${r.label}`} perLevel={false} />
  )
}

const levelTone = (l: Harness2Level) => l.status === 'error' ? 'text-bad' : l.solved ? 'text-good' : l.status ? 'text-muted' : 'text-accent'
const levelState = (l: Harness2Level) => l.status === 'error' ? 'error' : l.solved ? `solved in ${l.action_count ?? '—'} actions` : l.status ? 'not solved' : 'playing'

/** A per-level run: a strip of levels, the picked level's rounds at their budgets, the harness it kept, and one round's stages. */
function LevelsView({ runId, levels, live }: { runId: string; levels: Harness2Level[]; live?: boolean }) {
  const [pickedLevel, setLevel] = useState<number | null>(null)
  const [pickedRound, setRound] = useState<string | null>(null)
  const level = levels.find((l) => l.level === pickedLevel) ?? levels.at(-1)
  const round = level?.rounds.find((r) => r.round === pickedRound) ?? level?.rounds.at(-1)
  const solved = levels.filter((l) => l.solved).length
  const levelPath = level ? `${runId}/levels/L${level.level}` : ''
  const rolloutPath = (r: StageRollout) => {
    const [from, label] = (r.reused ?? '').split('/')
    return r.reused ? `${levelPath}/rounds/${from}/rollouts/${label}` : `${levelPath}/rounds/${round?.round}/rollouts/${r.label}`
  }
  return (
    <div className="flex flex-col gap-4">
      <Card title="Levels · one task each, in order" actions={<span className="text-[12px] text-muted">{solved} of {levels.length} started levels solved</span>}>
        {levels.length ? (
          <div className="flex flex-wrap gap-1.5">
            {levels.map((l) => (
              <button key={l.level} type="button" onClick={() => { setLevel(l.level); setRound(null) }} title={l.error || undefined} className={chip(l === level)}>
                <span className={cx('font-mono text-[12px]', l === level && 'text-accent')}>L{l.level}</span>
                <span className={cx('text-[11px]', levelTone(l))}>
                  {levelState(l)} · {l.rounds.length} {l.rounds.length === 1 ? 'round' : 'rounds'}{l.rounds.at(-1)?.budget ? ` · last at ${l.rounds.at(-1)!.budget}` : ''}
                </span>
              </button>
            ))}
          </div>
        ) : <div className="text-[12px] text-faint">No level has started yet.</div>}
        <div className="mt-2 text-[11.5px] text-muted">Each level starts from the harness the previous level kept, at the budget the previous level ended on. An unsolved round moves on to the next budget; the budget never goes down.</div>
        {level?.error && <div className="mt-2 text-[12px] text-bad">{level.error}</div>}
      </Card>

      {level && (
        <Card title={`L${level.level} · rounds`}>
          {level.rounds.length ? (
            <div className="flex flex-wrap gap-1.5">
              {level.rounds.map((r) => (
                <button key={r.round} type="button" onClick={() => setRound(r.round)} className={chip(r === round)}>
                  <span className={cx('font-mono text-[12px]', r === round && 'text-accent')}>{r.round} · {r.budget ?? '—'} actions</span>
                  <span className={cx('text-[11px]', r.solved ? 'text-good' : 'text-muted')}>
                    {r.kept ? `${r.solved ? `solved in ${r.action_count}` : 'not solved'} · kept ${r.kept}` : 'playing'}
                  </span>
                </button>
              ))}
            </div>
          ) : <div className="text-[12px] text-faint">The first round has not started.</div>}
          <div className="mt-2 text-[11.5px] text-muted">A round: base1 plays the starting harness (in the level's first round; a later round reads the previous round's kept rollout instead), INV and DOM edit it side by side, and the composer merges them (agg1). The kept harness is chosen among the rollouts played at the round's budget.</div>
        </Card>
      )}

      {level && (
        <Card title={`Kept harness · what L${level.level} passes on`}>
          {Object.keys(level.kept_files).length ? (
            <div className="flex flex-col gap-2">
              {Object.entries(level.kept_files).map(([name, text]) => (
                <Collapsible key={name} title={<span className="font-mono text-[12.5px]">{name}</span>}><Pre>{text}</Pre></Collapsible>
              ))}
            </div>
          ) : <div className="text-[12px] text-faint">{level.status ? 'The empty harness: nothing kept.' : 'Written when the level ends.'}</div>}
        </Card>
      )}

      {level && round && (
        <Stages key={`${level.level}/${round.round}`} runId={`${levelPath}/rounds/${round.round}`} rollouts={round.rollouts}
          coach={round.coach_sessions} edits={round.harness_edits} diffs={round.harness_diffs} live={live} kept={round.kept}
          keptNote={round.kept ? `kept ${round.kept}` : undefined} rolloutPath={rolloutPath} perLevel />
      )}
    </div>
  )
}

/** One coaching cycle: its rollouts, its coach sessions, and the harness each stage wrote. */
function Stages({ runId, rollouts, coach, edits, diffs, live, kept, keptNote, rolloutPath, perLevel }: {
  runId: string; rollouts: StageRollout[]; coach: CoachSession[]; edits: Record<string, Record<string, string>>
  diffs: Record<string, Record<string, string>>; live?: boolean; kept?: string; keptNote?: string
  rolloutPath: (r: StageRollout) => string; perLevel: boolean
}) {
  const [picked, setPicked] = useState<Picked | null>(null)
  const current: Picked | null = picked ?? (rollouts.length ? { kind: 'rollout', id: rollouts.at(-1)!.label } : null)
  const isPicked = (kind: Picked['kind'], id: string) => current?.kind === kind && current.id === id
  const shown = current?.kind === 'rollout' ? rollouts.find((r) => r.label === current.id) : undefined
  return (
    <div className="flex flex-col gap-4">
      <Card title="Rollouts · the player" actions={keptNote ? <span className="text-[12px] text-muted">{keptNote}</span> : undefined}>
        {rollouts.length ? (
          <div className="flex flex-wrap gap-1.5">
            {rollouts.map((r) => {
              const levels = r.result?.levels_completed ?? r.latest_transition?.after?.levels_completed
              const actions = r.result?.action_count ?? r.latest_transition?.action_index
              const outcome = perLevel ? (r.result?.level_solved === true ? 'solved' : 'not solved') : `${String(levels ?? 0)} levels`
              return (
                <button key={r.label} type="button" onClick={() => setPicked({ kind: 'rollout', id: r.label })} title={role(r.label)} className={chip(isPicked('rollout', r.label))}>
                  <span className={cx('font-mono text-[12px]', isPicked('rollout', r.label) && 'text-accent')}>{r.label}{r.label === kept ? ' ★' : ''}</span>
                  <span className="text-[11px] text-muted">
                    {r.result || !perLevel ? outcome : 'playing'} ·{String(actions ?? 0)} actions{r.result || perLevel ? '' : ' · playing'}
                    {r.reused ? ` · same harness as ${r.reused}, not replayed` : ''}
                  </span>
                </button>
              )
            })}
          </div>
        ) : <div className="text-[12px] text-faint">No rollout has started yet.</div>}
        <div className="mt-2 text-[11.5px] text-muted">{perLevel
          ? 'base = starting harness · inv / dom = general and game-specific edits · agg = composed. A stage whose harness is unchanged or fell back reuses the rollout already played at this budget.'
          : 'base = starting harness · inv / dom = general and game-specific edits · agg = composed · final = fresh run of the adopted harness (the reported result).'}</div>
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
        <div className="mt-2 text-[11.5px] text-muted">INV writes general playing habits, DOM writes knowledge about this game, the composer merges what helped. A session that writes no edit falls back to the starting harness.</div>
      </Card>

      {Object.keys(edits).length > 0 && (
        <Card title="Harness edits · what each stage wrote">
          <div className="flex flex-col gap-2">
            {Object.entries(edits).map(([label, files]) => (
              <Collapsible key={label} title={<span className="font-mono text-[12.5px]">{label} <span className="text-faint">· {role(label)} · {Object.keys(files).length ? `${Object.keys(files).length} files` : 'empty (fell back to the base harness)'}</span></span>}>
                <StageFiles files={files} diffs={diffs[label] ?? {}} />
              </Collapsible>
            ))}
          </div>
        </Card>
      )}

      {shown && <BaselineDetail key={rolloutPath(shown)} runId={rolloutPath(shown)} live={live} notes={false} />}
      {current?.kind === 'coach' && <CoachTimeline key={current.id} runId={runId} session={coach.find((s) => s.id === current.id)} live={live} />}
    </div>
  )
}

function CoachTimeline({ runId, session, live }: { runId: string; session?: CoachSession; live?: boolean }) {
  const events = useQuery({
    queryKey: ['coach-session', runId, session?.id],
    enabled: Boolean(session),
    queryFn: ({ signal }) => api.get<{ agent_events: { total: number; events: AgentEvent[] }; prompts?: SessionPrompts }>(`/harness2/session${q({ run: runId, session: session!.id })}`, signal),
    refetchInterval: live && !session?.finished ? 5000 : false,
    placeholderData: keepPreviousData,
  })
  const items = useMemo(() => {
    const data = events.data?.agent_events
    if (!data) return []
    const first = data.total - data.events.length
    return withPrompts(data.events.map((event, i) => fromAgentEvent(event, first + i)), events.data?.prompts, `coach-${session?.id}`)
  }, [events.data, session?.id])
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
        <>
          <div className="mb-2 text-[11.5px] text-muted">The coach gets its mission (first item below) and one fixed instruction, "Read MISSION.md first. Do what it asks. Edit context/harness/ in place…", which the run does not record. File edits show what it changed.</div>
          <Timeline items={items} pinned={(item) => keys.has(pinKey(item, context))} onPin={togglePin} emptyText="No events yet" />
        </>
      )}
    </Card>
  )
}

/** One stage's harness: each file's changes against the starting harness, or the whole file on request. */
function StageFiles({ files, diffs }: { files: Record<string, string>; diffs: Record<string, string> }) {
  const [whole, setWhole] = useState<Set<string>>(new Set())
  return (
    <div className="flex flex-col gap-3">
      {Object.entries(files).map(([name, text]) => {
        const diff = diffs[name]
        const showWhole = whole.has(name) || !diff
        return (
          <div key={name} className="flex flex-col gap-1">
            <div className="flex items-center gap-2 font-mono text-[11.5px] text-muted">
              {name}
              {diff && (
                <button type="button" className="text-[11px] text-link hover:underline"
                  onClick={() => setWhole((w) => { const n = new Set(w); if (n.has(name)) n.delete(name); else n.add(name); return n })}>
                  {showWhole ? 'show changes' : 'show whole file'}
                </button>
              )}
              {!diff && <span className="text-faint">· same as the starting harness</span>}
            </div>
            {showWhole ? <Pre>{text}</Pre> : <DiffView diff={diff} />}
          </div>
        )
      })}
    </div>
  )
}
