import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { PixelImage } from '../components/Frame'
import { Button, Card, Empty, ErrorBox, Field, Input, Loading, Notice, Pill, Select, cx } from '../components/ui'

// BFS optimal path (experiement/bfs_solver/web_api.py, prefix /api/optimal-path).
const BASE = '/api/optimal-path'
const ACTIVE = new Set(['starting', 'running', 'stopping'])
const fmt = new Intl.NumberFormat()

interface ReplayFrame {
  action?: string | null
  levelNumber?: number
  totalLevels?: number
  renderedFrame?: { data_url?: string } | null
}

export interface OptimalRun {
  run_id: string
  status: string
  started_at?: string
  error?: string | null
  config?: { game_id?: string; timeout_seconds?: number; max_states?: number }
  progress?: {
    elapsedMs?: number
    timeoutMs?: number
    levelNumber?: number
    totalLevels?: number
    maxDepthDiscovered?: number
    expandedStates?: number
    uniqueStates?: number
    frontierStates?: number
    transitions?: number
    transitionsPerSecond?: number
  }
  result?: {
    solved?: boolean
    status?: string
    reason?: string
    solutionDepth?: number
    levelsSolved?: number
    totalLevels?: number
    failedLevelNumber?: number
    searchMs?: number
    uniqueStates?: number
  } | null
  replay?: ReplayFrame[]
}

/** Readable reason a search ended without a path (same wording as the old page). */
export function failureText(run: OptimalRun): string {
  const timeout = Math.round((run.progress?.timeoutMs ?? (run.config?.timeout_seconds ?? 0) * 1000) / 1000)
  const outcome = run.result?.status || run.status
  const failedAt = run.result?.failedLevelNumber ? ` on level ${run.result.failedLevelNumber} of ${run.result.totalLevels}` : ''
  const messages: Record<string, string> = {
    time_limit: `The ${timeout} second whole-game time limit expired${failedAt}.`,
    state_limit: `The search reached ${fmt.format(run.config?.max_states ?? 0)} unique states${failedAt}.`,
    exhausted: 'The reachable state graph was exhausted without finding a win.',
    unsupported: `This game uses a mechanic the current solver does not support (${run.result?.reason || 'unknown'}).`,
    ineligible: 'This game does not expose a formal PuzzleScript win condition or playable level.',
    cancelled: 'The search was stopped before it found a winning path.',
    failed: run.error || 'The solver could not complete this run.',
  }
  return messages[outcome] ?? messages[run.status] ?? `Search ended: ${outcome}.`
}

export function OptimalPathView() {
  const client = useQueryClient()
  const games = useQuery({ queryKey: ['optimal-games'], queryFn: ({ signal }) => api.get<{ games: { game_id: string; title: string }[] }>(`${BASE}/games`, signal) })
  const [runId, setRunId] = useState<string | null>(null)
  const current = useQuery({
    queryKey: ['optimal-current'],
    queryFn: ({ signal }) => api.get<{ run: OptimalRun | null }>(`${BASE}/runs/current`, signal),
    enabled: runId === null,
  })
  useEffect(() => { if (current.data?.run && runId === null) setRunId(current.data.run.run_id) }, [current.data, runId])
  const run = useQuery({
    queryKey: ['optimal-run', runId],
    enabled: Boolean(runId),
    queryFn: ({ signal }) => api.get<OptimalRun>(`${BASE}/runs/${runId}`, signal),
    refetchInterval: (query) => (query.state.data && ACTIVE.has(query.state.data.status) ? 500 : false),
  })
  const [game, setGame] = useState('')
  const [timeout, setTimeoutSeconds] = useState(60)
  const [maxStates, setMaxStates] = useState(100_000)
  useEffect(() => {
    if (!game && games.data?.games.length) setGame(games.data.games.find((g) => g.game_id === 'ps_sokoban_basic-v1')?.game_id ?? games.data.games[0].game_id)
  }, [games.data, game])

  const start = useMutation({
    mutationFn: () => api.post<OptimalRun>(`${BASE}/runs`, { game_id: game, timeout_seconds: timeout, max_states: maxStates }),
    onSuccess: (r) => { client.setQueryData(['optimal-run', r.run_id], r); setRunId(r.run_id) },
  })
  const stop = useMutation({
    mutationFn: () => api.post<OptimalRun>(`${BASE}/runs/${runId}/stop`),
    onSuccess: (r) => client.setQueryData(['optimal-run', r.run_id], r),
  })
  const data = run.data ?? current.data?.run ?? null
  const active = Boolean(data && ACTIVE.has(data.status))
  const progress = data?.progress ?? {}
  const timeoutMs = progress.timeoutMs ?? timeout * 1000
  const elapsed = data ? (active && data.started_at ? Math.min(timeoutMs, Math.max(progress.elapsedMs ?? 0, Date.now() - Date.parse(data.started_at))) : progress.elapsedMs ?? 0) : 0
  const totalLevels = progress.totalLevels ?? data?.result?.totalLevels ?? 0
  const levelNumber = progress.levelNumber ?? data?.result?.failedLevelNumber ?? totalLevels
  const error = start.error ?? stop.error ?? games.error ?? (run.error instanceof ApiError && run.error.status !== 404 ? run.error : null)

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-4">
      <div>
        <Link to="/tools" className="text-[12px] text-muted">← Tools</Link>
        <h1 className="text-[18px] font-semibold tracking-tight">BFS optimal path</h1>
        <div className="text-[12.5px] text-muted">Breadth-first search through every playable level of a game, then replay of the whole solution.</div>
      </div>
      {error ? <ErrorBox error={error} /> : null}
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Game" className="min-w-72 flex-1">
            <Select value={game} onChange={(e) => setGame(e.target.value)} disabled={active || games.isLoading}>
              {(games.data?.games ?? []).map((g) => <option key={g.game_id} value={g.game_id}>{g.title} ({g.game_id})</option>)}
            </Select>
          </Field>
          <Field label="Time limit (s, whole game)"><Input type="number" min={1} max={600} value={timeout} onChange={(e) => setTimeoutSeconds(Number(e.target.value))} disabled={active} className="w-32" /></Field>
          <Field label="Max unique states"><Input type="number" min={1000} max={1_000_000} step={1000} value={maxStates} onChange={(e) => setMaxStates(Number(e.target.value))} disabled={active} className="w-36" /></Field>
          <Button variant="primary" disabled={active || !game || start.isPending} onClick={() => start.mutate()}>Start search</Button>
          <Button variant="danger" disabled={!active || stop.isPending} onClick={() => stop.mutate()}>Stop</Button>
        </div>
      </Card>

      <Card title="Search progress" actions={<Pill tone={active ? 'running' : data?.status === 'solved' ? 'solved' : data ? 'neutral' : 'queued'} dot={active}>{(data?.status ?? 'idle').replace('_', ' ')}</Pill>}>
        <div className="mb-2 flex items-center gap-3 text-[12.5px]">
          <span className="tabular-nums">{(elapsed / 1000).toFixed(1)}s / {Math.round(timeoutMs / 1000)}s</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken"><div className="h-full bg-accent" style={{ width: `${timeoutMs ? Math.min(100, (elapsed / timeoutMs) * 100) : 0}%` }} /></div>
          <span className="text-muted">{totalLevels ? `Level ${levelNumber} of ${totalLevels}` : 'Waiting to start'}</span>
        </div>
        <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
          {[
            ['Depth reached', progress.maxDepthDiscovered], ['Expanded', progress.expandedStates], ['Unique states', progress.uniqueStates],
            ['Frontier', progress.frontierStates], ['Transitions', progress.transitions], ['Speed /s', Math.round(progress.transitionsPerSecond ?? 0)],
          ].map(([label, value]) => (
            <div key={label as string}><div className="text-[11px] text-faint">{label}</div><div className="text-[15px] font-semibold tabular-nums">{fmt.format(Number(value ?? 0))}</div></div>
          ))}
        </div>
        <div className="mt-2 text-[11.5px] text-faint">Depth is a live counter, not a percentage: the solution depth is unknown until the search reaches a win.</div>
      </Card>

      {current.isLoading && !data ? <Loading /> : !data ? (
        <Card><Empty title="Ready to search">Each level gets a shared-state BFS tree; the time budget covers the whole game.</Empty></Card>
      ) : active ? (
        <Notice>Searching… the frontier is expanding breadth-first. You can leave and return without losing the run.</Notice>
      ) : data.status === 'solved' && data.result?.solved ? (
        <Replay run={data} />
      ) : (
        <Card title="No winning path found"><div className="text-[13px]">{failureText(data)}</div></Card>
      )}
    </div>
  )
}

function Replay({ run }: { run: OptimalRun }) {
  const frames = run.replay ?? []
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  useEffect(() => { setIndex(0); setPlaying(false) }, [run.run_id])
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setIndex((i) => { if (i >= frames.length - 1) { setPlaying(false); return i } return i + 1 }), 500)
    return () => window.clearInterval(timer)
  }, [playing, frames.length])
  const frame = frames[index]
  const result = run.result!
  return (
    <Card title={`${result.solutionDepth}-action whole-game path · replay verified`} actions={<span className="text-[12px] text-muted">{result.levelsSolved} / {result.totalLevels} levels · {((result.searchMs ?? 0) / 1000).toFixed(2)}s · {fmt.format(result.uniqueStates ?? 0)} states</span>}>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_minmax(0,1fr)]">
        <div className="flex flex-col items-center gap-2">
          {frame?.renderedFrame?.data_url ? <PixelImage src={frame.renderedFrame.data_url} alt={`Step ${index}`} className="max-h-[420px] w-auto" /> : <div className="flex h-60 w-80 items-center justify-center rounded bg-sunken text-[12px] text-faint">No rendered frame</div>}
          <div className="flex items-center gap-1.5">
            <Button size="sm" onClick={() => { setPlaying(false); setIndex(Math.max(0, index - 1)) }} disabled={index === 0}>← Prev</Button>
            <Button size="sm" variant="primary" onClick={() => { if (index >= frames.length - 1) setIndex(0); setPlaying(!playing) }}>{playing ? 'Pause' : 'Play'}</Button>
            <Button size="sm" onClick={() => { setPlaying(false); setIndex(Math.min(frames.length - 1, index + 1)) }} disabled={index >= frames.length - 1}>Next →</Button>
          </div>
          <div className="text-[12px] text-muted tabular-nums">{index + 1} / {frames.length} · {frame?.action || 'RESET'} · level {frame?.levelNumber ?? 1} / {frame?.totalLevels ?? 1}</div>
        </div>
        <div className="flex max-h-[480px] flex-wrap content-start gap-1 overflow-auto">
          {frames.map((f, i) => (
            <button key={i} type="button" onClick={() => { setPlaying(false); setIndex(i) }} className={cx('rounded border px-1.5 py-0.5 text-[11px] tabular-nums', i === index ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-fg')}>
              <span className="mr-1 text-faint">{i}</span>{f.action || 'RESET'}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3 text-[11.5px] text-faint">Fast mode solves every playable level in order using semantic state equivalence. Each level path is shortest in its merged state graph, and every displayed action sequence is replay-verified in the real engine.</div>
    </Card>
  )
}
