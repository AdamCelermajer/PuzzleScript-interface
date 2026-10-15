import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob, ResumeResult } from '../api/types'
import { GameThumb, HarnessChip, LevelPips, RunId, SectionLabel, StatusDot } from '../components/identity'
import { Button, Empty, ErrorBox, Input, Loading, Notice, Select, cx } from '../components/ui'
import { gameName, relativeTime, shortTime } from '../lib/format'
import { EMPTY_FILTERS, MODE_LABEL, distinct, groupLaunches, matchesFilters, modelParts, runHref, type Launch, type RunFilters, type RunView } from '../lib/runs'
import { processStatus } from '../lib/status'

const STATUS_OPTIONS: [string, string][] = [
  ['', 'Any status'], ['active', 'Active'], ['running', 'Running'], ['queued', 'Queued'], ['paused', 'Paused'],
  ['finished', 'Finished'], ['stopped', 'Stopped'], ['failed', 'Failed'], ['attention', 'Needs assistance'], ['unconfirmed', 'Unconfirmed'],
  ['solved', 'Solved'],
]
const ARCHIVE_PAGE = 12

type JobVerb = 'stop' | 'pause' | 'dismiss' | 'resume'

export function RunsView() {
  const [params, setParams] = useSearchParams()
  const filters: RunFilters = { ...EMPTY_FILTERS, ...Object.fromEntries([...params.entries()].filter(([k]) => k in EMPTY_FILTERS)) }
  const catalog = useCatalog(5000)
  const navigate = useNavigate()
  const client = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveLimit, setArchiveLimit] = useState(ARCHIVE_PAGE)
  const jobAction = useMutation({
    mutationFn: ({ verb, job }: { verb: JobVerb; job: string }) => api.post(`/experiments/${verb}${q({ job })}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['catalog'] }),
  })
  const resume = useMutation({
    mutationFn: (runId: string) => api.post<ResumeResult>('/runs/resume', { run_id: runId }),
    onSuccess: (result) => { client.invalidateQueries({ queryKey: ['catalog'] }); navigate(`/runs${q({ job: result.job_id })}`) },
  })
  const setFilter = (key: keyof RunFilters, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const runs = catalog.views
  const jobs = catalog.data?.jobs ?? []
  const jobById = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs])
  const visible = useMemo(() => runs.filter((r) => matchesFilters(r, filters)), [runs, params]) // eslint-disable-line react-hooks/exhaustive-deps
  const launches = useMemo(() => groupLaunches(visible, jobById), [visible, jobById])
  const current = launches.filter((l) => !l.archive)
  const archive = launches.filter((l) => l.archive)
  const archiveRuns = archive.reduce((n, l) => n + l.runs.length, 0)
  const options = useMemo(() => ({ harness: distinct(runs, (r) => r.harness), model: distinct(runs, (r) => r.model), game: distinct(runs, (r) => r.game) }), [runs])
  const anyFilter = Object.values(filters).some(Boolean)
  const toggle = (id: string, on: boolean) => setSelected((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })
  const onJob = (verb: JobVerb, job: CatalogJob) => {
    const name = job.id.split('/').at(-1)
    const prompts: Partial<Record<JobVerb, string>> = {
      stop: `Stop ${name}? Queued runs are cancelled and owned containers stopped.`,
      dismiss: `Remove ${name} from the active list? Artifacts are kept.`,
      resume: `Resume ${name}? This starts paid model calls.`,
    }
    if (!prompts[verb] || window.confirm(prompts[verb])) jobAction.mutate({ verb, job: job.id })
  }
  const card = (launch: Launch, compact = false) => (
    <LaunchCard
      key={launch.id}
      launch={launch}
      compact={compact}
      selected={selected}
      onSelect={toggle}
      busy={jobAction.isPending}
      onJob={onJob}
      onResume={(id) => window.confirm('Resume this run in a new batch? This starts paid model calls.') && resume.mutate(id)}
      onFocus={() => setFilter('job', launch.id)}
    />
  )

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Runs</h1>
          <p className="mt-1 text-[13.5px] text-muted">
            {catalog.data ? `${runs.length} runs in ${launches.length} launches · updated ${relativeTime(catalog.data.checked_at * 1000)}` : 'Every launch, live and finished'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear {selected.size}</Button>}
          {selected.size >= 2 && <Button onClick={() => navigate(`/compare?${[...selected].map((id) => `run=${encodeURIComponent(id)}`).join('&')}`)}>Compare {selected.size}</Button>}
          <Link to="/launch"><Button variant="primary">New launch</Button></Link>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <Input placeholder="Filter id, game, model…" value={filters.q} onChange={(e) => setFilter('q', e.target.value)} className="w-60" />
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
        {anyFilter && <Button variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Reset</Button>}
        {filters.job && <span className="ml-auto text-[12px] text-muted">Showing one launch</span>}
      </div>

      {catalog.data?.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
      {(jobAction.error || resume.error) && <ErrorBox error={jobAction.error ?? resume.error} />}

      {catalog.isLoading ? <Loading label="Reading the run catalog…" /> : catalog.error ? <ErrorBox error={catalog.error} retry={() => catalog.refetch()} /> : !visible.length ? (
        <div className="rounded-xl border border-dashed border-line-strong"><Empty title={runs.length ? 'No runs match these filters' : 'No runs yet'}>{runs.length ? 'Loosen a filter or reset them.' : <Link to="/launch">Launch the first run.</Link>}</Empty></div>
      ) : (
        <>
          <section className="flex flex-col gap-3">
            <SectionLabel>Launches {current.length > 0 && <span className="ml-1 text-faint">{current.length}</span>}</SectionLabel>
            {current.length ? current.map((l) => card(l)) : (
              <div className="rounded-xl border border-dashed border-line-strong px-5 py-4 text-[13px] text-muted">No launch from the new harnesses matches. {archiveRuns > 0 && 'Older runs are in the archive below.'}</div>
            )}
          </section>
          {archive.length > 0 && (
            <section className="flex flex-col gap-3">
              <button type="button" onClick={() => setArchiveOpen(!archiveOpen || Boolean(filters.job))} className="flex items-center justify-between rounded-xl border border-line bg-panel px-4 py-3 text-left hover:bg-hover">
                <span>
                  <span className="section-label">{archiveOpen || filters.job ? '▾' : '▸'} Archive</span>
                  <span className="ml-3 text-[13px] text-muted">{archiveRuns} runs in {archive.length} folders · recorded before the harness revamp (no run_spec.json)</span>
                </span>
                <span className="text-[12px] text-faint">{archiveOpen ? 'Hide' : 'Show'}</span>
              </button>
              {(archiveOpen || filters.job) && (
                <>
                  {archive.slice(0, filters.job ? undefined : archiveLimit).map((l) => card(l, true))}
                  {!filters.job && archive.length > archiveLimit && <Button variant="ghost" onClick={() => setArchiveLimit(archiveLimit + ARCHIVE_PAGE)}>Show {Math.min(ARCHIVE_PAGE, archive.length - archiveLimit)} more folders</Button>}
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}

function LaunchCard({ launch, compact, selected, onSelect, busy, onJob, onResume, onFocus }: {
  launch: Launch
  compact?: boolean
  selected: Set<string>
  onSelect: (id: string, on: boolean) => void
  busy: boolean
  onJob: (verb: JobVerb, job: CatalogJob) => void
  onResume: (id: string) => void
  onFocus: () => void
}) {
  const [open, setOpen] = useState(!compact)
  const job = launch.job
  const status = job ? processStatus({ status: job.status, status_source: job.can_stop ? 'Batch worker heartbeat' : 'Saved batch record', needs_assistance: job.needs_assistance }) : null
  const games = [...new Set(launch.runs.map((r) => r.game))]
  const solved = launch.runs.filter((r) => r.outcome.tone === 'solved').length
  return (
    <article className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow)]">
      <header className="flex flex-wrap items-center gap-4 px-4 py-3">
        <div className="flex -space-x-2">
          {games.slice(0, 3).map((g) => <GameThumb key={g} gameId={g} size={36} className="ring-2 ring-panel" />)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <button type="button" onClick={onFocus} className="truncate text-left text-[15px] font-semibold tracking-tight hover:underline">{launch.label}</button>
            {status && <StatusDot status={status} />}
            <span className="text-[12px] text-faint">{launch.started ? shortTime(launch.started) : ''}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
            {launch.modes.map((m) => <span key={m} className="rounded-md bg-neutral-soft px-1.5 py-px">{MODE_LABEL[m]}</span>)}
            {launch.harnesses.map((h) => <HarnessChip key={h} harness={h} legacy={launch.archive} />)}
            <span className="truncate" title={launch.models.join(', ')}>{launch.models.map((m) => modelParts(m).name).slice(0, 3).join(', ')}{launch.models.length > 3 ? ` +${launch.models.length - 3}` : ''}</span>
            {launch.budget && <span className="text-faint">· {launch.budget}</span>}
          </div>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-right">
            <div className="text-[15px] font-semibold tabular-nums">{solved}<span className="text-faint">/{launch.runs.length}</span></div>
            <div className="section-label">solved</div>
          </div>
          <div className="flex items-center gap-1.5">
            {job?.can_pause && <Button size="sm" disabled={busy} onClick={() => onJob('pause', job)}>Pause</Button>}
            {job?.can_stop && <Button size="sm" variant="danger" disabled={busy} onClick={() => onJob('stop', job)}>Stop</Button>}
            {job?.can_resume && <Button size="sm" disabled={busy} onClick={() => onJob('resume', job)}>Resume</Button>}
            {job?.can_dismiss && <Button size="sm" variant="ghost" disabled={busy} onClick={() => onJob('dismiss', job)}>Dismiss</Button>}
            {job?.comparison && <Link to={`/compare?job=${encodeURIComponent(job.id)}`}><Button size="sm">Compare</Button></Link>}
            <Button size="sm" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? '▾' : '▸'} {launch.runs.length} run{launch.runs.length === 1 ? '' : 's'}</Button>
          </div>
        </div>
      </header>
      {open && (
        <div className="overflow-x-auto border-t border-line">
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-8" />
                <th>Game</th>
                <th>Levels</th>
                <th>Harness</th>
                <th>Model</th>
                <th>Progress</th>
                <th>Status</th>
                <th>Run</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {launch.runs.map((run) => <RunRow key={run.id} run={run} selected={selected.has(run.id)} onSelect={(on) => onSelect(run.id, on)} onResume={() => onResume(run.id)} />)}
            </tbody>
          </table>
        </div>
      )}
    </article>
  )
}

function RunRow({ run, selected, onSelect, onResume }: { run: RunView; selected: boolean; onSelect: (on: boolean) => void; onResume: () => void }) {
  const raw = run.raw
  return (
    <tr className={cx(selected && 'selected')}>
      <td><input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} aria-label={`Select ${run.id}`} className="accent-[var(--fg)]" /></td>
      <td className="min-w-52">
        <div className="flex items-center gap-3">
          <GameThumb gameId={run.game} size={30} />
          <div className="min-w-0">
            <Link to={runHref(run.id)} className="block truncate text-[13.5px] font-semibold text-fg">{gameName(run.game)}</Link>
            <div className="truncate text-[11.5px] text-faint">{MODE_LABEL[run.mode]}{run.worldModel && run.worldModel !== 'not-recorded' ? ` · ${run.worldModel}` : ''}</div>
          </div>
        </div>
      </td>
      <td><LevelPips levels={run.outcome.score} total={run.outcome.total} solved={run.outcome.tone === 'solved'} /></td>
      <td><HarnessChip harness={run.harness} legacy={run.legacy} /></td>
      <td className="max-w-56">
        <div className="truncate text-[13px]" title={run.model}>{modelParts(run.model).name}</div>
        <div className="truncate text-[11.5px] text-faint">{[modelParts(run.model).provider, run.effort].filter((x) => x && x !== '—').join(' · ')}</div>
      </td>
      <td className="whitespace-nowrap text-[12px] tabular-nums text-muted">
        {run.progress.used ?? '–'}{run.progress.budget ? <span className="text-faint">/{run.progress.budget}</span> : null} <span className="text-[11px] text-faint">{run.progress.unit}</span>
      </td>
      <td>
        <StatusDot status={run.process} />
        <div className="text-[11px] text-faint" title={raw.failure_reason ?? undefined}>{raw.failure_reason ? 'needs attention' : relativeTime(run.activity)}</div>
      </td>
      <td><RunId id={run.id} className="w-44" /></td>
      <td className="text-right whitespace-nowrap">
        {raw.resumable && !raw.resumed_as && <Button size="sm" onClick={onResume}>{run.kind === 'avo' ? 'Resume' : 'Continue'}</Button>}
        {raw.resumed_as && <Link to={runHref(raw.resumed_as)} className="text-[12px]">continued →</Link>}
      </td>
    </tr>
  )
}
