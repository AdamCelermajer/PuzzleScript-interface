import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob, ResumeResult } from '../api/types'
import { OutcomeCell, ProcessPill, ProgressText } from '../components/status'
import { Button, ErrorBox, Loading, Mono, Notice, Pill } from '../components/ui'
import { dateTime, gameName, relativeTime } from '../lib/format'
import { MODE_LABEL, gameHref, normalizeRun, runHref, type RunView } from '../lib/runs'
import { BaselineDetail } from './BaselineDetail'
import { CampaignDetail } from './CampaignDetail'

/** One view for every mode: header from the catalog row, body by run kind. */
export function RunDetailView() {
  const id = decodeURIComponent(useParams()['*'] ?? '').replace(/\/+$/, '')
  const catalog = useCatalog(5000)
  const raw = catalog.data?.runs.find((r) => r.id === id)
  const run = raw ? normalizeRun(raw) : null
  const job = catalog.data?.jobs.find((j) => j.id === run?.batch)
  const campaign = run ? run.kind === 'avo' : id.endsWith('/campaign')

  if (!id) return <ErrorBox error="No run id in the URL" />
  return (
    <div className="flex flex-col gap-4">
      <Link to="/runs" className="text-[12px] text-muted">← Runs</Link>
      {run ? <RunHeader run={run} job={job} /> : catalog.isLoading ? <Loading label="Reading the run catalog…" /> : (
        <div className="flex flex-col gap-1">
          <h1 className="font-mono text-[15px] font-semibold break-all">{id}</h1>
          <Notice tone="warn">This run is not in the current catalog (it may have no artifacts yet). Showing saved artifacts only.</Notice>
        </div>
      )}
      {campaign ? <CampaignDetail runId={id} live={run?.process.tone === 'running'} /> : <BaselineDetail runId={id} live={run?.process.tone === 'running'} mode={run?.mode} />}
    </div>
  )
}

function RunHeader({ run, job }: { run: RunView; job?: CatalogJob }) {
  const raw = run.raw
  const navigate = useNavigate()
  const client = useQueryClient()
  const resume = useMutation({
    mutationFn: () => api.post<ResumeResult>('/runs/resume', { run_id: run.id }),
    onSuccess: (result) => { client.invalidateQueries({ queryKey: ['catalog'] }); navigate(runHref(result.run_id)) },
  })
  const stop = useMutation({
    mutationFn: (jobId: string) => api.post(`/experiments/stop${q({ job: jobId })}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['catalog'] }),
  })
  const budget = raw.run_budget ?? {}
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[17px] font-semibold"><Link to={gameHref(run.game)} className="text-fg">{gameName(run.game)}</Link></h1>
            <Pill tone="accent">{MODE_LABEL[run.mode]}</Pill>
            <ProcessPill status={run.process} />
            <OutcomeCell outcome={run.outcome} campaign={run.kind === 'avo'} />
          </div>
          <Mono className="mt-1 block break-all text-muted">{run.id}</Mono>
        </div>
        <div className="flex items-center gap-2">
          {job?.can_stop && <Button variant="danger" disabled={stop.isPending} onClick={() => window.confirm('Stop the whole batch this run belongs to?') && stop.mutate(job.id)}>Stop batch</Button>}
          {raw.resumable && !raw.resumed_as && (
            <Button disabled={resume.isPending} onClick={() => window.confirm('Resume this run in a new batch? This starts paid model calls.') && resume.mutate()}>
              {run.kind === 'avo' ? 'Resume campaign' : 'Continue run'}
            </Button>
          )}
          {raw.resumed_as && <Link to={runHref(raw.resumed_as)}><Button>Open continuation →</Button></Link>}
        </div>
      </div>
      {(resume.error || stop.error) && <ErrorBox error={resume.error ?? stop.error} />}
      {raw.failure_reason && <Notice tone="warn">{raw.failure_reason}</Notice>}
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[12.5px] md:grid-cols-4 xl:grid-cols-6">
        <Fact label="Harness" value={`${run.harness}${run.legacy ? ' (legacy record)' : ''}`} />
        <Fact label="Model" value={<Mono className="break-all">{run.model}</Mono>} />
        <Fact label="Effort" value={run.effort} />
        {run.kind === 'avo' && <Fact label="Optimizer" value={<Mono className="break-all">{run.optimizerModel ?? '—'} · {raw.optimizer_effort ?? '—'}</Mono>} />}
        {run.worldModel && <Fact label="World model" value={run.worldModel} />}
        <Fact label="Progress" value={<ProgressText run={run} />} />
        <Fact label="Wall budget" value={budget.max_wall_seconds === 0 ? 'unlimited' : budget.max_wall_seconds ? `${(budget.max_wall_seconds / 3600).toFixed(1)}h` : '—'} />
        {run.kind === 'avo' && <Fact label="Moves (research / solver)" value={`${budget.research_moves ?? '—'} / ${budget.solver_moves ?? '—'}`} />}
        <Fact label="Launched" value={dateTime(run.started)} />
        <Fact label="Last activity" value={`${relativeTime(run.activity)}`} />
        <Fact label="Process source" value={run.process.detail || '—'} />
        {raw.provider && <Fact label="Provider pin" value={raw.provider} />}
        {run.batch && <Fact label="Batch" value={<Link to={`/runs${q({ job: run.batch })}`} className="break-all">{run.batch.split('/').at(-1)}</Link>} />}
        {raw.continued_from && <Fact label="Continued from" value={<Link to={runHref(raw.continued_from)} className="break-all">{raw.continued_from}</Link>} />}
        {raw.log_href && <Fact label="Worker log" value={<a href={raw.log_href} target="_blank" rel="noreferrer">open ↗</a>} />}
      </div>
    </div>
  )
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] text-faint">{label}</div>
      <div className="break-words">{value}</div>
    </div>
  )
}
