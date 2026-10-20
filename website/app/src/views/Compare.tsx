import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { JobComparison } from '../api/types'
import { LineChart, MAX_SERIES, seriesColor, type Series } from '../components/LineChart'
import { GameThumb, HarnessChip, RunId } from '../components/identity'
import { OutcomeCell, ProcessPill } from '../components/status'
import { Button, Card, Empty, ErrorBox, Input, Loading, Notice, PageHeader, Pill, Select, cx } from '../components/ui'
import { bestSoFar, firstSuccess, levelCurve } from '../lib/compare'
import { dateTime, duration, gameName, shortId } from '../lib/format'
import { distinct, jobLabel, runHref, unitLabel, type RunView } from '../lib/runs'

const shortLabel = (r: RunView) => `${r.model.split('/').at(-1)} · ${r.effort}`
const seriesLabel = (r: RunView) => `${r.variant} · ${r.harness} · ${r.model.split('/').at(-1)} · ${r.effort}${r.worldModel && r.worldModel !== 'not-recorded' ? ` · ${r.worldModel}` : ''}`

export function CompareView() {
  const [params, setParams] = useSearchParams()
  const job = params.get('job') ?? ''
  const ids = params.getAll('run')
  const catalog = useCatalog(10_000)
  const byId = useMemo(() => new Map(catalog.views.map((r) => [r.id, r])), [catalog.views])
  const chosen = job ? catalog.views.filter((r) => r.batch === job) : ids.map((id) => byId.get(id)).filter((r): r is RunView => Boolean(r))
  const jobRecord = catalog.data?.jobs.find((j) => j.id === job)

  const setRuns = (next: string[]) => {
    const search = new URLSearchParams()
    next.forEach((id) => search.append('run', id))
    setParams(search)
  }

  if (catalog.isLoading) return <Loading label="Reading the run catalog…" />
  if (catalog.error) return <ErrorBox error={catalog.error} retry={() => catalog.refetch()} />
  const picking = !job && chosen.length < 2
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Compare"
        subtitle={job ? <>Launch <span className="font-mono">{jobLabel({ id: job })}</span>{jobRecord ? ` · ${dateTime(jobRecord.created_at)}` : ''}</> : 'Outcome curves for selected runs. Descriptive, not a significance test.'}
        actions={job ? <Button onClick={() => setRuns(chosen.map((r) => r.id))}>Edit as a selection</Button> : undefined}
      />
      {picking ? (
        <Picker runs={catalog.views} selected={ids} onChange={setRuns} />
      ) : (
        <>
          {!job && <SelectionBar runs={chosen} onRemove={(id) => setRuns(ids.filter((x) => x !== id))} onEdit={() => setParams(new URLSearchParams([...ids.map((id) => ['run', id]), ['pick', '1']]))} />}
          {ids.length > chosen.length && !job && <Notice tone="warn">{ids.length - chosen.length} selected runs are not in the current catalog.</Notice>}
          {params.get('pick') ? <Picker runs={catalog.views} selected={ids} onChange={setRuns} /> : <Comparison runs={chosen} job={jobRecord?.comparison ? job : ''} />}
        </>
      )}
    </div>
  )
}

function SelectionBar({ runs, onRemove, onEdit }: { runs: RunView[]; onRemove: (id: string) => void; onEdit: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {runs.map((r, i) => (
        <span key={r.id} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-0.5 text-[12px]">
          {i < MAX_SERIES && <span className="inline-block h-2 w-2 rounded-full" style={{ background: seriesColor(i) }} />}
          <Link to={runHref(r.id)}>{shortId(r.id, 2)}</Link>
          <button type="button" onClick={() => onRemove(r.id)} className="text-faint hover:text-fg" aria-label="Remove">×</button>
        </span>
      ))}
      <Button size="sm" variant="ghost" onClick={onEdit}>Add runs…</Button>
    </div>
  )
}

function Picker({ runs, selected, onChange }: { runs: RunView[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const [game, setGame] = useState(runs.find((r) => selected.includes(r.id))?.game ?? '')
  const [variant, setVariant] = useState('')
  const [search, setSearch] = useState('')
  const set = new Set(selected)
  const needle = search.toLowerCase()
  const shown = runs.filter((r) => (!game || r.game === game) && (!variant || r.variant === variant) && (!needle || `${r.id} ${r.model} ${r.harness}`.toLowerCase().includes(needle)) && r.raw.has_result !== undefined)
  return (
    <Card title={`Pick at least two runs (${selected.length} selected)`} actions={selected.length >= 2 && <Button variant="primary" size="sm" onClick={() => onChange(selected)}>Compare {selected.length}</Button>}>
      <div className="mb-2 flex flex-wrap gap-2">
        <Select value={game} onChange={(e) => setGame(e.target.value)}>
          <option value="">Any game</option>
          {distinct(runs, (r) => r.game).map((g) => <option key={g} value={g}>{gameName(g)}</option>)}
        </Select>
        <Select value={variant} onChange={(e) => setVariant(e.target.value)}>
          <option value="">Any framework</option>
          {distinct(runs, (r) => r.variant).map((v) => <option key={v} value={v}>{v}</option>)}
        </Select>
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by id, model, harness…" className="w-64" />
      </div>
      <div className="max-h-[60vh] overflow-auto rounded border border-line">
        {shown.length ? (
          <table className="data-table">
            <thead><tr><th /><th>Outcome</th><th>Framework</th><th>Harness</th><th>Model</th><th>Game</th><th>Launched</th><th>Run</th></tr></thead>
            <tbody>
              {shown.slice(0, 300).map((r) => (
                <tr key={r.id} className={cx(set.has(r.id) && 'selected')} style={{ cursor: 'pointer' }} onClick={() => onChange(set.has(r.id) ? selected.filter((x) => x !== r.id) : [...selected, r.id])}>
                  <td><input type="checkbox" readOnly checked={set.has(r.id)} /></td>
                  <td><OutcomeCell outcome={r.outcome} campaign={r.kind === 'avo'} /></td>
                  <td>{r.variant}</td>
                  <td><HarnessChip harness={r.harness} legacy={r.legacy} /></td>
                  <td className="max-w-64 truncate">{r.model} <span className="text-faint">· {r.effort}</span></td>
                  <td>{gameName(r.game)}</td>
                  <td className="text-[12px] text-muted">{dateTime(r.started)}</td>
                  <td className="font-mono text-[11.5px]">{shortId(r.id, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty title="No runs match" />}
      </div>
    </Card>
  )
}

function Comparison({ runs, job }: { runs: RunView[]; job: string }) {
  const campaigns = runs.filter((r) => r.kind === 'avo')
  const baselines = runs.filter((r) => r.kind !== 'avo')
  const transitions = useQueries({
    queries: baselines.map((r) => ({
      queryKey: ['transitions', r.id, r.activity],
      queryFn: ({ signal }: { signal: AbortSignal }) => api.text(`/api/workbench/record/file${q({ run: r.id, file: 'transitions.jsonl' })}`, signal).then(levelCurve),
      staleTime: 60_000,
      retry: false,
    })),
  })
  const pairs = useQuery({
    queryKey: ['comparison', job],
    enabled: Boolean(job),
    queryFn: ({ signal }) => api.get<JobComparison>(`/comparison${q({ job })}`, signal),
  })
  if (!runs.length) return <Empty title="No runs in this selection" />
  // Colors follow each run's position in the full selection so both charts and the table agree.
  const index = new Map(runs.map((r, i) => [r.id, i]))
  const campaignSeries: Series[] = campaigns.map((r) => ({ id: r.id, label: seriesLabel(r), points: bestSoFar(r.raw.result_inputs?.evaluations ?? []), target: r.outcome.total, color: index.get(r.id), short: shortLabel(r) }))
  const baselineSeries: Series[] = baselines.map((r, i) => ({ id: r.id, label: seriesLabel(r), points: transitions[i]?.data?.points ?? [], target: transitions[i]?.data?.total ?? r.outcome.total, color: index.get(r.id), short: shortLabel(r) }))
  const mixedGames = new Set(runs.map((r) => r.game)).size > 1
  return (
    <div className="flex flex-col gap-4">
      {mixedGames && <Notice tone="warn">These runs cover different games; levels are not directly comparable across games.</Notice>}
      <Card title="Summary" bodyClass="p-0">
        <div className="overflow-auto">
          <table className="data-table">
            <thead>
              <tr><th /><th>Game · run</th><th>Framework</th><th>Harness</th><th>Model · effort</th><th>Outcome</th><th>Process</th><th>Used</th><th>First solve</th><th>Search time</th></tr>
            </thead>
            <tbody>
              {runs.map((r, i) => {
                const evaluations = r.raw.result_inputs?.evaluations ?? []
                const first = r.kind === 'avo' ? firstSuccess(evaluations) : null
                const firstEval = first ? evaluations[first - 1] : null
                const lastEval = evaluations.at(-1)
                return (
                  <tr key={r.id}>
                    <td>{i < MAX_SERIES && <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: seriesColor(i) }} />}</td>
                    <td><div className="flex items-center gap-2.5"><GameThumb gameId={r.game} size={28} /><div className="min-w-0"><Link to={runHref(r.id)} className="block text-[13px] font-semibold">{gameName(r.game)}</Link><RunId id={r.id} className="w-44" /></div></div></td>
                    <td>{r.variant}{r.worldModel && r.worldModel !== 'not-recorded' && <div className="text-[11px] text-faint">{r.worldModel}</div>}</td>
                    <td><HarnessChip harness={r.harness} legacy={r.legacy} /></td>
                    <td className="max-w-64 truncate">{r.model} <span className="text-faint">· {r.effort}</span></td>
                    <td><OutcomeCell outcome={r.outcome} campaign={r.kind === 'avo'} /></td>
                    <td><ProcessPill status={r.process} /></td>
                    <td className="whitespace-nowrap text-[12.5px] tabular-nums text-muted">{r.progress.used ?? '—'}{r.progress.budget ? ` / ${r.progress.budget}` : ''} {unitLabel(r.progress.unit, true)}</td>
                    <td className="text-[12px]">{r.kind === 'avo' ? (first ? `eval ${first}` : '—') : r.outcome.tone === 'solved' ? `${r.progress.used ?? '—'} act` : '—'}</td>
                    <td className="text-[12px] text-muted">{r.kind === 'avo' ? duration(firstEval?.score.search_session_elapsed_seconds ?? lastEval?.score.search_session_elapsed_seconds) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
      {campaigns.length > 0 && (
        <Card title="AVO · best fresh-solver fitness by completed evaluation">
          <LineChart series={campaignSeries} xDomain={Math.max(0, ...campaigns.map((r) => r.progress.budget ?? 0))} xLabel="Evaluation" yLabel="Levels (fitness)" />
        </Card>
      )}
      {baselines.length > 0 && (
        <Card title="Direct play · levels completed by action" actions={transitions.some((t) => t.isLoading) && <span className="text-[11.5px] text-muted">loading transitions…</span>}>
          {transitions.some((t) => t.error) && <div className="mb-2"><Notice tone="warn">Some runs have no transitions.jsonl (older runs); their curves are empty.</Notice></div>}
          <LineChart series={baselineSeries} xLabel="Action" yLabel="Levels completed" />
        </Card>
      )}
      {job && (
        <Card title="Matched world-model pairs">
          {pairs.isLoading ? <Loading /> : pairs.error ? <ErrorBox error={pairs.error} /> : pairs.data && (
            <table className="data-table">
              <thead><tr><th>Pair</th><th>Game</th><th>Model</th><th>Final only</th><th>Between hypotheses</th></tr></thead>
              <tbody>
                {pairs.data.pairs.map((p) => (
                  <tr key={p.id}>
                    <td className="font-mono text-[12px]">{p.id} · #{p.repeat}</td>
                    <td>{gameName(p.game_id)}</td>
                    <td>{p.model} <span className="text-faint">· {p.effort}</span></td>
                    {(['final-only', 'between-hypotheses'] as const).map((m) => {
                      const r = p.runs[m]
                      return (
                        <td key={m}>
                          {r ? (
                            <Link to={runHref(r.id)} className="inline-flex items-center gap-1.5 text-fg">
                              <span className="font-mono text-[12px]">{r.best_fitness ?? '—'}</span>
                              {r.solved ? <Pill tone="solved">solved{r.first_success_evaluation ? ` @${r.first_success_evaluation}` : ''}</Pill> : <span className="text-[11.5px] text-muted">{r.evaluated} evals</span>}
                              {!r.finalized && <span className="text-[11px] text-faint">provisional</span>}
                            </Link>
                          ) : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  )
}
