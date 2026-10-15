import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, q } from '../api/client'
import { useCatalog } from '../api/hooks'
import type { CatalogJob } from '../api/types'
import { GameThumb, HarnessChip, LevelPips, SectionLabel, StatusDot, TierBadge, harnessColor, harnessLabel } from '../components/identity'
import { ProgressBar } from '../components/status'
import { Button, Empty, ErrorBox, Loading, Notice, Toggle, cx } from '../components/ui'
import { gameName, relativeTime } from '../lib/format'
import { MODE_LABEL, gameHref, jobLabel, launchLabel, modelParts, runHref, type RunView } from '../lib/runs'
import { processStatus } from '../lib/status'

export interface MatrixCell {
  best_levels: number | null
  win_levels: number | null
  runs: number
  best_run_id: string
  solved: boolean
  run_ids: string[]
}

export interface ResultsMatrix {
  games: { game_id: string; title: string; tier: string | null; win_levels: number | null }[]
  columns: { harness: string; model: string; label: string; runs: number }[]
  cells: Record<string, MatrixCell>
  archive: boolean
  checked_at: number
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const MODES = [['', 'All modes'], ['baseline', 'Baseline'], ['baseline-plus', 'Baseline+'], ['campaign', 'Campaign']] as const

/** Consecutive columns of the same harness, for the grouped header. */
export function harnessGroups(columns: ResultsMatrix['columns']): { harness: string; span: number }[] {
  const groups: { harness: string; span: number }[] = []
  for (const column of columns) {
    const last = groups.at(-1)
    if (last && last.harness === column.harness) last.span += 1
    else groups.push({ harness: column.harness, span: 1 })
  }
  return groups
}

export function ResultsView() {
  const [params, setParams] = useSearchParams()
  const archive = params.get('archive') === '1'
  const mode = params.get('mode') ?? ''
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const matrix = useQuery({
    queryKey: ['results-matrix', archive, mode],
    queryFn: ({ signal }) => api.get<ResultsMatrix>(`/results/matrix${q({ archive: archive ? 1 : 0, mode })}`, signal),
    refetchInterval: 20_000,
    placeholderData: keepPreviousData,
  })
  const catalog = useCatalog(5000)
  const data = matrix.data
  const totals = useMemo(() => {
    const cells = Object.values(data?.cells ?? {})
    return { runs: cells.reduce((n, c) => n + c.runs, 0), solved: cells.filter((c) => c.solved).length, cells: cells.length }
  }, [data])

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Results</h1>
          <p className="mt-1 text-[13.5px] text-muted">Best levels solved per game and harness·model. Filled pips are solved levels.</p>
        </div>
        <Link to="/launch"><Button variant="primary">New launch</Button></Link>
      </header>

      <RunningNow catalog={catalog} />

      <section className="flex flex-col gap-3">
        <SectionLabel
          right={
            <div className="flex items-center gap-4">
              <div className="flex rounded-lg border border-line bg-panel p-0.5">
                {MODES.map(([id, label]) => (
                  <button key={id} type="button" onClick={() => set('mode', id)} className={cx('rounded-md px-2.5 py-1 text-[12px]', mode === id ? 'bg-accent text-accent-fg' : 'text-muted hover:text-fg')}>
                    {label}
                  </button>
                ))}
              </div>
              <Toggle checked={archive} onChange={(v) => set('archive', v ? '1' : '')} label={<span className="text-[12.5px] text-muted">Include archive</span>} />
            </div>
          }
        >
          Results matrix
          {data && <span className="ml-3 font-normal tracking-normal normal-case text-faint">{plural(data.games.length, 'game')} · {plural(data.columns.length, 'configuration')} · {plural(totals.runs, 'run')} · {plural(totals.solved, 'solved cell')}</span>}
        </SectionLabel>
        {matrix.isLoading ? <Loading label="Computing results…" /> : matrix.error instanceof ApiError && matrix.error.status === 404 ? (
          <Notice tone="warn">The workbench API has not loaded the results route yet (restart the API on port 8010). Meanwhile, see <Link to="/runs">all runs</Link>.</Notice>
        ) : matrix.error ? <ErrorBox error={matrix.error} retry={() => matrix.refetch()} /> : data && !data.games.length ? (
          <div className="rounded-xl border border-dashed border-line-strong">
            <Empty title={archive ? 'No runs with results yet' : 'No results from the new harnesses yet'}>
              {archive ? <Link to="/launch">Launch a run.</Link> : <>Runs recorded before the harness revamp are in the archive. <button type="button" className="text-link hover:underline" onClick={() => set('archive', '1')}>Include archive</button>.</>}
            </Empty>
          </div>
        ) : data && <Matrix data={data} runs={catalog.views} />}
      </section>
    </div>
  )
}

function RunningNow({ catalog }: { catalog: ReturnType<typeof useCatalog> }) {
  const client = useQueryClient()
  const action = useMutation({
    mutationFn: ({ verb, job }: { verb: 'stop' | 'pause' | 'resume'; job: string }) => api.post(`/experiments/${verb}${q({ job })}`),
    onSettled: () => client.invalidateQueries({ queryKey: ['catalog'] }),
  })
  const all = (catalog.data?.jobs ?? []).slice().sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  const live = all.filter((j) => ['starting', 'running', 'stopping'].includes(j.status))
  const paused = all.filter((j) => j.status === 'paused' && !j.dismissed_from_runs_at)
  const owned = new Set(live.map((j) => j.id))
  const loose = catalog.views.filter((r) => r.process.tone === 'running' && r.process.live && !owned.has(r.batch))
  const act = (verb: 'stop' | 'pause' | 'resume', job: CatalogJob) =>
    (verb !== 'stop' || window.confirm(`Stop ${jobLabel(job)}? Queued runs are cancelled.`)) &&
    (verb !== 'resume' || window.confirm('Resume this batch? This starts paid model calls.')) &&
    action.mutate({ verb, job: job.id })
  const count = live.length + (loose.length ? 1 : 0)
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel right={catalog.data && <span className="text-[11.5px] tracking-normal normal-case text-faint">updated {relativeTime(catalog.data.checked_at * 1000)}</span>}>
        Running now {count > 0 && <span className="ml-1.5 rounded-full bg-run-soft px-1.5 py-px text-[10.5px] text-run">{count}</span>}
      </SectionLabel>
      {action.error ? <ErrorBox error={action.error} /> : null}
      {catalog.isLoading ? <Loading /> : !count ? (
        <div className="flex items-center justify-between rounded-xl border border-dashed border-line-strong px-5 py-4 text-[13px] text-muted">
          Nothing is running right now.
          <Link to="/launch" className="text-[13px] font-medium text-fg">Start a launch →</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 2xl:grid-cols-2">
          {live.map((job) => <LiveJob key={job.id} job={job} runs={catalog.views.filter((r) => r.batch === job.id)} busy={action.isPending} onAction={(verb) => act(verb, job)} />)}
          {loose.length > 0 && <LiveJob runs={loose} busy={false} onAction={() => undefined} />}
        </div>
      )}
      {paused.length > 0 && (
        <div className="flex flex-col divide-y divide-line rounded-xl border border-line bg-panel">
          {paused.map((job) => {
            const runs = catalog.views.filter((r) => r.batch === job.id)
            return (
              <div key={job.id} className="flex items-center gap-3 px-4 py-2">
                <span className="h-2 w-2 rounded-full bg-warn" />
                <span className="text-[12px] text-muted">paused</span>
                <Link to={`/runs${q({ job: job.id })}`} className="truncate text-[13px] font-medium">{launchLabel(job.id)}</Link>
                <span className="text-[12px] text-faint">{plural(runs.length, 'run')} · {[...new Set(runs.map((r) => gameName(r.game)))].join(', ')} · {relativeTime(job.created_at ? Date.parse(job.created_at) : 0)}</span>
                <span className="ml-auto flex gap-1.5">
                  {job.can_resume && <Button size="sm" disabled={action.isPending} onClick={() => act('resume', job)}>Resume</Button>}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function LiveJob({ job, runs, busy, onAction }: { job?: CatalogJob; runs: RunView[]; busy: boolean; onAction: (verb: 'stop' | 'pause' | 'resume') => void }) {
  const status = job ? processStatus({ status: job.status, status_source: job.can_stop ? 'Batch worker heartbeat' : '', needs_assistance: job.needs_assistance }) : null
  const label = job ? launchLabel(job.id) : 'Other live containers'
  const ordered = [...runs].sort((a, b) => Number(b.process.tone === 'running') - Number(a.process.tone === 'running'))
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-panel shadow-[var(--shadow)]">
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        {status && <StatusDot status={status} />}
        <Link to={job ? `/runs${q({ job: job.id })}` : '/runs?status=running'} className="min-w-0 truncate text-[13.5px] font-semibold text-fg">{label}</Link>
        <span className="text-[12px] text-faint">{job ? relativeTime(job.created_at ? Date.parse(job.created_at) : 0) : ''}</span>
        <div className="ml-auto flex items-center gap-1.5">
          {job?.can_pause && <Button size="sm" disabled={busy} onClick={() => onAction('pause')}>Pause</Button>}
          {job?.can_stop && <Button size="sm" variant="danger" disabled={busy} onClick={() => onAction('stop')}>Stop</Button>}
          {job?.can_resume && <Button size="sm" disabled={busy} onClick={() => onAction('resume')}>Resume</Button>}
        </div>
      </div>
      <div className="divide-y divide-line">
        {ordered.slice(0, 8).map((run) => (
          <Link key={run.id} to={runHref(run.id)} className="grid grid-cols-[28px_minmax(0,1.2fr)_minmax(0,1fr)_110px_minmax(80px,0.8fr)_96px] items-center gap-3 px-4 py-2 text-fg hover:bg-hover hover:no-underline">
            <GameThumb gameId={run.game} size={28} />
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium">{gameName(run.game)}</span>
              <span className="block truncate text-[11.5px] text-faint">{MODE_LABEL[run.mode]} · {modelParts(run.model).name}</span>
            </span>
            <HarnessChip harness={run.harness} legacy={run.legacy} className="justify-self-start" />
            <LevelPips levels={run.outcome.score} total={run.outcome.total} solved={run.outcome.tone === 'solved'} size="sm" />
            <span className="flex flex-col gap-1">
              <ProgressBar used={run.progress.used} budget={run.progress.budget} tone={run.process.tone === 'running' ? 'run' : 'muted'} />
              <span className="text-[11px] text-faint tabular-nums">{run.progress.used ?? 0}{run.progress.budget ? `/${run.progress.budget}` : ''} {run.progress.unit}</span>
            </span>
            <span className="flex flex-col items-end gap-0.5">
              <StatusDot status={run.process} />
              <span className="text-[11px] text-faint">{relativeTime(run.activity)}</span>
            </span>
          </Link>
        ))}
        {ordered.length > 8 && <Link to={job ? `/runs${q({ job: job.id })}` : '/runs'} className="block px-4 py-2 text-[12px]">{ordered.length - 8} more runs →</Link>}
      </div>
    </div>
  )
}

function Matrix({ data, runs }: { data: ResultsMatrix; runs: RunView[] }) {
  const groups = harnessGroups(data.columns)
  const byId = useMemo(() => new Map(runs.map((r) => [r.id, r])), [runs])
  const [open, setOpen] = useState<string | null>(null)
  const navigate = useNavigate()
  return (
    <div className="w-fit max-w-full overflow-auto rounded-xl border border-line bg-panel shadow-[var(--shadow)]" style={{ maxHeight: 'calc(100vh - 220px)' }}>
      <table className="border-separate border-spacing-0 text-[13px]">
        <thead>
          <tr>
            <th rowSpan={2} className="sticky top-0 left-0 z-30 min-w-[240px] border-r border-b border-line bg-panel px-4 py-2 text-left align-bottom">
              <span className="section-label">Game</span>
            </th>
            {groups.map((g, i) => (
              <th key={i} colSpan={g.span} className="sticky top-0 z-20 border-b border-l border-line bg-panel px-3 pt-2.5 pb-1.5 text-left" style={{ boxShadow: `inset 0 2px 0 ${harnessColor(g.harness)}` }}>
                <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold">
                  <span className="h-2 w-2 rounded-[2px]" style={{ background: harnessColor(g.harness) }} />
                  {harnessLabel(g.harness)}
                </span>
              </th>
            ))}
          </tr>
          <tr>
            {data.columns.map((c, i) => (
              <th key={`${c.harness}|${c.model}`} title={c.model} className={cx('sticky top-[37px] z-20 w-[124px] min-w-[124px] max-w-[124px] border-b border-line bg-panel px-3 pb-2 text-left align-bottom text-[11.5px] font-medium text-muted', (i === 0 || data.columns[i - 1].harness !== c.harness) && 'border-l')}>
                <span className="line-clamp-2 break-words [overflow-wrap:anywhere]">{c.label}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.games.map((game) => (
            <tr key={game.game_id} className="group">
              <td className="sticky left-0 z-10 border-r border-b border-line bg-panel px-4 py-2 group-hover:bg-hover">
                <Link to={gameHref(game.game_id)} className="flex items-center gap-3 text-fg hover:no-underline">
                  <GameThumb gameId={game.game_id} size={40} rounded="rounded-md" />
                  <span className="min-w-0">
                    <span className="block truncate text-[13.5px] font-semibold">{game.title}</span>
                    <span className="flex items-center gap-2 text-[11.5px] text-faint">
                      <TierBadge tier={game.tier} />
                      {game.win_levels ? <span>{game.win_levels} levels</span> : null}
                    </span>
                  </span>
                </Link>
              </td>
              {data.columns.map((c, i) => {
                const key = `${game.game_id}|${c.harness}|${c.model}`
                const cell = data.cells[key]
                const first = i === 0 || data.columns[i - 1].harness !== c.harness
                return (
                  <td key={key} className={cx('relative border-b border-line px-3 py-2 group-hover:bg-hover', first && 'border-l', cell?.solved && 'bg-ok-soft/60')}>
                    {cell ? (
                      <button
                        type="button"
                        onClick={() => (cell.runs === 1 ? navigate(runHref(cell.best_run_id)) : setOpen(open === key ? null : key))}
                        className="flex w-full flex-col items-start gap-1 rounded-md text-left"
                        title={`${cell.runs} run${cell.runs === 1 ? '' : 's'} · best ${cell.best_levels ?? '–'}/${cell.win_levels ?? '?'}`}
                      >
                        <LevelPips levels={cell.best_levels} total={cell.win_levels ?? game.win_levels} solved={cell.solved} size="sm" />
                        <span className="text-[11px] text-faint">{cell.runs} run{cell.runs === 1 ? '' : 's'}{cell.runs > 1 ? ' ▾' : ''}</span>
                      </button>
                    ) : <span className="text-faint">·</span>}
                    {open === key && cell && <CellPopover cell={cell} byId={byId} onClose={() => setOpen(null)} />}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CellPopover({ cell, byId, onClose }: { cell: MatrixCell; byId: Map<string, RunView>; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey) }
  }, [onClose])
  return (
    <div ref={ref} className="absolute top-full left-2 z-40 mt-1 w-80 overflow-hidden rounded-lg border border-line bg-raised shadow-xl">
      <div className="border-b border-line px-3 py-2 section-label">{cell.runs} runs</div>
      <div className="max-h-72 overflow-auto">
        {cell.run_ids.map((id) => {
          const run = byId.get(id)
          return (
            <Link key={id} to={runHref(id)} className="flex items-center gap-3 px-3 py-2 text-fg hover:bg-hover hover:no-underline">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px]">{run ? `${MODE_LABEL[run.mode]} · ${run.effort}` : id.split('/').slice(-2).join('/')}</span>
                <span className="block truncate font-mono text-[10.5px] text-faint">{id.replace(/\/campaign$/, '').split('/').slice(-2).join('/')}</span>
              </span>
              {run && <LevelPips levels={run.outcome.score} total={run.outcome.total} solved={run.outcome.tone === 'solved'} size="sm" showNumber={false} />}
              {id === cell.best_run_id && <span className="text-[10.5px] font-semibold text-ok">best</span>}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
