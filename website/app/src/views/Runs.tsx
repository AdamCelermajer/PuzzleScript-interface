import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob, ResumeResult } from '../api/types'
import { OutcomeCell, ProcessPill, ProgressText } from '../components/status'
import { Button, Empty, ErrorBox, Input, Loading, Notice, PageHeader, Pill, Select, cx } from '../components/ui'
import { dateTime, gameName, relativeTime, shortId, shortTime } from '../lib/format'
import { EMPTY_FILTERS, MODE_LABEL, distinct, modelParts, gameHref, jobLabel, matchesFilters, runHref, type RunFilters, type RunView } from '../lib/runs'
import { processStatus } from '../lib/status'

const STATUS_OPTIONS: [string, string][] = [
  ['', 'Any status'], ['active', 'Active (running or queued)'], ['running', 'Running'], ['queued', 'Queued'], ['paused', 'Paused'],
  ['finished', 'Finished'], ['stopped', 'Stopped'], ['failed', 'Failed'], ['attention', 'Needs assistance'], ['unconfirmed', 'Unconfirmed'],
  ['solved', 'Outcome: solved'],
]
const PAGE = 200

function useJobAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ action, job }: { action: 'stop' | 'pause' | 'dismiss' | 'resume'; job: string }) => api.post<Record<string, unknown>>(`/experiments/${action}${q({ job })}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['catalog'] }),
  })
}

export function RunsView() {
  const [params, setParams] = useSearchParams()
  const filters: RunFilters = { ...EMPTY_FILTERS, ...Object.fromEntries([...params.entries()].filter(([k]) => k in EMPTY_FILTERS)) }
  const catalog = useCatalog(5000)
  const navigate = useNavigate()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [limit, setLimit] = useState(PAGE)
  const client = useQueryClient()
  const jobAction = useJobAction()
  const resume = useMutation({
    mutationFn: (runId: string) => api.post<ResumeResult>('/runs/resume', { run_id: runId }),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['catalog'] })
      navigate(`/runs${q({ job: result.job_id })}`)
    },
  })

  const setFilter = (key: keyof RunFilters, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
    setLimit(PAGE)
  }

  const runs = catalog.views
  const visible = useMemo(() => runs.filter((r) => matchesFilters(r, filters)), [runs, params]) // eslint-disable-line react-hooks/exhaustive-deps
  const jobs = catalog.data?.jobs ?? []
  const jobById = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs])
  const options = useMemo(() => ({
    harness: distinct(runs, (r) => r.harness),
    model: distinct(runs, (r) => r.model),
    game: distinct(runs, (r) => r.game),
  }), [runs])
  const activeJobs = jobs
    .filter((j) => ['starting', 'running', 'stopping', 'paused'].includes(j.status) || (j.can_resume && !j.dismissed_from_runs_at && j.status === 'paused'))
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  const focusedJob = filters.job ? jobById.get(filters.job) : undefined
  const anyFilter = Object.values(filters).some(Boolean)
  const error = jobAction.error ?? resume.error

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Runs"
        subtitle={catalog.data ? `${runs.length} runs · ${jobs.length} launches · catalog checked ${relativeTime(catalog.data.checked_at * 1000)}` : 'Every mode and harness, live and finished'}
        actions={
          <>
            {selected.size >= 2 && (
              <Button onClick={() => navigate(`/compare?${[...selected].map((id) => `run=${encodeURIComponent(id)}`).join('&')}`)}>Compare {selected.size} runs</Button>
            )}
            {selected.size > 0 && <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear selection</Button>}
            <Link to="/launch"><Button variant="primary">New launch</Button></Link>
          </>
        }
      />

      {catalog.data?.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
      {error && <ErrorBox error={error} />}

      {focusedJob ? (
        <JobBanner job={focusedJob} busy={jobAction.isPending} onAction={(action) => confirmJob(action, focusedJob) && jobAction.mutate({ action, job: focusedJob.id })} onClear={() => setFilter('job', '')} />
      ) : (
        activeJobs.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <div className="text-[12px] font-medium text-muted">Active launches</div>
            {activeJobs.map((job) => (
              <JobBanner key={job.id} job={job} compact busy={jobAction.isPending} onOpen={() => setFilter('job', job.id)} onAction={(action) => confirmJob(action, job) && jobAction.mutate({ action, job: job.id })} />
            ))}
          </div>
        )
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Input placeholder="Filter by id, game, model…" value={filters.q} onChange={(e) => setFilter('q', e.target.value)} className="w-56" />
        <Select value={filters.mode} onChange={(e) => setFilter('mode', e.target.value)}>
          <option value="">Any mode</option>
          {Object.entries(MODE_LABEL).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </Select>
        <Select value={filters.harness} onChange={(e) => setFilter('harness', e.target.value)}>
          <option value="">Any harness</option>
          {options.harness.map((h) => <option key={h} value={h}>{h}</option>)}
        </Select>
        <Select value={filters.model} onChange={(e) => setFilter('model', e.target.value)} className="max-w-56">
          <option value="">Any model</option>
          {options.model.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
        <Select value={filters.game} onChange={(e) => setFilter('game', e.target.value)} className="max-w-48">
          <option value="">Any game</option>
          {options.game.map((g) => <option key={g} value={g}>{gameName(g)}</option>)}
        </Select>
        <Select value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
          {STATUS_OPTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </Select>
        {anyFilter && <Button variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Reset filters</Button>}
        <span className="ml-auto text-[12px] text-muted">{visible.length} shown</span>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-panel">
        {catalog.isLoading ? (
          <Loading label="Reading the run catalog…" />
        ) : catalog.error ? (
          <div className="p-3"><ErrorBox error={catalog.error} retry={() => catalog.refetch()} /></div>
        ) : !visible.length ? (
          <Empty title={runs.length ? 'No runs match these filters' : 'No runs yet'}>
            {runs.length ? 'Loosen a filter or reset them.' : <Link to="/launch">Launch the first run.</Link>}
          </Empty>
        ) : (
          <div className="max-h-[calc(100vh-260px)] overflow-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-6"><span className="sr-only">Select</span></th>
                  <th>Process</th>
                  <th>Outcome</th>
                  <th>Mode</th>
                  <th>Harness</th>
                  <th>Model · effort</th>
                  <th>Game</th>
                  <th>Progress</th>
                  <th>Launched</th>
                  <th>Run</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.slice(0, limit).map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    selected={selected.has(run.id)}
                    onSelect={(on) => setSelected((s) => { const n = new Set(s); if (on) n.add(run.id); else n.delete(run.id); return n })}
                    onResume={() => window.confirm(`Resume ${shortId(run.id, 3)} in a new batch? This starts paid model calls.`) && resume.mutate(run.id)}
                    resuming={resume.isPending && resume.variables === run.id}
                    onJob={() => setFilter('job', run.batch)}
                  />
                ))}
              </tbody>
            </table>
            {visible.length > limit && (
              <div className="flex justify-center border-t border-line p-2">
                <Button variant="ghost" onClick={() => setLimit(limit + PAGE)}>Show {Math.min(PAGE, visible.length - limit)} more</Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function confirmJob(action: string, job: CatalogJob): boolean {
  const name = jobLabel(job)
  if (action === 'stop') return window.confirm(`Stop batch ${name}? Queued runs are cancelled and owned containers stopped.`)
  if (action === 'dismiss') return window.confirm(`Remove ${name} from the active list? Artifacts and results are kept.`)
  if (action === 'resume') return window.confirm(`Resume batch ${name}? This starts paid model calls.`)
  return true
}

function JobBanner({ job, compact, busy, onAction, onOpen, onClear }: {
  job: CatalogJob
  compact?: boolean
  busy: boolean
  onAction: (action: 'stop' | 'pause' | 'dismiss' | 'resume') => void
  onOpen?: () => void
  onClear?: () => void
}) {
  const status = processStatus({ status: job.status, status_source: job.status_source ?? (job.can_stop ? 'Batch worker heartbeat' : ''), needs_assistance: job.needs_assistance })
  const counts = job.runs.reduce<Record<string, number>>((acc, r) => { const s = r.status ?? 'queued'; acc[s] = (acc[s] ?? 0) + 1; return acc }, {})
  return (
    <div className={cx('flex flex-wrap items-center gap-3 rounded-lg border border-line bg-panel px-3', compact ? 'py-1.5' : 'py-2.5')}>
      <ProcessPill status={status} />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {onOpen ? <button type="button" onClick={onOpen} className="truncate font-medium text-accent hover:underline">{jobLabel(job)}</button> : <span className="truncate font-medium">{jobLabel(job)}</span>}
          {job.comparison && <Pill tone="accent">paired comparison</Pill>}
          {job.recovery_of && <Pill tone="neutral">recovery</Pill>}
        </div>
        <div className="text-[11.5px] text-muted">
          {dateTime(job.created_at)} · {job.runs.length} runs · {Object.entries(counts).map(([s, n]) => `${n} ${s === 'cancelled' ? 'stopped' : s}`).join(', ')}
          {job.parallel ? ` · ${job.parallel} at once` : ''}
          {job.error ? ` · ${job.error}` : ''}
        </div>
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        {!compact && job.comparison && <Link to={`/compare?job=${encodeURIComponent(job.id)}`}><Button size="sm">Compare pairs</Button></Link>}
        {job.can_pause && <Button size="sm" disabled={busy} onClick={() => onAction('pause')}>Pause</Button>}
        {job.can_stop && <Button size="sm" variant="danger" disabled={busy} onClick={() => onAction('stop')}>Stop</Button>}
        {job.can_resume && <Button size="sm" disabled={busy} onClick={() => onAction('resume')}>Resume batch</Button>}
        {job.can_dismiss && <Button size="sm" variant="ghost" disabled={busy} onClick={() => onAction('dismiss')}>Dismiss</Button>}
        {onClear && <Button size="sm" variant="ghost" onClick={onClear}>Show all runs</Button>}
      </div>
    </div>
  )
}

function RunRow({ run, selected, onSelect, onResume, resuming, onJob }: {
  run: RunView
  selected: boolean
  onSelect: (on: boolean) => void
  onResume: () => void
  resuming: boolean
  onJob: () => void
}) {
  const raw = run.raw
  return (
    <tr className={cx(selected && 'selected')}>
      <td><input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} aria-label={`Select ${run.id}`} /></td>
      <td>
        <div className="flex flex-col items-start gap-0.5">
          <ProcessPill status={run.process} />
          {raw.failure_reason && <span className="max-w-36 truncate text-[11px] text-warn" title={raw.failure_reason}>{raw.failure_reason}</span>}
        </div>
      </td>
      <td><OutcomeCell outcome={run.outcome} campaign={run.kind === 'avo'} /></td>
      <td>
        <span className="whitespace-nowrap">{MODE_LABEL[run.mode]}</span>
        {run.worldModel && run.worldModel !== 'not-recorded' && <div className="text-[11px] text-faint">{run.worldModel}</div>}
      </td>
      <td>
        <span className="whitespace-nowrap" title={run.legacy ? 'Identity normalized from a pre-revamp config (no run_spec.json)' : 'run_spec.json'}>{run.harness}{run.legacy && <span className="text-faint">*</span>}</span>
      </td>
      <td className="max-w-48">
        <div className="truncate" title={run.model}>{modelParts(run.model).name}</div>
        <div className="truncate text-[11px] text-faint" title={run.optimizerModel ?? undefined}>{[modelParts(run.model).provider, run.effort].filter(Boolean).join(' · ')}{run.optimizerModel && run.optimizerModel !== run.model ? ` · opt ${modelParts(run.optimizerModel).name}` : ''}</div>
      </td>
      <td className="whitespace-nowrap"><Link to={gameHref(run.game)}>{gameName(run.game)}</Link></td>
      <td><ProgressText run={run} /></td>
      <td className="whitespace-nowrap text-[12px] text-muted" title={`Last activity ${dateTime(run.activity)}`}>{run.started ? shortTime(run.started) : '—'}</td>
      <td className="max-w-40">
        <Link to={runHref(run.id)} className="block truncate text-[12px]" title={run.id}>{shortId(run.id, 1)}</Link>
        {run.batch && <button type="button" onClick={onJob} className="block max-w-40 truncate text-left text-[11px] text-faint hover:text-accent" title={run.batch}>{run.batch.split('/').at(-1)}</button>}
      </td>
      <td className="whitespace-nowrap text-right">
        {raw.resumable && !raw.resumed_as && <Button size="sm" disabled={resuming} onClick={onResume}>{run.kind === 'avo' ? 'Resume' : 'Continue'}</Button>}
        {raw.resumed_as && <Link to={runHref(raw.resumed_as)} className="text-[11.5px]">resumed →</Link>}
      </td>
    </tr>
  )
}
