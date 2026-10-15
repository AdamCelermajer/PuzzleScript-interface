import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useBenchmarks } from '../api/hooks'
import type { BenchmarkDetail, BenchmarkGame, BenchmarkList, PlayFrame } from '../api/types'
import { GridCanvas, PixelImage, toGrid } from '../components/Frame'
import { Button, Empty, ErrorBox, Field, Input, Loading, Notice, PageHeader, Pill, Pre, Select, Tabs, Tag, cx } from '../components/ui'
import { dateTime, gameName } from '../lib/format'
import { runHref } from '../lib/runs'
import { benchmarkMatches, solveRateText, type BenchmarkFilters } from '../lib/benchmarks'

const TIERS = ['easy', 'medium', 'hard', 'none']

export function BenchmarksView() {
  const list = useBenchmarks()
  const { gameId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const filters: BenchmarkFilters = {
    tier: params.get('tier') ?? '',
    tags: params.getAll('tag'),
    collection: params.get('collection') ?? '',
    status: params.get('status') ?? 'playable',
    review: params.get('review') ?? '',
    q: params.get('q') ?? '',
  }
  const update = (mutate: (p: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next, { replace: true })
  }
  const setOne = (key: string, value: string) => update((p) => (value ? p.set(key, value) : p.delete(key)))
  const toggleTag = (tag: string) => update((p) => {
    const tags = p.getAll('tag')
    p.delete('tag')
    for (const t of tags.includes(tag) ? tags.filter((x) => x !== tag) : [...tags, tag]) p.append('tag', t)
  })

  const data = list.data
  const games = useMemo(() => (data?.games ?? []).filter((g) => benchmarkMatches(g, filters)), [data, params]) // eslint-disable-line react-hooks/exhaustive-deps
  const harnesses = useMemo(() => [...new Set((data?.games ?? []).flatMap((g) => Object.keys(g.measured.by_harness)))].sort(), [data])
  const collections = useMemo(() => [...new Set((data?.games ?? []).flatMap((g) => g.collections))].sort(), [data])
  const drafts = (data?.games ?? []).filter((g) => g.tags_status === 'draft').length
  const open = (id: string) => navigate(`/benchmarks/${encodeURIComponent(id)}?${params.toString()}`)

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Benchmarks"
        subtitle={data ? `${data.count} games in benchmark/games.json · solve rates computed live from the run catalog` : 'Game metadata, tags and measured solve rates'}
        actions={drafts > 0 && <Button variant={filters.review ? 'primary' : 'default'} onClick={() => setOne('review', filters.review ? '' : 'draft')}>Review queue · {drafts} draft</Button>}
      />
      {data?.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Input value={filters.q} onChange={(e) => setOne('q', e.target.value)} placeholder="Search title, id, summary, notes…" className="w-64" />
          <Select value={filters.tier} onChange={(e) => setOne('tier', e.target.value)}>
            <option value="">Any tier</option>
            {TIERS.map((t) => <option key={t} value={t}>{t === 'none' ? 'No tier' : t}</option>)}
          </Select>
          <Select value={filters.collection} onChange={(e) => setOne('collection', e.target.value)}>
            <option value="">Any collection</option>
            {collections.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Select value={filters.status} onChange={(e) => setOne('status', e.target.value === 'playable' ? '' : e.target.value || 'any')}>
            <option value="playable">Playable</option>
            <option value="excluded">Excluded</option>
            <option value="any">Any status</option>
          </Select>
          <Select value={filters.review} onChange={(e) => setOne('review', e.target.value)}>
            <option value="">Any tag review</option>
            <option value="draft">Draft tags (review queue)</option>
            <option value="reviewed">Reviewed tags</option>
            <option value="none">No tags</option>
          </Select>
          <span className="ml-auto text-[12px] text-muted">{games.length} shown</span>
        </div>
        {data && <TagFilter vocabulary={data.tag_vocabulary} definitions={data.tag_definitions} selected={filters.tags} onToggle={toggleTag} />}
      </div>
      <div className="grid grid-cols-1 gap-4" style={gameId ? { gridTemplateColumns: 'minmax(0,1fr) minmax(460px,44%)' } : undefined}>
        <div className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel">
          {list.isLoading ? <Loading label="Loading benchmark metadata…" /> : list.error ? <div className="p-3"><ErrorBox error={list.error} retry={() => list.refetch()} /></div> : !games.length ? (
            <Empty title="No game matches these filters" />
          ) : (
            <div className="max-h-[calc(100vh-270px)] overflow-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Game</th><th>Tier</th><th>Levels</th><th>Tags</th><th>BFS depth</th>
                    {!gameId && harnesses.map((h) => <th key={h} title="Solved runs / runs with artifacts">{h}</th>)}
                    {gameId && <th>Solved</th>}
                  </tr>
                </thead>
                <tbody>
                  {games.map((g) => (
                    <tr key={g.game_id} className={cx(g.game_id === gameId && 'selected')} style={{ cursor: 'pointer' }} onClick={() => open(g.game_id)}>
                      <td className="max-w-72">
                        <div className="flex items-center gap-1.5"><span className="font-medium">{g.title}</span>{g.status === 'excluded' && <Pill tone="neutral">excluded</Pill>}</div>
                        <div className="truncate text-[11.5px] text-muted" title={g.summary}>{g.summary || <span className="font-mono text-faint">{g.game_id}</span>}</div>
                      </td>
                      <td className="whitespace-nowrap">{g.tier ?? <span className="text-faint">—</span>}{g.tier_source && <div className="text-[11px] text-faint">{g.tier_source}</div>}</td>
                      <td className="text-muted">{g.levels ?? '—'}</td>
                      <td className="max-w-72">
                        <div className="flex flex-wrap gap-1">
                          {[...g.tags.mechanics, ...g.tags.properties].slice(0, gameId ? 3 : 6).map((t) => <Tag key={t} title={data?.tag_definitions[t]}>{t}</Tag>)}
                          {g.tags_status === 'draft' && <span className="text-[11px] text-warn" title="Drafted by a model; not yet reviewed">draft</span>}
                        </div>
                      </td>
                      <td className="text-muted">{g.bfs ? (g.bfs.solved ? g.bfs.depth ?? 'solved' : 'unsolved') : '—'}</td>
                      {!gameId && harnesses.map((h) => {
                        const m = g.measured.by_harness[h]
                        return <td key={h} className="text-[12px] whitespace-nowrap tabular-nums">{m ? <span className={m.solved_runs ? 'text-ok' : 'text-muted'}>{m.solved_runs}/{m.runs}</span> : <span className="text-faint">—</span>}</td>
                      })}
                      {gameId && <td className="whitespace-nowrap text-[12px] tabular-nums text-muted" title={solveRateText(g)}>{g.measured.runs ? <span className={g.measured.solved_runs ? 'text-ok' : ''}>{g.measured.solved_runs}/{g.measured.runs}</span> : '—'}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {gameId && data && <BenchmarkDrawer key={gameId} gameId={gameId} list={data} onClose={() => navigate(`/benchmarks?${params.toString()}`)} />}
      </div>
    </div>
  )
}

function TagFilter({ vocabulary, definitions, selected, onToggle }: { vocabulary: BenchmarkList['tag_vocabulary']; definitions: Record<string, string>; selected: string[]; onToggle: (t: string) => void }) {
  const [open, setOpen] = useState(selected.length > 0)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1">
        <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? '▾' : '▸'} Tags{selected.length ? ` (${selected.length}, all required)` : ''}</Button>
        {!open && selected.map((t) => <Tag key={t} active onClick={() => onToggle(t)}>{t} ×</Tag>)}
      </div>
      {open && (['mechanics', 'properties'] as const).map((kind) => (
        <div key={kind} className="flex flex-wrap items-center gap-1">
          <span className="w-20 text-[11.5px] text-faint">{kind}</span>
          {vocabulary[kind].map((t) => <Tag key={t} title={definitions[t]} active={selected.includes(t)} onClick={() => onToggle(t)}>{t}</Tag>)}
        </div>
      ))}
    </div>
  )
}

type DrawerTab = 'overview' | 'play' | 'rules' | 'runs'

function BenchmarkDrawer({ gameId, list, onClose }: { gameId: string; list: BenchmarkList; onClose: () => void }) {
  const [tab, setTab] = useState<DrawerTab>('overview')
  const detail = useQuery({ queryKey: ['benchmark', gameId], queryFn: ({ signal }) => api.get<BenchmarkDetail>(`/benchmarks/${encodeURIComponent(gameId)}`, signal) })
  const game = detail.data
  return (
    <aside className="flex min-w-0 flex-col gap-3 self-start rounded-lg border border-line bg-panel p-4 xl:sticky xl:top-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[16px] font-semibold">{game?.title ?? gameName(gameId)}</h2>
          <div className="font-mono text-[11.5px] text-muted">{gameId}</div>
          {game?.author && <div className="text-[12px] text-muted">by {game.author}{game.homepage ? ` · ${game.homepage}` : ''}</div>}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">✕</Button>
      </div>
      <Tabs<DrawerTab> value={tab} onChange={setTab} tabs={[
        { id: 'overview', label: 'Overview' },
        { id: 'play', label: 'Play', hidden: game ? game.status !== 'playable' || game.arc_catalog === false : false },
        { id: 'rules', label: 'Rules & levels' },
        { id: 'runs', label: `Runs${game ? ` (${game.runs.length})` : ''}` },
      ]} />
      {detail.isLoading ? <Loading /> : detail.error ? <ErrorBox error={detail.error} /> : game && (
        <>
          {tab === 'overview' && <Overview game={game} list={list} />}
          {tab === 'play' && <Play game={game} />}
          {tab === 'rules' && <Rules game={game} />}
          {tab === 'runs' && <GameRuns game={game} />}
        </>
      )}
    </aside>
  )
}

function Overview({ game, list }: { game: BenchmarkDetail; list: BenchmarkList }) {
  const client = useQueryClient()
  const [tier, setTier] = useState(game.tier ?? '')
  const [summary, setSummary] = useState(game.summary ?? '')
  const [notes, setNotes] = useState(game.notes ?? '')
  const [mechanics, setMechanics] = useState<string[]>(game.tags.mechanics)
  const [properties, setProperties] = useState<string[]>(game.tags.properties)
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<BenchmarkGame>(`/benchmarks/${encodeURIComponent(game.game_id)}`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['benchmarks'] })
      client.invalidateQueries({ queryKey: ['benchmark', game.game_id] })
    },
  })
  const tagsChanged = mechanics.join() !== game.tags.mechanics.join() || properties.join() !== game.tags.properties.join()
  const toggle = (kind: 'mechanics' | 'properties', tag: string) => {
    const [value, set] = kind === 'mechanics' ? [mechanics, setMechanics] : [properties, setProperties]
    set(value.includes(tag) ? value.filter((t) => t !== tag) : [...value, tag])
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2 text-[12.5px]">
        <Fact label="Levels" value={game.levels ?? '—'} />
        <Fact label="Structure" value={game.structure ? `${game.structure.objects} objects · ${game.structure.rule_groups} rule groups` : '—'} />
        <Fact label="BFS" value={game.bfs ? (game.bfs.solved ? `depth ${game.bfs.depth}` : 'unsolved') : 'not searched'} />
        <Fact label="Collections" value={game.collections.join(', ') || '—'} />
        <Fact label="Measured" value={solveRateText(game)} />
        <Fact label="Best levels" value={game.measured.best_levels ?? '—'} />
      </div>
      {game.status === 'excluded' && <Notice tone="warn">Excluded: {game.exclusion_reasons.join('; ') || 'no reason recorded'}</Notice>}
      {save.error && <ErrorBox error={save.error} />}
      {save.isSuccess && <Notice tone="ok">Saved to benchmark/games.json</Notice>}

      <Field label={<>Tier {game.tier_source && <span className="font-normal text-faint">· source {game.tier_source}</span>}</>}>
        <div className="flex gap-2">
          <Select value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="">No tier</option>
            {['easy', 'medium', 'hard'].map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <Button disabled={tier === (game.tier ?? '') || save.isPending} onClick={() => save.mutate({ tier: tier || null })}>Save tier</Button>
        </div>
      </Field>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 text-[12px] font-medium text-muted">
          Tags
          {game.tags_status === 'draft' ? <Pill tone="warn">draft{game.tags_model ? ` · ${game.tags_model}` : ''}</Pill> : game.tags_status === 'reviewed' ? <Pill tone="ok">reviewed</Pill> : <Pill tone="neutral">none</Pill>}
        </div>
        {(['mechanics', 'properties'] as const).map((kind) => (
          <div key={kind} className="flex flex-wrap items-center gap-1">
            <span className="w-20 text-[11.5px] text-faint">{kind}</span>
            {list.tag_vocabulary[kind].map((t) => (
              <Tag key={t} title={list.tag_definitions[t]} active={(kind === 'mechanics' ? mechanics : properties).includes(t)} onClick={() => toggle(kind, t)}>{t}</Tag>
            ))}
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Button variant={game.tags_status === 'draft' && !tagsChanged ? 'primary' : 'default'} disabled={save.isPending || (!tagsChanged && game.tags_status === 'reviewed')} onClick={() => save.mutate({ tags: { mechanics, properties } })}>
            {tagsChanged ? 'Save tags (marks reviewed)' : game.tags_status === 'reviewed' ? 'Tags reviewed' : 'Accept draft as reviewed'}
          </Button>
          {tagsChanged && <Button variant="ghost" onClick={() => { setMechanics(game.tags.mechanics); setProperties(game.tags.properties) }}>Undo</Button>}
        </div>
      </div>

      <Field label="Summary (one line)">
        <div className="flex gap-2">
          <Input value={summary} maxLength={300} onChange={(e) => setSummary(e.target.value)} className="flex-1" />
          <Button disabled={summary === (game.summary ?? '') || save.isPending} onClick={() => save.mutate({ summary })}>Save</Button>
        </div>
      </Field>
      <Field label="Notes">
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} className="rounded-md border border-line-strong bg-panel p-2 text-[13px] focus:border-accent focus:outline-none" />
        <div><Button disabled={notes === (game.notes ?? '') || save.isPending} onClick={() => save.mutate({ notes })}>Save notes</Button></div>
      </Field>
      {game.readme && (
        <Field label="Readme">
          <div className="max-h-48 overflow-auto rounded-md bg-sunken p-2 text-[12.5px] whitespace-pre-wrap">{game.readme}</div>
        </Field>
      )}
    </div>
  )
}

const KEYS: Record<string, string> = { ArrowUp: 'ACTION1', ArrowDown: 'ACTION2', ArrowLeft: 'ACTION3', ArrowRight: 'ACTION4', ' ': 'ACTION5', x: 'ACTION5', z: 'ACTION7', u: 'ACTION7', r: 'RESET' }
const BUTTONS: [string, string][] = [['ACTION1', '↑'], ['ACTION2', '↓'], ['ACTION3', '←'], ['ACTION4', '→'], ['ACTION5', 'Space'], ['ACTION7', 'Undo (z)'], ['RESET', 'Reset (r)']]

function Play({ game }: { game: BenchmarkDetail }) {
  const [frame, setFrame] = useState<PlayFrame | null>(null)
  const [level, setLevel] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [moves, setMoves] = useState(0)
  const session = useRef<string | null>(null)
  const box = useRef<HTMLDivElement>(null)

  const close = () => {
    if (session.current) api.del(`/benchmarks/play/${session.current}`).catch(() => undefined)
    session.current = null
  }
  useEffect(() => close, [])

  const start = async () => {
    close()
    setBusy(true)
    setError(null)
    try {
      const body = level === '' ? {} : { level: Number(level) }
      const result = await api.post<PlayFrame>(`/benchmarks/${encodeURIComponent(game.game_id)}/play`, body)
      session.current = result.session
      setFrame(result)
      setMoves(0)
      box.current?.focus()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  // Keys pressed while a move is in flight are queued (the API allows one move at a time per session).
  const queue = useRef<string[]>([])
  const draining = useRef(false)
  const act = async (action: string) => {
    if (!session.current) return
    if (queue.current.length < 8) queue.current.push(action)
    if (draining.current) return
    draining.current = true
    try {
      while (queue.current.length && session.current) {
        const next = queue.current.shift()!
        try {
          setFrame(await api.post<PlayFrame>(`/benchmarks/play/${session.current}/${next}`))
          setMoves((m) => (next === 'RESET' ? 0 : m + 1))
          setError(null)
        } catch (e) {
          setError(e)
          queue.current = []
        }
      }
    } finally {
      draining.current = false
    }
  }
  const image = frame?.rendered_frame?.data_url
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Start level">
          <Select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="">First level</option>
            {Array.from({ length: game.levels ?? 0 }, (_, i) => <option key={i} value={i}>Level {i + 1}</option>)}
          </Select>
        </Field>
        <Button variant="primary" onClick={start} disabled={busy}>{frame ? 'Restart session' : 'Start playing'}</Button>
        {frame && <span className="text-[12px] text-muted">{frame.state} · levels {frame.levels_completed}/{frame.win_levels} · {moves} moves</span>}
      </div>
      {error ? <ErrorBox error={error} /> : null}
      {frame ? (
        <div
          ref={box}
          tabIndex={0}
          onKeyDown={(e) => {
            const action = KEYS[e.key] ?? KEYS[e.key.toLowerCase()]
            if (action) {
              e.preventDefault()
              act(action)
            }
          }}
          className="flex flex-col items-center gap-3 rounded-md border border-line bg-sunken p-3 outline-none focus:border-accent"
        >
          {image ? <PixelImage src={image} alt={`${game.title} frame`} className="w-full max-w-[520px]" /> : <GridCanvas grid={toGrid(frame.frame)} maxSize={480} />}
          <div className="text-[11.5px] text-faint">Click here, then use arrows, space/x, z (undo) and r (reset).</div>
          <div className="flex flex-wrap justify-center gap-1.5">
            {BUTTONS.map(([action, label]) => <Button key={action} size="sm" disabled={busy} onClick={() => act(action)}>{label}</Button>)}
          </div>
        </div>
      ) : (
        <Empty title="Manual play">Starts a dedicated session on the local ARC service; it never touches campaign sessions.</Empty>
      )}
    </div>
  )
}

function Rules({ game }: { game: BenchmarkDetail }) {
  const levels = game.level_annotations?.levels ?? []
  return (
    <div className="flex flex-col gap-3">
      <Field label={`Reviewed rules · ${game.rules_source}`}>
        {game.reviewed_rules.length ? (
          <ol className="flex flex-col gap-1 text-[12.5px]">{game.reviewed_rules.map((r, i) => <li key={i} className="rounded bg-sunken px-2 py-1">{r}</li>)}</ol>
        ) : <span className="text-[12px] text-faint">No reviewed rules for this game.</span>}
      </Field>
      {levels.length > 0 && (
        <Field label="Level annotations">
          {game.level_annotations.methodology && <div className="text-[11.5px] text-faint">{game.level_annotations.methodology}</div>}
          <Pre className="max-h-72">{JSON.stringify(levels, null, 2)}</Pre>
        </Field>
      )}
      {game.bfs_searches.length > 0 && (
        <Field label="BFS searches">
          <table className="data-table">
            <thead><tr><th>Level</th><th>Status</th><th>Depth</th><th>States</th></tr></thead>
            <tbody>{game.bfs_searches.map((b, i) => <tr key={i}><td>{b.level}</td><td>{b.status}</td><td>{b.depth ?? '—'}</td><td>{b.expanded_states ?? '—'}</td></tr>)}</tbody>
          </table>
        </Field>
      )}
      {game.reference && (
        <Field label={`Reference solutions · ${game.reference.artifact_status ?? ''}`}>
          <div className="text-[12px] text-muted">{game.reference.levels.filter((l) => l.replay_verified).length} / {game.reference.levels.length} levels replay-verified</div>
        </Field>
      )}
    </div>
  )
}

function GameRuns({ game }: { game: BenchmarkDetail }) {
  if (!game.runs.length) return <Empty title="No runs on this game yet"><Link to="/launch">Launch one</Link></Empty>
  const runs = [...game.runs].sort((a, b) => (b.modified ?? 0) - (a.modified ?? 0))
  return (
    <div className="max-h-[60vh] overflow-auto">
      <table className="data-table">
        <thead><tr><th>Run</th><th>Harness</th><th>Model</th><th>Result</th><th>Activity</th></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td className="font-mono text-[11.5px]"><Link to={runHref(r.id!)}>{r.id!.split('/').slice(-2).join('/')}</Link><div className="text-[11px] text-faint">{r.kind === 'avo' ? 'campaign' : r.condition}</div></td>
              <td>{r.harness ?? r.agent_backend}</td>
              <td className="max-w-40 truncate">{r.model}</td>
              <td>{r.solved ? <Pill tone="solved">solved</Pill> : <span className="font-mono text-[12px] text-muted">{r.kind === 'avo' ? r.best_fitness ?? '—' : r.levels ?? '—'}</span>}</td>
              <td className="text-[11.5px] whitespace-nowrap text-muted">{dateTime(r.modified)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="min-w-0"><div className="text-[11px] text-faint">{label}</div><div className="truncate">{value}</div></div>
}
