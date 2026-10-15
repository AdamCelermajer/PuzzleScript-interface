import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ArtifactView } from '../components/BoardArtifacts'
import { Markdown } from '../components/Markdown'
import { Button, Card, Empty, ErrorBox, Input, Loading, Notice, Tag, cx } from '../components/ui'
import {
  BOARD_STATUSES, MEETING_DATE, STATUS_LABEL, bullets, cardText, countdownText, fileUrl, isUrl, newCardText, oneLine, slugify,
  type BoardCard, type BoardLink, type BoardStatus,
} from '../lib/board'
import { runHref } from '../lib/runs'

interface BoardList {
  cards: BoardCard[]
  errors: { file: string; error: string }[]
}

const STATUS_DOT: Record<BoardStatus, string> = { todo: 'border border-faint', 'in-progress': 'bg-run', blocked: 'bg-bad', done: 'bg-ok' }

function useBoard() {
  return useQuery({ queryKey: ['board'], queryFn: ({ signal }) => api.get<BoardList>('/board', signal) })
}

function usePatchCard() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ slug, ...patch }: { slug: string; status?: BoardStatus; order?: number }) => api.patch<BoardCard>(`/board/${encodeURIComponent(slug)}`, patch),
    onSuccess: (card) => {
      client.setQueryData<BoardList>(['board'], (old) => old && { ...old, cards: old.cards.map((c) => (c.slug === card.slug ? card : c)) })
      client.setQueryData(['board-card', card.slug], card)
    },
  })
}

export function StatusBadge({ status }: { status: BoardStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] whitespace-nowrap text-muted">
      <span className={cx('inline-block h-2 w-2 rounded-full', STATUS_DOT[status])} />
      {STATUS_LABEL[status]}
    </span>
  )
}

function MeetingChip() {
  const date = new Date(`${MEETING_DATE}T12:00:00`)
  const label = date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel px-3 py-1.5 text-[13px] shadow-[var(--shadow)]">
      <span className="section-label !text-[10.5px]">Meeting</span>
      <span className="font-semibold">{label}</span>
      <span className="text-muted">· {countdownText(MEETING_DATE)}</span>
    </span>
  )
}

export function BoardView() {
  const board = useBoard()
  const patch = usePatchCard()
  const navigate = useNavigate()
  const [dragging, setDragging] = useState<string | null>(null)
  const [over, setOver] = useState<BoardStatus | null>(null)
  const cards = board.data?.cards ?? []
  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] leading-tight font-semibold tracking-[-0.02em]">Board</h1>
          <p className="mt-1 text-[13.5px] text-muted">Research questions and their current answers · docs/board/ · drag a card to change its status</p>
        </div>
        <div className="flex items-center gap-2">
          <MeetingChip />
          <Link to="/board/new"><Button>New card</Button></Link>
          <Link to="/board/present"><Button variant="primary" disabled={!cards.length}>Present</Button></Link>
        </div>
      </header>
      {board.data?.errors.map((e) => <Notice key={e.file} tone="warn">{e.file}: {e.error}</Notice>)}
      {patch.error ? <ErrorBox error={patch.error} /> : null}
      {board.isLoading ? <Loading label="Reading the board…" /> : board.error ? <ErrorBox error={board.error} retry={() => board.refetch()} /> : !cards.length ? (
        <div className="rounded-xl border border-dashed border-line-strong"><Empty title="No cards yet"><Link to="/board/new">Add the first question.</Link></Empty></div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {BOARD_STATUSES.map((status) => {
            const column = cards.filter((c) => c.status === status)
            return (
              <section
                key={status}
                onDragOver={(e) => { e.preventDefault(); setOver(status) }}
                onDragLeave={() => setOver((s) => (s === status ? null : s))}
                onDrop={(e) => {
                  e.preventDefault()
                  setOver(null)
                  const slug = e.dataTransfer.getData('text/plain')
                  const card = cards.find((c) => c.slug === slug)
                  if (card && card.status !== status) patch.mutate({ slug, status })
                }}
                className={cx('flex min-h-40 flex-col gap-2 rounded-xl border p-2 transition-colors', over === status ? 'border-fg/40 bg-hover' : 'border-transparent bg-sunken/60')}
              >
                <div className="flex items-center justify-between px-1.5 pt-1">
                  <StatusBadge status={status} />
                  <span className="text-[11.5px] text-faint">{column.length}</span>
                </div>
                {column.map((card) => (
                  <article
                    key={card.slug}
                    draggable
                    onDragStart={(e) => { e.dataTransfer.setData('text/plain', card.slug); setDragging(card.slug) }}
                    onDragEnd={() => setDragging(null)}
                    onClick={() => navigate(`/board/${card.slug}`)}
                    className={cx('cursor-pointer rounded-lg border border-line bg-panel p-3 shadow-[var(--shadow)] hover:border-line-strong', dragging === card.slug && 'opacity-50')}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-[13.5px] leading-snug font-semibold">{card.title}</h3>
                      <span className="shrink-0 text-[11px] text-faint tabular-nums">#{card.order}</span>
                    </div>
                    {card.sections.current_answer && <p className="mt-1.5 line-clamp-3 text-[12.5px] leading-snug text-muted">{oneLine(card.sections.current_answer, 220)}</p>}
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-faint">
                      {card.due && <span className="font-medium text-warn">due {card.due} · {countdownText(card.due)}</span>}
                      {card.links.length > 0 && <span>{card.links.length} link{card.links.length === 1 ? '' : 's'}</span>}
                      {card.runs.length > 0 && <span>{card.runs.length} run{card.runs.length === 1 ? '' : 's'}</span>}
                      {card.artifact && <span>{card.artifact_exists ? 'artifact' : 'artifact pending'}</span>}
                      {card.threads.map((t) => <span key={t}>#{t}</span>)}
                    </div>
                  </article>
                ))}
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function BoardCardView() {
  const { slug = '' } = useParams()
  const card = useQuery({ queryKey: ['board-card', slug], queryFn: ({ signal }) => api.get<BoardCard>(`/board/${encodeURIComponent(slug)}`, signal) })
  const patch = usePatchCard()
  const [editing, setEditing] = useState(false)
  const [doc, setDoc] = useState<BoardLink | null>(null)
  const c = card.data
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-5">
      <Link to="/board" className="text-[12px] text-muted">← Board</Link>
      {card.isLoading ? <Loading /> : card.error ? <ErrorBox error={card.error} /> : c && (editing ? <CardEditor slug={c.slug} initial={cardText(c)} onDone={() => setEditing(false)} /> : (
        <>
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-3"><StatusBadge status={c.status} /><span className="text-[12px] text-faint">#{c.order}</span>{c.due && <span className="text-[12px] font-medium text-warn">due {c.due} · {countdownText(c.due)}</span>}</div>
              <h1 className="mt-1 text-[26px] leading-tight font-semibold tracking-[-0.02em]">{c.title}</h1>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={() => setEditing(true)}>Edit</Button>
              <Link to={`/board/present?card=${c.slug}`}><Button variant="primary">Present from here</Button></Link>
            </div>
          </header>
          <div className="flex flex-wrap gap-1.5">
            {BOARD_STATUSES.map((s) => (
              <Button key={s} size="sm" variant={c.status === s ? 'primary' : 'default'} disabled={patch.isPending} onClick={() => c.status !== s && patch.mutate({ slug: c.slug, status: s })}>{STATUS_LABEL[s]}</Button>
            ))}
          </div>
          {patch.error ? <ErrorBox error={patch.error} /> : null}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <Card bodyClass="flex flex-col gap-4 p-5">
              {([['Question', c.sections.question], ['Current answer', c.sections.current_answer], ['Evidence', c.sections.evidence], ['Next', c.sections.next]] as const).map(([name, text]) => (
                <section key={name}>
                  <div className="section-label mb-1">{name}</div>
                  <Markdown className="text-[14px]">{text || '—'}</Markdown>
                </section>
              ))}
            </Card>
            <div className="flex flex-col gap-4">
              <Card title={`Links (${c.links.length})`}>
                {c.links.length ? (
                  <ul className="flex flex-col gap-1.5 text-[13px]">
                    {c.links.map((l) => (
                      <li key={l.path_or_url} className="min-w-0">
                        {isUrl(l.path_or_url) || l.path_or_url.endsWith('.pdf')
                          ? <a className="link" href={isUrl(l.path_or_url) ? l.path_or_url : fileUrl(l.path_or_url)} target="_blank" rel="noreferrer">{l.label} ↗</a>
                          : <button type="button" className="link text-left hover:underline" onClick={() => setDoc(l)}>{l.label}</button>}
                        <div className="truncate font-mono text-[11px] text-faint" title={l.path_or_url}>{l.path_or_url}</div>
                      </li>
                    ))}
                  </ul>
                ) : <span className="text-[12.5px] text-faint">No links.</span>}
              </Card>
              {(c.runs.length > 0 || c.threads.length > 0) && (
                <Card title="Runs & threads">
                  <div className="flex flex-col gap-1.5 text-[12.5px]">
                    {c.runs.map((r) => <Link key={r} to={runHref(r)} className="truncate font-mono text-[11.5px]" title={r}>{r}</Link>)}
                    <div className="flex flex-wrap gap-1">{c.threads.map((t) => <Link key={t} to={`/diary?thread=${t}`}><Tag>{t}</Tag></Link>)}</div>
                  </div>
                </Card>
              )}
            </div>
          </div>
          {c.artifact && (
            <Card title={<>Artifact <span className="ml-2 font-mono text-[11.5px] font-normal text-faint">{c.artifact}</span></>}>
              <ArtifactView card={c} />
            </Card>
          )}
          {doc && <DocModal link={doc} onClose={() => setDoc(null)} />}
        </>
      ))}
    </div>
  )
}

function DocModal({ link, onClose }: { link: BoardLink; onClose: () => void }) {
  const doc = useQuery({ queryKey: ['board-doc', link.path_or_url], queryFn: ({ signal }) => api.text(fileUrl(link.path_or_url), signal), retry: false })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex justify-center bg-black/40 p-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="flex w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div className="min-w-0"><div className="font-semibold">{link.label}</div><div className="truncate font-mono text-[11px] text-faint">{link.path_or_url}</div></div>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-5">
          {doc.isLoading ? <Loading /> : doc.error ? <Notice tone="warn">{(doc.error as Error).message.includes('not found') || (doc.error as Error).message.includes('404') ? 'This document has not been written yet.' : (doc.error as Error).message}</Notice>
            : link.path_or_url.endsWith('.md') ? <Markdown className="text-[14px]">{doc.data ?? ''}</Markdown>
              : <pre className="text-[12px] whitespace-pre-wrap">{doc.data}</pre>}
        </div>
      </div>
    </div>
  )
}

/** Raw markdown editor with live preview (same style as the Diary editor). */
function CardEditor({ slug, initial, onDone }: { slug?: string; initial: string; onDone: (slug: string) => void }) {
  const client = useQueryClient()
  const [text, setText] = useState(initial)
  const [newSlug, setNewSlug] = useState('')
  const target = slug ?? (newSlug || slugify(/^title:\s*"?(.*?)"?\s*$/m.exec(text)?.[1] ?? 'card'))
  const save = useMutation({
    mutationFn: () => api.put<{ created: boolean; card: BoardCard }>(`/board/${encodeURIComponent(target)}`, { text }),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['board'] })
      client.setQueryData(['board-card', result.card.slug], result.card)
      onDone(result.card.slug)
    },
  })
  const body = text.replace(/\r\n/g, '\n').replace(/^---\n[\s\S]*?\n---\n?/, '')
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-[13px] text-muted">Front matter + sections <span className="font-mono">## Question / ## Current answer / ## Evidence / ## Next</span>. Ctrl+Enter saves.</div>
        <div className="flex items-center gap-2">
          {!slug && <Input value={newSlug} onChange={(e) => setNewSlug(e.target.value)} placeholder={target} className="w-56 font-mono text-[12px]" />}
          {slug && <Button variant="ghost" onClick={() => onDone(slug)}>Cancel</Button>}
          <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</Button>
        </div>
      </div>
      {save.error ? <ErrorBox error={save.error} /> : null}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); save.mutate() } }}
          spellCheck
          className="min-h-[65vh] rounded-lg border border-line bg-panel p-3 font-mono text-[12.5px] leading-[1.55] focus:border-line-strong focus:outline-none"
        />
        <Card className="min-h-[65vh]"><Markdown className="text-[13.5px]">{body}</Markdown></Card>
      </div>
      <div className="text-[11.5px] text-faint">Saved to docs/board/{target}.md</div>
    </div>
  )
}

export function BoardNewView() {
  const board = useBoard()
  const navigate = useNavigate()
  if (board.isLoading) return <Loading />
  const order = Math.max(0, ...(board.data?.cards ?? []).map((c) => c.order)) + 1
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-4">
      <Link to="/board" className="text-[12px] text-muted">← Board</Link>
      <h1 className="text-[26px] font-semibold tracking-[-0.02em]">New card</h1>
      <CardEditor initial={newCardText('New research question', order)} onDone={(slug) => navigate(`/board/${slug}`)} />
    </div>
  )
}

// ---------------------------------------------------------------- present mode

/** Full-screen slides, one card per slide in `order`; arrows/space/PageDown navigate, Esc exits, Export PDF prints. */
export function BoardPresentView() {
  const board = useBoard()
  const navigate = useNavigate()
  const cards = (board.data?.cards ?? []).slice().sort((a, b) => a.order - b.order)
  const start = new URLSearchParams(window.location.search).get('card')
  const [index, setIndex] = useState(0)
  useEffect(() => {
    if (start && cards.length) setIndex(Math.max(0, cards.findIndex((c) => c.slug === start)))
  }, [start, cards.length]) // eslint-disable-line react-hooks/exhaustive-deps
  const exit = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined)
    navigate('/board')
  }, [navigate])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); setIndex((i) => Math.min(cards.length - 1, i + 1)) }
      if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key)) { e.preventDefault(); setIndex((i) => Math.max(0, i - 1)) }
      if (e.key === 'Home') setIndex(0)
      if (e.key === 'End') setIndex(cards.length - 1)
      if (e.key === 'Escape' && !document.fullscreenElement) exit()
      if (e.key.toLowerCase() === 'f') document.documentElement.requestFullscreen?.().catch(() => undefined)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cards.length, exit])
  // Esc first leaves browser full screen; a second Esc (handled above) leaves present mode.
  if (board.isLoading) return <div className="fixed inset-0 z-50 grid place-items-center bg-bg"><Loading /></div>
  const card = cards[index]
  return (
    <div className="present-root fixed inset-0 z-50 flex flex-col bg-bg text-fg">
      <div className="present-chrome flex items-center justify-between gap-3 border-b border-line px-8 py-3 text-[13px] text-muted">
        <span><span className="font-semibold text-fg">Research proposal progress</span> · Meeting {new Date(`${MEETING_DATE}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
        <span className="flex items-center gap-2">
          <span className="tabular-nums">{cards.length ? index + 1 : 0} / {cards.length}</span>
          <Button size="sm" variant="ghost" onClick={() => setIndex(Math.max(0, index - 1))} disabled={index === 0}>←</Button>
          <Button size="sm" variant="ghost" onClick={() => setIndex(Math.min(cards.length - 1, index + 1))} disabled={index >= cards.length - 1}>→</Button>
          <Button size="sm" onClick={() => document.documentElement.requestFullscreen?.().catch(() => undefined)}>Full screen (F)</Button>
          <Button size="sm" onClick={() => window.print()}>Export PDF</Button>
          <Button size="sm" variant="ghost" onClick={exit}>Exit (Esc)</Button>
        </span>
      </div>
      <div className="present-screen min-h-0 flex-1 overflow-auto">
        {card ? <Slide card={card} index={index} total={cards.length} /> : <Empty title="No cards to present" />}
      </div>
      <div className="present-chrome h-1 bg-line"><div className="h-full bg-fg transition-all" style={{ width: `${cards.length ? ((index + 1) / cards.length) * 100 : 0}%` }} /></div>
      {/* Print: every slide, one A4 landscape page each. */}
      <div className="present-print">
        {cards.map((c, i) => <Slide key={c.slug} card={c} index={i} total={cards.length} print />)}
      </div>
    </div>
  )
}

function Slide({ card, index, total, print }: { card: BoardCard; index: number; total: number; print?: boolean }) {
  const evidence = bullets(card.sections.evidence)
  const next = bullets(card.sections.next)
  return (
    <section className={cx('slide mx-auto flex max-w-[1400px] flex-col gap-7 px-14 py-10', print && 'slide-print')}>
      <div className="flex items-center gap-4 text-[15px] text-muted">
        <span className="tabular-nums">{index + 1} / {total}</span>
        <StatusBadge status={card.status} />
        {card.due && <span className="font-medium text-warn">due {card.due}</span>}
      </div>
      <h1 className="text-[44px] leading-[1.1] font-semibold tracking-[-0.025em]">{card.title}</h1>
      {card.sections.question && <p className="max-w-[60ch] text-[22px] leading-snug text-muted">{card.sections.question}</p>}
      <div className="rounded-2xl border border-line bg-panel px-7 py-5">
        <div className="section-label mb-2 !text-[12px]">Current answer</div>
        <Markdown className="text-[24px] leading-snug">{card.sections.current_answer || '—'}</Markdown>
      </div>
      {card.artifact && <div className="slide-artifact"><ArtifactView card={card} large /></div>}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        {evidence.length > 0 && (
          <div>
            <div className="section-label mb-2 !text-[12px]">Evidence</div>
            <ul className="flex list-disc flex-col gap-1.5 pl-6 text-[19px] leading-snug">{evidence.map((e, i) => <li key={i}><Markdown className="inline">{e}</Markdown></li>)}</ul>
          </div>
        )}
        {next.length > 0 && (
          <div>
            <div className="section-label mb-2 !text-[12px]">Next</div>
            <ul className="flex list-disc flex-col gap-1.5 pl-6 text-[19px] leading-snug">{next.map((e, i) => <li key={i}><Markdown className="inline">{e}</Markdown></li>)}</ul>
          </div>
        )}
      </div>
    </section>
  )
}
