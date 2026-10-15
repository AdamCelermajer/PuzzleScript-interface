import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob, ResumeResult } from '../api/types'
import { GameThumb, HarnessChip, LevelPips, RunId, StatusDot } from '../components/identity'
import { ProgressText } from '../components/status'
import { Button, ErrorBox, Loading, Notice } from '../components/ui'
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
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5">
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
    <div className="flex flex-col gap-4 rounded-xl border border-line bg-panel p-5 shadow-[var(--shadow)]">
      <div className="flex flex-wrap items-start gap-5">
        <Link to={gameHref(run.game)} className="shrink-0"><GameThumb gameId={run.game} size={88} rounded="rounded-lg" /></Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em]"><Link to={gameHref(run.game)} className="text-fg">{gameName(run.game)}</Link></h1>
            <span className="rounded-md bg-neutral-soft px-1.5 py-px text-[12px] font-medium text-muted">{MODE_LABEL[run.mode]}</span>
            <HarnessChip harness={run.harness} legacy={run.legacy} />
            <StatusDot status={run.process} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2">
            <LevelPips levels={run.outcome.score} total={run.outcome.total} solved={run.outcome.tone === 'solved'} size="lg" />
            <span className="text-[13px] text-muted"><span className="font-medium text-fg">{run.model}</span> · {run.effort}</span>
          </div>
          <RunId id={run.id} className="mt-2" />
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
        {run.kind === 'avo' && <Fact label="Optimizer" value={<span className="break-all">{run.optimizerModel ?? "—"} · {raw.optimizer_effort ?? "—"}</span>} />}
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
      <div className="section-label !text-[10.5px]">{label}</div>
      <div className="break-words">{value}</div>
    </div>
  )
}
