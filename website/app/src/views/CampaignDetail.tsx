import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api, q } from '../api/client'
import type { AvoArtifact, AvoFrame, AvoLogs, AvoSnapshot, Submission } from '../api/types'
import { GridCanvas, PixelImage, toGrid } from '../components/Frame'
import { Markdown } from '../components/Markdown'
import { Timeline } from '../components/Timeline'
import { Button, Card, Empty, ErrorBox, Input, Loading, Notice, Pill, Pre, Select, Tabs, cx } from '../components/ui'
import { fromAvoLog } from '../lib/events'
import { bytes, dateTime, duration } from '../lib/format'

type Tab = 'trace' | 'solver' | 'artifacts'
type Phase = 'research' | 'evaluation'
const STREAMS: [string, string][] = [['session', 'Conversation + tools'], ['reasoning', 'Reasoning'], ['environment', 'Environment'], ['workspace', 'Workspace'], ['all', 'Everything']]

/** AVO campaigns: lineage, fresh evaluations, frame replay, optimizer/player traces, solver and world model. */
export function CampaignDetail({ runId, live }: { runId: string; live?: boolean }) {
  const snapshot = useQuery({
    queryKey: ['avo-run', runId],
    queryFn: ({ signal }) => api.get<AvoSnapshot>(`/avo/run${q({ run: runId })}`, signal),
    refetchInterval: live ? 5000 : false,
    placeholderData: keepPreviousData,
  })
  const [candidate, setCandidate] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('trace')
  const data = snapshot.data
  const selected = candidate ?? data?.current ?? data?.candidates.at(-1)?.candidate_id ?? null

  if (snapshot.isLoading) return <Loading label="Reading campaign…" />
  if (snapshot.error) return <ErrorBox error={snapshot.error} retry={() => snapshot.refetch()} />
  if (!data) return null
  const best = data.candidates.filter((c) => c.fitness !== null).sort((a, b) => (b.fitness ?? 0) - (a.fitness ?? 0))[0]
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Phase" value={data.phase.replaceAll('_', ' ')} sub={data.finalized ? 'campaign finalized' : data.active ? 'process running' : 'not running'} />
        <Stat label="Hypotheses evaluated" value={`${data.hypotheses_evaluated} / ${data.max_hypotheses ?? '—'}`} sub={`${data.hypotheses_registered} registered`} />
        <Stat label="Best fresh fitness" value={best ? `${best.fitness} / ${best.win_levels ?? data.win_levels ?? '—'}` : '—'} sub={best ? `${best.candidate_id}${best.success ? ' · solved' : ''}` : 'no evaluation yet'} />
        <Stat label="Research actions (current)" value={`${data.research.actions} / ${data.research.budget ?? '—'}`} sub={`level ${data.research.levels}`} />
        <Stat label="Fresh evaluation (current)" value={`${data.fresh_evaluation.actions} / ${data.fresh_evaluation.budget ?? '—'}`} sub={`level ${data.fresh_evaluation.levels}`} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card title="Lineage" bodyClass="p-0" actions={<span className="text-[11.5px] text-muted">last activity {dateTime(data.last_activity)}</span>}>
          {data.candidates.length ? (
            <div className="max-h-[420px] overflow-auto">
              <table className="data-table">
                <thead><tr><th>Hypothesis</th><th>Parents</th><th>Fresh fitness</th><th>Research</th><th>Evaluation</th></tr></thead>
                <tbody>
                  {data.candidates.map((c) => (
                    <tr key={c.candidate_id} className={cx(c.candidate_id === selected && 'selected')} style={{ cursor: 'pointer' }} onClick={() => setCandidate(c.candidate_id)}>
                      <td className="font-mono text-[12px]">{c.candidate_id}{c.candidate_id === data.current && <span className="ml-1 text-[11px] text-accent">current</span>}</td>
                      <td className="font-mono text-[11.5px] text-muted">{c.parent_ids.join(', ') || 'seed'}</td>
                      <td>
                        {c.evaluated ? (
                          <span className="inline-flex items-center gap-1.5"><span className="font-mono text-[12px]">{c.fitness ?? '—'} / {c.win_levels ?? '—'}</span>{c.success && <Pill tone="solved">solved</Pill>}</span>
                        ) : <span className="text-[12px] text-faint">not evaluated</span>}
                      </td>
                      <td className="font-mono text-[12px] text-muted">{c.research.actions} act · L{c.research.levels}</td>
                      <td className="font-mono text-[12px] text-muted">{c.evaluation.actions} act · L{c.evaluation.levels}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty title="No hypothesis registered yet" />}
        </Card>
        {selected ? <FrameReplay runId={runId} snapshot={data} candidate={selected} live={live} /> : <Card title="Replay"><Empty title="Nothing to replay yet" /></Card>}
      </div>

      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'trace', label: 'Agent timeline' }, { id: 'solver', label: 'Solver & world model' }, { id: 'artifacts', label: 'Artifacts' }]} />
      {tab === 'trace' && <Trace runId={runId} candidates={data.candidates.map((c) => c.candidate_id)} defaultScope="outer" live={live} />}
      {tab === 'solver' && <SolverPanel runId={runId} />}
      {tab === 'artifacts' && <Artifacts runId={runId} />}
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2">
      <div className="text-[11px] text-faint">{label}</div>
      <div className="font-mono text-[15px] font-semibold tabular-nums">{value}</div>
      {sub && <div className="truncate text-[11.5px] text-muted">{sub}</div>}
    </div>
  )
}

function FrameReplay({ runId, snapshot, candidate, live }: { runId: string; snapshot: AvoSnapshot; candidate: string; live?: boolean }) {
  const entry = snapshot.candidates.find((c) => c.candidate_id === candidate)
  const [phase, setPhase] = useState<Phase>('evaluation')
  const [step, setStep] = useState<number | null>(null)
  useEffect(() => { setStep(null); setPhase(entry && entry.evaluation.actions ? 'evaluation' : 'research') }, [candidate]) // eslint-disable-line react-hooks/exhaustive-deps
  const total = entry ? entry[phase].actions : 0
  const revision = entry ? entry[phase].revision : 0
  const frame = useQuery({
    queryKey: ['avo-frame', runId, candidate, phase, step, step === null ? revision : 0],
    enabled: total > 0,
    queryFn: ({ signal }) => api.get<AvoFrame>(`/avo/frame${q({ run: runId, candidate, phase, step: step ?? undefined })}`, signal),
    placeholderData: keepPreviousData,
    staleTime: step === null ? 0 : Infinity,
  })
  const position = step ?? frame.data?.total_actions ?? total
  const max = frame.data?.total_actions ?? total
  const progress = frame.data?.transition?.progress
  return (
    <Card
      title={`Replay · ${candidate}`}
      actions={
        <div className="flex items-center gap-1.5">
          <Select value={phase} onChange={(e) => { setPhase(e.target.value as Phase); setStep(null) }} className="h-6 text-[12px]">
            <option value="evaluation" disabled={!entry?.evaluation.actions}>Fresh evaluation ({entry?.evaluation.actions ?? 0})</option>
            <option value="research" disabled={!entry?.research.actions}>Research ({entry?.research.actions ?? 0})</option>
          </Select>
        </div>
      }
    >
      {!total ? <Empty title={`No ${phase === 'evaluation' ? 'fresh-evaluation' : 'research'} actions saved for ${candidate}`} /> : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5">
            <Button size="sm" onClick={() => setStep(0)} disabled={position <= 0}>Initial</Button>
            <Button size="sm" onClick={() => setStep(Math.max(0, position - 1))} disabled={position <= 0}>← Prev</Button>
            <span className="w-24 text-center font-mono text-[12px] tabular-nums">{position} / {max}</span>
            <Button size="sm" onClick={() => setStep(position + 1 >= max ? null : position + 1)} disabled={position >= max}>Next →</Button>
            <Button size="sm" variant={step === null ? 'primary' : 'default'} onClick={() => setStep(null)}>{live ? 'Follow live' : 'Latest'}</Button>
          </div>
          <input type="range" min={0} max={max} value={position} onChange={(e) => { const v = Number(e.target.value); setStep(v >= max ? null : v) }} className="w-full accent-[var(--accent)]" />
          {frame.error ? <ErrorBox error={frame.error} /> : frame.isLoading ? <Loading label="Rendering frame…" /> : frame.data && (
            <div className="flex flex-wrap gap-4">
              {frame.data.rendered_frame?.data_url ? (
                <PixelImage src={frame.data.rendered_frame.data_url} alt="Saved frame" className="max-h-[300px] w-auto" />
              ) : (
                <GridCanvas grid={toGrid(frame.data.fallback_frame)} maxSize={340} />
              )}
              <div className="flex min-w-48 flex-1 flex-col gap-1 text-[12.5px]">
                <div><span className="text-muted">Action</span> <span className="font-mono">{frame.data.transition?.action?.id ?? (position === 0 ? 'initial state' : '—')}</span></div>
                <div><span className="text-muted">State</span> {frame.data.transition?.status || '—'}</div>
                <div><span className="text-muted">Levels</span> {progress?.levels_completed ?? '—'} / {progress?.win_levels ?? '—'}</div>
                <div className="text-[11px] text-faint">Source: {frame.data.source.replaceAll('_', ' ')}{frame.data.replay_exact ? '' : ' · replay differs from saved grid'}</div>
                {frame.data.reasoning?.status === 'captured' && frame.data.reasoning.text && (
                  <div className="mt-1">
                    <div className="text-[11px] text-faint">Player reasoning at this action</div>
                    <div className="max-h-40 overflow-auto rounded-md bg-sunken p-2 text-[12px] whitespace-pre-wrap">{frame.data.reasoning.text}</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function Trace({ runId, candidates, defaultScope, live }: { runId: string; candidates: string[]; defaultScope: string; live?: boolean }) {
  const [scope, setScope] = useState(defaultScope)
  const [stream, setStream] = useState('session')
  const [pages, setPages] = useState(1)
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  useEffect(() => setPages(1), [scope, stream, applied])
  const logs = useQuery({
    queryKey: ['avo-logs', runId, scope, stream, pages, applied],
    queryFn: async ({ signal }) => {
      // Page 0 is the newest; load `pages` pages and concatenate oldest first.
      const results = await Promise.all(Array.from({ length: pages }, (_, page) =>
        api.get<AvoLogs>(`/avo/logs${q({ run: runId, scope, stream, page, limit: 120, search: applied })}`, signal)))
      return { total: results[0]?.total ?? 0, hasMore: results.at(-1)?.has_more ?? false, entries: results.reverse().flatMap((r) => r.entries) }
    },
    refetchInterval: live && pages === 1 ? 8000 : false,
    placeholderData: keepPreviousData,
  })
  const items = useMemo(() => (logs.data?.entries ?? []).map(fromAvoLog), [logs.data])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="outer">Outer optimizer</option>
          {candidates.map((c) => <option key={c} value={c}>{c} · inner player</option>)}
        </Select>
        <div className="flex gap-1">
          {STREAMS.map(([id, label]) => (
            <Button key={id} size="sm" variant={stream === id ? 'primary' : 'default'} onClick={() => setStream(id)}>{label}</Button>
          ))}
        </div>
        <form className="ml-auto flex gap-1" onSubmit={(e) => { e.preventDefault(); setApplied(search) }}>
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Server-side search…" className="h-7 w-52" />
          <Button size="sm" type="submit">Search</Button>
        </form>
      </div>
      {logs.isLoading ? <Loading label="Reading trace…" /> : logs.error ? <ErrorBox error={logs.error} /> : (
        <>
          {logs.data?.hasMore && (
            <div className="flex items-center justify-between text-[12px] text-muted">
              Showing the newest {items.length} of {logs.data.total} entries.
              <Button size="sm" onClick={() => setPages(pages + 1)} disabled={logs.isFetching}>Load older</Button>
            </div>
          )}
          <Timeline items={items} emptyText={scope === 'outer' ? 'No optimizer trace saved' : `No trace saved for ${scope}`} />
        </>
      )}
    </div>
  )
}

function SolverPanel({ runId }: { runId: string }) {
  const [candidate, setCandidate] = useState('')
  const record = useQuery({
    queryKey: ['submission', runId, candidate],
    queryFn: ({ signal }) => api.get<Submission>(`/submission${q({ run: runId, candidate })}`, signal),
  })
  const [file, setFile] = useState<string | null>(null)
  const data = record.data
  const solver = data?.files.find((f) => f.name === 'solver.py')
  const shown = file ?? solver?.path ?? null
  useEffect(() => setFile(null), [candidate])
  const content = useQuery({
    queryKey: ['submission-file', runId, shown],
    enabled: Boolean(shown),
    queryFn: ({ signal }) => api.text(`/submission/file${q({ run: runId, file: shown! })}`, signal),
  })
  const worldModel = useQuery({
    queryKey: ['world-model', runId],
    enabled: Boolean(data?.world_model),
    queryFn: ({ signal }) => api.text(`/submission/file${q({ run: runId, file: 'world_model.md' })}`, signal),
  })
  if (record.isLoading) return <Loading label="Reading evaluated submission…" />
  if (record.error) return <ErrorBox error={record.error} />
  if (!data) return null
  const reconstructed = data.world_model_record?.provenance === 'reconstructed_from_saved_outer_history'
  return (
    <div className="flex flex-col gap-3">
      <Card
        title={data.selection === 'candidate' ? `Evaluated solver · ${data.best?.candidate_id}` : 'Best evaluated solver'}
        actions={solver && <a href={`/api/workbench/submission/download${q({ run: runId, candidate: data.best?.candidate_id ?? '' })}`}><Button size="sm">Download submission .zip</Button></a>}
      >
        <div className="mb-2 text-[12px] text-muted">
          {data.best
            ? `${data.best.candidate_id} · fresh fitness ${data.best.fitness} · ${data.best.success ? 'solved' : 'not solved'} · ${data.best.environment_steps ?? '—'} evaluation actions · ${data.best.finish_reason ?? ''}`
            : 'No completed evaluation yet.'}
          {data.evaluations_to_success ? ` · first solved at evaluation ${data.evaluations_to_success}${data.seconds_to_success == null ? '' : ` after ${duration(data.seconds_to_success)} of search`}` : ''}
        </div>
        {data.evaluations.length > 0 && (
          <div className="mb-3 max-h-48 overflow-auto rounded border border-line">
            <table className="data-table">
              <thead><tr><th>Candidate</th><th>Fitness</th><th>Actions</th><th>Outcome</th><th>Finish reason</th></tr></thead>
              <tbody>
                {data.evaluations.map((e) => (
                  <tr key={e.candidate_id} className={cx(e.candidate_id === data.best?.candidate_id && 'selected')} style={{ cursor: 'pointer' }} onClick={() => setCandidate(e.candidate_id ?? '')}>
                    <td className="font-mono text-[12px]">{e.candidate_id}</td>
                    <td className="font-mono text-[12px]">{e.fitness}</td>
                    <td className="text-muted">{e.environment_steps ?? '—'}</td>
                    <td>{e.success ? <Pill tone="solved">solved</Pill> : <span className="text-[12px] text-muted">not solved</span>}</td>
                    <td className="max-w-80 truncate text-[12px] text-muted" title={e.finish_reason ?? ''}>{e.finish_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data.files.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[200px_minmax(0,1fr)]">
            <div className="flex flex-col gap-0.5">
              {data.files.map((f) => (
                <button key={f.path} type="button" onClick={() => setFile(f.path)} className={cx('flex justify-between gap-2 truncate rounded px-2 py-1 text-left font-mono text-[11.5px]', f.path === shown ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-sunken')}>
                  <span className="truncate">{f.name}</span><span className="text-faint">{bytes(f.size)}</span>
                </button>
              ))}
            </div>
            {content.isLoading ? <Loading /> : content.error ? <ErrorBox error={content.error} /> : <Pre className="max-h-[560px]">{content.data}</Pre>}
          </div>
        ) : <Empty title="No evaluated solver files saved" />}
      </Card>
      <Card title="World model (final outer report)" actions={<span className="text-[11.5px] text-muted">condition: {data.mode === 'not-recorded' ? 'not recorded (older campaign)' : data.mode}</span>}>
        {reconstructed && <div className="mb-2"><Notice tone="warn">Reconstructed after the run from saved outer history; not a measurement of the original session's final beliefs.</Notice></div>}
        {!data.world_model ? <Empty title="No final world model saved">A time limit or infrastructure failure can leave it missing.</Empty>
          : worldModel.isLoading ? <Loading /> : worldModel.error ? <ErrorBox error={worldModel.error} /> : <Markdown>{worldModel.data ?? ''}</Markdown>}
      </Card>
    </div>
  )
}

function Artifacts({ runId }: { runId: string }) {
  const list = useQuery({ queryKey: ['avo-artifacts', runId], queryFn: ({ signal }) => api.get<{ artifacts: AvoArtifact[] }>(`/avo/artifacts${q({ run: runId })}`, signal) })
  const [path, setPath] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const content = useQuery({
    queryKey: ['avo-artifact', runId, path],
    enabled: Boolean(path),
    queryFn: ({ signal }) => api.get<{ content: string; truncated: boolean; size: number }>(`/avo/artifact${q({ run: runId, path: path! })}`, signal),
  })
  if (list.isLoading) return <Loading label="Listing artifacts…" />
  if (list.error) return <ErrorBox error={list.error} />
  const needle = filter.toLowerCase()
  const artifacts = (list.data?.artifacts ?? []).filter((a) => !needle || a.path.toLowerCase().includes(needle))
  if (!list.data?.artifacts.length) return <Empty title="No readable artifacts" />
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[340px_minmax(0,1fr)]">
      <div className="flex flex-col gap-2">
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={`Filter ${list.data.artifacts.length} files…`} />
        <div className="max-h-[560px] overflow-auto rounded-md border border-line">
          {artifacts.map((a) => (
            <button key={a.path} type="button" onClick={() => setPath(a.path)} className={cx('flex w-full justify-between gap-2 border-b border-line px-2 py-1 text-left last:border-b-0', a.path === path ? 'bg-accent-soft' : 'hover:bg-sunken')}>
              <span className="min-w-0 truncate font-mono text-[11.5px]" title={a.path}>{a.path}</span>
              <span className="shrink-0 text-[11px] text-faint">{bytes(a.size)}</span>
            </button>
          ))}
        </div>
      </div>
      <Card title={path ?? 'Select a file'}>
        {!path ? <Empty title="Select a file on the left" /> : content.isLoading ? <Loading /> : content.error ? <ErrorBox error={content.error} /> : content.data && (
          <>
            {content.data.truncated && <div className="mb-2"><Notice tone="warn">Showing the first 512 KB of {bytes(content.data.size)}.</Notice></div>}
            {path.endsWith('.md') ? <Markdown>{content.data.content}</Markdown> : <Pre className="max-h-[620px]">{prettyJson(path, content.data.content)}</Pre>}
          </>
        )}
      </Card>
    </div>
  )
}

function prettyJson(path: string, text: string): string {
  if (!path.endsWith('.json')) return text
  try { return JSON.stringify(JSON.parse(text), null, 2) } catch { return text }
}
