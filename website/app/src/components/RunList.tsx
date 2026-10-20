import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useGameTitle } from '../api/hooks'
import type { CatalogJob } from '../api/types'
import { relativeTime, shortTime } from '../lib/format'
import { modelParts, runHref, type Launch, type RunView } from '../lib/runs'
import { processStatus } from '../lib/status'
import { GameThumb, HarnessChip, LevelPips, RunId, StatusDot } from './identity'
import { Button, cx } from './ui'

export type JobVerb = 'stop' | 'pause' | 'dismiss' | 'resume'

/**
 * One column template for the header, run rows and group rows, sized to fit the content
 * width at 1280px+ without horizontal scrolling (flexible columns truncate with a tooltip).
 */
const COLUMNS = 'grid grid-cols-[18px_minmax(170px,1.7fr)_minmax(104px,0.8fr)_118px_minmax(110px,1.1fr)_104px_112px_minmax(96px,0.9fr)_76px] items-center gap-x-3'

export interface RunListProps {
  launches: Launch[]
  selectable?: boolean
  selected?: Set<string>
  onSelect?: (id: string, on: boolean) => void
  onResume?: (runId: string) => void
  onJob?: (verb: JobVerb, job: CatalogJob) => void
  busy?: boolean
  /** Launch ids whose group starts expanded (e.g. a focused or live launch). */
  expanded?: (launch: Launch) => boolean
  header?: boolean
  empty?: ReactNode
}

/** Flat run list, newest first. A launch with two or more runs collapses into one group row. */
export function RunList({ launches, selectable, selected, onSelect, onResume, onJob, busy, expanded, header = true, empty }: RunListProps) {
  if (!launches.length) return <>{empty ?? null}</>
  return (
    <div className="rounded-xl border border-line bg-panel shadow-[var(--shadow)]">
      {header && (
        <div className={cx(COLUMNS, 'sticky top-0 z-10 rounded-t-xl border-b border-line bg-panel px-4 py-2 section-label !text-[10.5px]')}>
          <span />
          <span>Game</span>
          <span>Levels</span>
          <span>Harness</span>
          <span>Model</span>
          <span>Progress</span>
          <span>Status</span>
          <span>Run</span>
          <span />
        </div>
      )}
      <div className="divide-y divide-line">
        {launches.map((launch) =>
          launch.runs.length >= 2 ? (
            <GroupRow key={`${launch.id}|${launch.archive}`} launch={launch} {...{ selectable, selected, onSelect, onResume, onJob, busy }} defaultOpen={expanded?.(launch) ?? false} />
          ) : (
            <RunRow key={launch.runs[0].id} run={launch.runs[0]} job={launch.job} {...{ selectable, selected, onSelect, onResume, onJob, busy }} />
          ),
        )}
      </div>
    </div>
  )
}

function JobActions({ job, busy, onJob }: { job?: CatalogJob; busy?: boolean; onJob?: (verb: JobVerb, job: CatalogJob) => void }) {
  if (!job || !onJob) return null
  const verb: JobVerb | null = job.can_stop ? 'stop' : job.can_resume ? 'resume' : null
  if (!verb) return null
  return (
    <span className="flex items-center justify-end gap-1">
      {job.can_pause && <Button size="sm" variant="ghost" disabled={busy} onClick={(e) => { e.stopPropagation(); onJob('pause', job) }} title="Pause the launch">Pause</Button>}
      <Button size="sm" variant={verb === 'stop' ? 'danger' : 'default'} disabled={busy} onClick={(e) => { e.stopPropagation(); onJob(verb, job) }}>{verb === 'stop' ? 'Stop' : 'Resume'}</Button>
    </span>
  )
}

function RunRow({ run, job, indent, selectable, selected, onSelect, onResume, onJob, busy }: {
  run: RunView
  job?: CatalogJob
  indent?: boolean
} & Omit<RunListProps, 'launches' | 'expanded' | 'header' | 'empty'>) {
  const raw = run.raw
  const title = useGameTitle()
  const { name, provider } = modelParts(run.model)
  const progress = run.progress
  return (
    <div className={cx(COLUMNS, 'px-4 py-2.5 hover:bg-hover', indent && 'bg-sunken/60', selected?.has(run.id) && 'bg-accent-soft')}>
      <span>
        {selectable && <input type="checkbox" checked={selected?.has(run.id) ?? false} onChange={(e) => onSelect?.(run.id, e.target.checked)} aria-label={`Select ${run.id}`} className="accent-[var(--fg)]" />}
      </span>
      <Link to={runHref(run.id)} className={cx('flex min-w-0 items-center gap-3 text-fg hover:no-underline', indent && 'pl-5')}>
        <GameThumb gameId={run.game} size={indent ? 26 : 32} />
        <span className="min-w-0">
          <span className="block truncate text-[13.5px] font-semibold">{title(run.game)}</span>
          <span className="block truncate text-[11.5px] text-faint">{run.variant}{run.worldModel && run.worldModel !== 'not-recorded' ? ` · ${run.worldModel}` : ''} · {shortTime(run.started)}</span>
        </span>
      </Link>
      <LevelPips levels={run.outcome.score} total={run.outcome.total} solved={run.outcome.tone === 'solved'} size="sm" />
      <HarnessChip harness={run.harness} legacy={run.legacy} className="justify-self-start" />
      <span className="min-w-0" title={run.model}>
        <span className="block truncate text-[13px]">{name}</span>
        <span className="block truncate text-[11px] text-faint">{[provider, run.effort].filter((x) => x && x !== '—').join(' · ')}</span>
      </span>
      <span className="text-[12px] whitespace-nowrap tabular-nums text-muted" title={`${progress.used ?? '?'} of ${progress.budget ?? '?'} ${progress.unit}`}>
        {progress.used === null && !progress.budget ? <span className="text-faint">–</span> : (
          <>{progress.used ?? '–'}{progress.budget ? <span className="text-faint">/{progress.budget}</span> : null} <span className="text-[11px] text-faint">{progress.unit === 'actions' ? 'act' : 'eval'}</span></>
        )}
      </span>
      <span className="min-w-0">
        <StatusDot status={run.process} />
        <span className="block truncate text-[11px] text-faint" title={raw.failure_reason ?? undefined}>{raw.failure_reason ? 'needs attention' : relativeTime(run.activity)}</span>
      </span>
      <RunId id={run.id} className="max-w-full" />
      <span className="flex justify-end">
        {raw.resumable && !raw.resumed_as && onResume ? <Button size="sm" onClick={() => onResume(run.id)}>{run.kind === 'avo' ? 'Resume' : 'Continue'}</Button>
          : raw.resumed_as ? <Link to={runHref(raw.resumed_as)} className="text-[12px] text-muted">continued →</Link>
            : !indent ? <JobActions job={job} busy={busy} onJob={onJob} /> : null}
      </span>
    </div>
  )
}

function GroupRow({ launch, defaultOpen, selectable, selected, onSelect, onResume, onJob, busy }: { launch: Launch; defaultOpen: boolean } & Omit<RunListProps, 'launches' | 'expanded' | 'header' | 'empty'>) {
  const [open, setOpen] = useState(defaultOpen)
  const title = useGameTitle()
  const job = launch.job
  const status = job ? processStatus({ status: job.status, status_source: job.can_stop ? 'Batch worker heartbeat' : 'Saved batch record', needs_assistance: job.needs_assistance }) : null
  const games = [...new Set(launch.runs.map((r) => r.game))]
  const solved = launch.runs.filter((r) => r.outcome.tone === 'solved').length
  const running = launch.runs.filter((r) => r.process.tone === 'running').length
  const models = launch.models.map((m) => modelParts(m).name)
  return (
    <div>
      <div className={cx(COLUMNS, 'cursor-pointer px-4 py-2.5 hover:bg-hover')} onClick={() => setOpen(!open)} role="button" aria-expanded={open}>
        <span className="text-[11px] text-faint">{open ? '▾' : '▸'}</span>
        <span className="flex min-w-0 items-center gap-3">
          <span className="flex shrink-0 -space-x-2.5">
            {games.slice(0, 3).map((g) => <GameThumb key={g} gameId={g} size={32} className="ring-2 ring-panel" />)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] font-semibold" title={launch.id}>{launch.label}</span>
            <span className="block truncate text-[11.5px] text-faint">
              {launch.runs.length} runs · {games.length === 1 ? title(games[0]) : `${games.length} games`} · {launch.variants.join(' / ')} · {shortTime(launch.started)}
            </span>
          </span>
        </span>
        <span className="text-[12.5px] tabular-nums" title="Runs whose solver solved the game">
          <span className="font-semibold">{solved}</span><span className="text-faint">/{launch.runs.length} solved</span>
        </span>
        <span className="flex min-w-0 items-center gap-1">
          <HarnessChip harness={launch.harnesses[0]} legacy={launch.runs.every((r) => r.legacy)} />
          {launch.harnesses.length > 1 && <span className="text-[11px] text-faint" title={launch.harnesses.join(', ')}>+{launch.harnesses.length - 1}</span>}
        </span>
        <span className="min-w-0 truncate text-[12.5px] text-muted" title={launch.models.join(', ')}>{models.slice(0, 2).join(', ')}{models.length > 2 ? ` +${models.length - 2}` : ''}</span>
        <span className="truncate text-[11.5px] text-faint" title={launch.budget}>{launch.budget || '–'}</span>
        <span className="min-w-0">
          {status ? <StatusDot status={status} /> : <span className="text-[12px] text-faint">–</span>}
          {running > 0 && <span className="block text-[11px] text-faint">{running} running</span>}
        </span>
        <span onClick={(e) => e.stopPropagation()} className="min-w-0"><RunId id={launch.id} className="max-w-full" /></span>
        <span onClick={(e) => e.stopPropagation()}><JobActions job={job} busy={busy} onJob={onJob} /></span>
      </div>
      {open && (
        <div className="divide-y divide-line border-t border-line">
          {launch.runs.map((run) => <RunRow key={run.id} run={run} indent {...{ selectable, selected, onSelect, onResume, busy }} />)}
        </div>
      )}
    </div>
  )
}
