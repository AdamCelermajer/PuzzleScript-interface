import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob, ResumeResult } from '../api/types'
import { RunList, type JobVerb } from '../components/RunList'
import { Button, Empty, ErrorBox, Input, Loading, Notice, Select, cx } from '../components/ui'
import { gameName, relativeTime } from '../lib/format'
import { EMPTY_FILTERS, distinct, groupLaunches, matchesFilters, type RunFilters } from '../lib/runs'

const STATUS_OPTIONS: [string, string][] = [
  ['', 'Any status'], ['active', 'Active'], ['running', 'Running'], ['queued', 'Queued'], ['paused', 'Paused'],
  ['finished', 'Finished'], ['stopped', 'Stopped'], ['failed', 'Failed'], ['attention', 'Needs assistance'], ['unconfirmed', 'Unconfirmed'],
  ['solved', 'Solved'],
]
const ARCHIVE_PAGE = 40
const FILTER_SELECT = 'h-8 min-w-0 max-w-44 shrink text-[12.5px]'

/** Job actions shared by the Runs page and the Results "Running now" list. */
export function useJobActions() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const jobAction = useMutation({
    mutationFn: ({ verb, job }: { verb: JobVerb; job: string }) => api.post(`/experiments/${verb}${q({ job })}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['catalog'] }),
  })
  const resume = useMutation({
    mutationFn: (runId: string) => api.post<ResumeResult>('/runs/resume', { run_id: runId }),
    onSuccess: (result) => { client.invalidateQueries({ queryKey: ['catalog'] }); navigate(`/runs${q({ job: result.job_id })}`) },
  })
  const onJob = (verb: JobVerb, job: CatalogJob) => {
    const name = job.id.split('/').at(-1)
    const prompts: Partial<Record<JobVerb, string>> = {
      stop: `Stop ${name}? Queued runs are cancelled and owned containers stopped.`,
      dismiss: `Remove ${name} from the active list? Artifacts are kept.`,
      resume: `Resume ${name}? This starts paid model calls.`,
    }
    if (!prompts[verb] || window.confirm(prompts[verb])) jobAction.mutate({ verb, job: job.id })
  }
  const onResume = (runId: string) => { if (window.confirm('Resume this run in a new batch? This starts paid model calls.')) resume.mutate(runId) }
  return { onJob, onResume, busy: jobAction.isPending || resume.isPending, error: jobAction.error ?? resume.error }
}

export function RunsView() {
  const [params, setParams] = useSearchParams()
  const filters: RunFilters = { ...EMPTY_FILTERS, ...Object.fromEntries([...params.entries()].filter(([k]) => k in EMPTY_FILTERS)) }
  const catalog = useCatalog(5000)
  const navigate = useNavigate()
  const actions = useJobActions()
  const client = useQueryClient()
  const archiving = useMutation({
    mutationFn: (body: { runs: string[]; archived: boolean }) => api.post<{ archived: string[] }>('/runs/archive', body),
    onSuccess: () => {
      setSelected(new Set())
      client.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [archiveOpen, setArchiveOpen] = useState(params.get('archive') === '1')
  const [archiveLimit, setArchiveLimit] = useState(ARCHIVE_PAGE)
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
  const archivedByHand = archive.reduce((n, l) => n + l.runs.filter((r) => r.archived).length, 0)
  const selectedRuns = runs.filter((r) => selected.has(r.id))
  const options = useMemo(() => ({ variant: distinct(runs, (r) => r.variant), harness: distinct(runs, (r) => r.harness), model: distinct(runs, (r) => r.model), game: distinct(runs, (r) => r.game) }), [runs])
  const anyFilter = Object.values(filters).some(Boolean)
  const showArchive = archiveOpen || Boolean(filters.job)
  const listProps = {
    selectable: true,
    selected,
    onSelect: (id: string, on: boolean) => setSelected((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n }),
    onResume: actions.onResume,
    onJob: actions.onJob,
    busy: actions.busy,
    expanded: (l: { id: string; runs: { process: { tone: string } }[] }) => l.id === filters.job || l.runs.some((r) => r.process.tone === 'running'),
  }

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Runs</h1>
          <p className="mt-1 text-[13.5px] text-muted">
            {catalog.data ? `${runs.length} runs · newest first · updated ${relativeTime(catalog.data.checked_at * 1000)}` : 'Every run, live and finished'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear {selected.size}</Button>}
          {selectedRuns.some((r) => !r.archived && !r.legacy) && <Button onClick={() => archiving.mutate({ runs: selectedRuns.filter((r) => !r.archived && !r.legacy).map((r) => r.id), archived: true })} disabled={archiving.isPending}>Archive {selectedRuns.filter((r) => !r.archived && !r.legacy).length}</Button>}
          {selectedRuns.some((r) => r.archived) && <Button onClick={() => archiving.mutate({ runs: selectedRuns.filter((r) => r.archived).map((r) => r.id), archived: false })} disabled={archiving.isPending}>Unarchive {selectedRuns.filter((r) => r.archived).length}</Button>}
          {selected.size >= 2 && <Button onClick={() => navigate(`/compare?${[...selected].map((id) => `run=${encodeURIComponent(id)}`).join('&')}`)}>Compare {selected.size}</Button>}
          <Link to="/launch"><Button variant="primary">New launch</Button></Link>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 xl:flex-nowrap">
        <Input placeholder="Filter id, game, model…" value={filters.q} onChange={(e) => setFilter('q', e.target.value)} className="min-w-48 flex-1" />
        <Select value={filters.variant} onChange={(e) => setFilter('variant', e.target.value)} className={FILTER_SELECT}>
          <option value="">Any framework</option>
          {options.variant.map((variant) => <option key={variant} value={variant}>{variant}</option>)}
        </Select>
        <Select value={filters.harness} onChange={(e) => setFilter('harness', e.target.value)} className={FILTER_SELECT}>
          <option value="">Any harness</option>
          {options.harness.map((h) => <option key={h} value={h}>{h}</option>)}
        </Select>
        <Select value={filters.model} onChange={(e) => setFilter('model', e.target.value)} className={FILTER_SELECT}>
          <option value="">Any model</option>
          {options.model.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
        <Select value={filters.game} onChange={(e) => setFilter('game', e.target.value)} className={FILTER_SELECT}>
          <option value="">Any game</option>
          {options.game.map((g) => <option key={g} value={g}>{gameName(g)}</option>)}
        </Select>
        <Select value={filters.status} onChange={(e) => setFilter('status', e.target.value)} className={FILTER_SELECT}>
          {STATUS_OPTIONS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </Select>
        {anyFilter && <Button variant="ghost" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Reset</Button>}
      </div>

      {catalog.data?.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
      {actions.error ? <ErrorBox error={actions.error} /> : null}
      {archiving.error ? <ErrorBox error={archiving.error} /> : null}

      {catalog.isLoading ? <Loading label="Reading the run catalog…" /> : catalog.error ? <ErrorBox error={catalog.error} retry={() => catalog.refetch()} /> : !visible.length ? (
        <div className="rounded-xl border border-dashed border-line-strong"><Empty title={runs.length ? 'No runs match these filters' : 'No runs yet'}>{runs.length ? 'Loosen a filter or reset them.' : <Link to="/launch">Launch the first run.</Link>}</Empty></div>
      ) : (
        <>
          <RunList
            launches={current}
            {...listProps}
            empty={<div className="rounded-xl border border-dashed border-line-strong px-5 py-4 text-[13px] text-muted">No run from the new harnesses matches.{archiveRuns > 0 && ' Older runs are in the archive below.'}</div>}
          />
          {archive.length > 0 && (
            <section className="flex flex-col gap-3">
              <button type="button" onClick={() => setArchiveOpen(!archiveOpen)} className={cx('flex items-center justify-between rounded-xl border border-line bg-panel px-4 py-3 text-left hover:bg-hover')}>
                <span>
                  <span className="section-label">{showArchive ? '▾' : '▸'} Archive</span>
                  <span className="ml-3 text-[13px] text-muted">{archiveRuns} runs: {archivedByHand ? `${archivedByHand} archived by you, ` : ''}{archiveRuns - archivedByHand} recorded before the harness revamp</span>
                </span>
                <span className="text-[12px] text-faint">{showArchive ? 'Hide' : 'Show'}</span>
              </button>
              {showArchive && (
                <>
                  <RunList launches={filters.job ? archive : archive.slice(0, archiveLimit)} {...listProps} />
                  {!filters.job && archive.length > archiveLimit && <Button variant="ghost" onClick={() => setArchiveLimit(archiveLimit + ARCHIVE_PAGE)}>Show more</Button>}
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}
