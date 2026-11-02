import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import type { DiaryEntry, DiaryRunLink, DiaryThread } from '../api/types'
import { Markdown } from '../components/Markdown'
import { Empty, ErrorBox, Loading, Tag, cx } from '../components/ui'
import { fileUrl } from '../lib/board'

/** Diary present mode: the whole research log as slides, oldest first.
 *  Per month: a chapter slide, one slide per entry (plus one per extra figure), then one
 *  "also in <month>" slide for the entries marked `brief`. Images listed in an entry's
 *  `docs` (under docs/) are its figures. Cream or warm dark deck, toggled with T. */

type SlideSpec =
  | { kind: 'overview' }
  | { kind: 'month'; month: string; entries: DiaryEntry[] }
  | { kind: 'entry'; entry: DiaryEntry; figure: number }
  | { kind: 'brief'; month: string; entries: DiaryEntry[] }

type Deck = 'cream' | 'dark'

const IMAGE = /\.(png|jpe?g|gif|webp)$/i
const EMPTY_SECTION = /^\s*(-\s*)?—\s*$/
const DECK_KEY = 'diary.present.deck'
// On screen a section shows its first bullets and a "+N more" button; print shows everything.
const FOUND_SHOWN = 4
const FOUND_BESIDE_FIGURE = 3
const SECTION_SHOWN = 2

const monthOf = (date: string) => date.slice(0, 7)
const monthLabel = (month: string, style: 'long' | 'short' = 'long') => new Date(`${month}-15T12:00:00`).toLocaleDateString(undefined, { month: style, year: style === 'long' ? 'numeric' : undefined })
const dayLabel = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const shortDay = (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const hasText = (s: string) => Boolean(s.trim()) && !EMPTY_SECTION.test(s)
const figuresOf = (entry: DiaryEntry) => entry.docs.filter((d) => IMAGE.test(d) && d.startsWith('docs/'))

/** Top-level bullets of a section; indented continuation lines are joined (as workbench/diary.py does). */
function bulletsOf(section: string): string[] {
  const items: string[] = []
  for (const line of section.split('\n')) {
    const m = line.match(/^[-*]\s+(.*)$/)
    if (m) items.push(m[1].trim())
    else if (items.length && line.trim() && /^\s/.test(line)) items[items.length - 1] += ' ' + line.trim()
    else if (line.trim() && !items.length) items.push(line.trim())
  }
  return items.filter((i) => !['—', '-', '–', ''].includes(i))
}

function formatTokens(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(n < 1e7 ? 1 : 0)}M`
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`
  return String(n)
}

const modelName = (model: string) => model.split('/').pop() ?? model

interface RunStats { runs: number; withTokens: number; tokens: number; output: number; byDate: boolean; models: [string, number][] }

/** An entry's runs: its explicitly linked runs, or else the runs started that day. */
function runStats(runs: DiaryRunLink[]): RunStats {
  const found = runs.filter((r) => r.found)
  const explicit = found.filter((r) => r.linked === 'explicit')
  return statsOf(explicit.length ? explicit : found, !explicit.length)
}

function statsOf(runs: DiaryRunLink[], byDate = false): RunStats {
  const models = new Map<string, number>()
  let tokens = 0, output = 0, withTokens = 0
  for (const r of runs) {
    if (!r.tokens) continue
    withTokens++
    tokens += r.tokens.total
    output += r.tokens.output
    const m = modelName(r.model || 'unknown')
    models.set(m, (models.get(m) ?? 0) + r.tokens.total)
  }
  return { runs: runs.length, withTokens, tokens, output, byDate, models: [...models].sort((a, b) => b[1] - a[1]) }
}

/** Every distinct run across entries, so a run linked twice is counted once. */
function uniqueRuns(entries: DiaryEntry[]): DiaryRunLink[] {
  const seen = new Map<string, DiaryRunLink>()
  for (const e of entries) for (const r of e.runs) if (r.found && !seen.has(r.id)) seen.set(r.id, r)
  return [...seen.values()]
}

function slideTitle(spec: SlideSpec): string {
  if (spec.kind === 'overview') return 'Overview'
  if (spec.kind === 'month') return monthLabel(spec.month)
  if (spec.kind === 'brief') return `Also in ${monthLabel(spec.month, 'short')}`
  const n = figuresOf(spec.entry).length
  return spec.figure > 0 ? `${spec.entry.title} (figure ${spec.figure + 1} of ${n})` : spec.entry.title
}

export function DiaryPresentView() {
  const [params, setParams] = useSearchParams()
  const thread = params.get('thread') ?? ''
  const navigate = useNavigate()
  const entries = useQuery({
    queryKey: ['diary', thread],
    queryFn: ({ signal }) => api.get<{ entries: DiaryEntry[] }>(`/diary${q({ thread })}`, signal),
  })
  const threads = useQuery({
    queryKey: ['diary-threads'],
    queryFn: ({ signal }) => api.get<{ threads: DiaryThread[] }>('/diary/threads', signal),
    staleTime: 60_000,
  })
  const all = useMemo(
    () => [...(entries.data?.entries ?? [])].sort((a, b) => a.date.localeCompare(b.date) || a.slug.localeCompare(b.slug)),
    [entries.data],
  )
  // ?since=meeting: only the entries after the last supervisor meeting; the overview lists what they asked for.
  const sinceMeeting = params.get('since') === 'meeting'
  const meeting = useMemo(() => [...all].reverse().find((e) => e.threads.includes('meetings')), [all])
  const sorted = useMemo(
    () => (sinceMeeting && meeting ? all.filter((e) => e.date > meeting.date) : all),
    [all, sinceMeeting, meeting],
  )
  const slides = useMemo(() => {
    const out: SlideSpec[] = [{ kind: 'overview' }]
    const months = [...new Set(sorted.map((e) => monthOf(e.date)))]
    for (const month of months) {
      const inMonth = sorted.filter((e) => monthOf(e.date) === month)
      out.push({ kind: 'month', month, entries: inMonth })
      for (const entry of inMonth.filter((e) => !e.brief)) {
        const n = Math.max(1, figuresOf(entry).length)
        for (let figure = 0; figure < n; figure++) out.push({ kind: 'entry', entry, figure })
      }
      const brief = inMonth.filter((e) => e.brief)
      if (brief.length) out.push({ kind: 'brief', month, entries: brief })
    }
    return out
  }, [sorted])
  const slideOf = useCallback((slug: string) => slides.findIndex((s) =>
    (s.kind === 'entry' && s.entry.slug === slug && s.figure === 0) || (s.kind === 'brief' && s.entries.some((e) => e.slug === slug))), [slides])
  const monthSlide = useCallback((month: string) => slides.findIndex((s) => s.kind === 'month' && s.month === month), [slides])

  const [index, setIndex] = useState(0)
  const [ready, setReady] = useState(false)
  const [deck, setDeck] = useState<Deck>(() => (localStorage.getItem(DECK_KEY) === 'dark' ? 'dark' : 'cream'))
  const [outline, setOutline] = useState(() => window.innerWidth >= 1600)
  const [zoom, setZoom] = useState<string | null>(null)
  const screen = useRef<HTMLDivElement>(null)

  // Start at ?s=<n> (1-based) or ?entry=<slug>; afterwards keep ?s in the URL so a reload stays put.
  useEffect(() => {
    if (ready || slides.length < 2) return
    const s = Number(params.get('s'))
    const entry = params.get('entry')
    setIndex(s >= 1 && s <= slides.length ? s - 1 : entry ? Math.max(0, slideOf(entry)) : 0)
    setReady(true)
  }, [ready, slides.length]) // eslint-disable-line react-hooks/exhaustive-deps
  // setParams changes identity with every URL change, so it stays out of the deps (it would loop).
  useEffect(() => {
    if (!ready) return
    if (params.get('s') !== String(index + 1) || params.has('entry')) {
      setParams((p) => { const next = new URLSearchParams(p); next.delete('entry'); next.set('s', String(index + 1)); return next }, { replace: true })
    }
    screen.current?.scrollTo({ top: 0 })
  }, [index, ready]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { localStorage.setItem(DECK_KEY, deck) }, [deck])

  const go = useCallback((i: number) => setIndex(Math.max(0, Math.min(slides.length - 1, i))), [slides.length])
  const exit = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined)
    navigate(`/diary${q({ thread })}`)
  }, [navigate, thread])
  const toggleSince = useCallback(() => {
    setIndex(0)
    setParams((p) => {
      const next = new URLSearchParams(p)
      if (next.get('since') === 'meeting') next.delete('since')
      else next.set('since', 'meeting')
      next.set('s', '1')
      return next
    }, { replace: true })
  }, [setParams])
  const jumpMonth = useCallback((dir: 1 | -1) => {
    const starts = slides.map((s, i) => (s.kind === 'month' ? i : -1)).filter((i) => i >= 0)
    const target = dir > 0 ? starts.find((i) => i > index) : [...starts].reverse().find((i) => i < index)
    if (target !== undefined) go(target)
    else go(dir > 0 ? slides.length - 1 : 0)
  }, [slides, index, go])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (zoom) { if (e.key === 'Escape') setZoom(null); return }
      if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); if (e.shiftKey) jumpMonth(1); else go(index + 1) }
      else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key)) { e.preventDefault(); if (e.shiftKey) jumpMonth(-1); else go(index - 1) }
      else if (e.key === 'Home') go(0)
      else if (e.key === 'End') go(slides.length - 1)
      else if (e.key === 'Escape' && !document.fullscreenElement) exit()
      else if (e.key.toLowerCase() === 'f') document.documentElement.requestFullscreen?.().catch(() => undefined)
      else if (e.key.toLowerCase() === 't') setDeck((d) => (d === 'cream' ? 'dark' : 'cream'))
      else if (e.key.toLowerCase() === 'o') setOutline((o) => !o)
      else if (e.key.toLowerCase() === 'm' && meeting) toggleSince()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [slides.length, index, go, jumpMonth, exit, zoom, meeting, toggleSince])

  const shell = (body: ReactNode) => <div className="present-root fixed inset-0 z-50 grid place-items-center bg-bg text-fg" data-deck={deck}>{body}</div>
  if (entries.isLoading) return shell(<Loading label="Reading the diary…" />)
  if (entries.error) return shell(<ErrorBox error={entries.error} retry={() => entries.refetch()} />)

  const info = threads.data?.threads.find((t) => t.id === thread)
  const openEntry = (slug: string) => go(slideOf(slug))
  const render = (spec: SlideSpec, i: number, print?: boolean) => {
    const props = { index: i, total: slides.length, print }
    if (spec.kind === 'overview') return <OverviewSlide key="overview" {...props} entries={sorted} threads={threads.data?.threads ?? []} thread={info} since={sinceMeeting ? meeting : undefined} onEntry={openEntry} />
    if (spec.kind === 'month') return <MonthSlide key={`m-${spec.month}`} {...props} month={spec.month} entries={spec.entries} onEntry={openEntry} />
    if (spec.kind === 'brief') return <BriefSlide key={`b-${spec.month}`} {...props} month={spec.month} entries={spec.entries} onZoom={setZoom} />
    return <EntrySlide key={`${spec.entry.slug}-${spec.figure}`} {...props} entry={spec.entry} figure={spec.figure} onZoom={setZoom} />
  }
  const current = slides[index]
  const currentMonth = current && current.kind !== 'overview' ? (current.kind === 'entry' ? monthOf(current.entry.date) : current.month) : ''
  return (
    <div className="present-root fixed inset-0 z-50 flex flex-col bg-bg text-fg" data-deck={deck}>
      <header className="present-chrome flex items-center gap-3 border-b border-line px-5 py-2.5 text-[13px] text-muted">
        <ChromeButton onClick={() => setOutline((o) => !o)} title="Outline (O)" active={outline}>☰</ChromeButton>
        <span className="deck-serif text-[15px] font-semibold text-fg">Research log</span>
        {info && <span className="font-mono">· {info.id}</span>}
        <span className="min-w-0 flex-1 truncate text-center text-faint">{current ? slideTitle(current) : ''}</span>
        <span className="tabular-nums">{index + 1} / {slides.length}</span>
        {meeting && (
          <ChromeButton onClick={toggleSince} active={sinceMeeting} title={`Only what came after the meeting of ${shortDay(meeting.date)} (M)`}>
            Since last meeting
          </ChromeButton>
        )}
        <ChromeButton onClick={() => setDeck((d) => (d === 'cream' ? 'dark' : 'cream'))} title="Cream or dark (T)">{deck === 'cream' ? '☾' : '☀'}</ChromeButton>
        <ChromeButton onClick={() => document.documentElement.requestFullscreen?.().catch(() => undefined)} title="Full screen (F)">⛶</ChromeButton>
        <ChromeButton onClick={() => window.print()} title="Export every slide as PDF">PDF</ChromeButton>
        <ChromeButton onClick={exit} title="Back to the diary (Esc)">✕</ChromeButton>
      </header>
      <div className="present-screen flex min-h-0 flex-1">
        {outline && <Outline slides={slides} index={index} onGo={go} />}
        <div className="relative min-w-0 flex-1">
          <div ref={screen} className="h-full overflow-auto">
            {sorted.length ? <Fit screen={screen} slide={index}>{render(current, index)}</Fit> : <Empty title="No entries to present" />}
          </div>
          <EdgeButton side="left" disabled={index === 0} onClick={() => go(index - 1)} />
          <EdgeButton side="right" disabled={index >= slides.length - 1} onClick={() => go(index + 1)} />
        </div>
      </div>
      <footer className="present-chrome flex items-center gap-4 border-t border-line px-5 py-2 text-[12.5px] text-muted">
        <button type="button" className="w-[30%] truncate text-left hover:text-fg disabled:opacity-30" disabled={index === 0} onClick={() => go(index - 1)}>
          ← {index > 0 ? slideTitle(slides[index - 1]) : ''}
        </button>
        <MonthProgress slides={slides} index={index} current={currentMonth} onMonth={(m) => go(monthSlide(m))} />
        <button type="button" className="w-[30%] truncate text-right hover:text-fg disabled:opacity-30" disabled={index >= slides.length - 1} onClick={() => go(index + 1)}>
          {index < slides.length - 1 ? slideTitle(slides[index + 1]) : ''} →
        </button>
      </footer>
      {zoom && (
        <button type="button" className="present-chrome fixed inset-0 z-[60] grid cursor-zoom-out place-items-center bg-black/75 p-6" onClick={() => setZoom(null)} title="Close (Esc)">
          <img src={fileUrl(zoom)} alt={zoom} className="max-h-full max-w-full rounded-lg object-contain shadow-2xl" />
        </button>
      )}
      {/* Print: every slide, one A4 landscape page each, always on the cream deck. */}
      <div className="present-print" data-deck="cream">{slides.map((s, i) => render(s, i, true))}</div>
    </div>
  )
}

/** Scales a slide down (to at least MIN_FIT) so it fits the screen without scrolling. A scaled slide is
 *  laid out wider (width / scale), so after scaling it still fills the width; the scale is the largest
 *  that fits, found by bisection (a wider layout is shorter, so fitting is monotonic in the scale). */
const MIN_FIT = 0.7
function Fit({ screen, slide, children }: { screen: RefObject<HTMLDivElement | null>; slide: number; children: ReactNode }) {
  const inner = useRef<HTMLDivElement>(null)
  const [fit, setFit] = useState({ scale: 1, height: 0 })
  useLayoutEffect(() => {
    const measure = () => {
      const box = screen.current, el = inner.current
      if (!box || !el) return
      const height = (scale: number) => { el.style.width = `${100 / scale}%`; return el.offsetHeight } // transforms leave layout size alone
      let scale = 1
      if (height(1) > box.clientHeight) {
        let lo = MIN_FIT, hi = 1
        for (let i = 0; i < 7; i++) { const mid = (lo + hi) / 2; if (height(mid) * mid <= box.clientHeight) lo = mid; else hi = mid }
        scale = lo
      }
      const natural = height(scale)
      setFit((f) => (f.scale === scale && f.height === natural * scale ? f : { scale, height: natural * scale }))
    }
    measure()
    const observer = new ResizeObserver(() => measure())
    if (screen.current) observer.observe(screen.current)
    if (inner.current) observer.observe(inner.current) // e.g. a "+N more" opened; settles once the width is final
    // Images load after the first layout; re-fit when one does.
    const imgs = [...(inner.current?.querySelectorAll('img') ?? [])]
    imgs.forEach((img) => img.addEventListener('load', measure))
    return () => { observer.disconnect(); imgs.forEach((img) => img.removeEventListener('load', measure)) }
  }, [screen, slide])
  return (
    <div className="overflow-hidden" style={{ height: fit.height || undefined }}>
      <div ref={inner} style={{ transform: `scale(${fit.scale})`, transformOrigin: 'top left' }}>{children}</div>
    </div>
  )
}

function ChromeButton({ children, onClick, title, active }: { children: ReactNode; onClick: () => void; title: string; active?: boolean }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-label={title}
      className={cx('grid h-7 min-w-7 place-items-center rounded-md px-1.5 text-[13px] hover:bg-hover hover:text-fg', active && 'bg-accent-soft text-fg')}>
      {children}
    </button>
  )
}

function EdgeButton({ side, disabled, onClick }: { side: 'left' | 'right'; disabled: boolean; onClick: () => void }) {
  if (disabled) return null
  return (
    <button type="button" onClick={onClick} aria-label={side === 'left' ? 'Previous slide' : 'Next slide'}
      className={cx('group absolute top-0 bottom-0 w-14 cursor-pointer', side === 'left' ? 'left-0' : 'right-3')}>
      <span className="grid h-11 w-11 place-items-center rounded-full border border-line bg-raised text-[18px] text-muted opacity-0 shadow-[var(--shadow)] transition-opacity group-hover:opacity-100">
        {side === 'left' ? '‹' : '›'}
      </span>
    </button>
  )
}

/** Side outline: months with their slides; the current slide is highlighted and kept in view. */
function Outline({ slides, index, onGo }: { slides: SlideSpec[]; index: number; onGo: (i: number) => void }) {
  const active = useRef<HTMLButtonElement>(null)
  useEffect(() => { active.current?.scrollIntoView({ block: 'nearest' }) }, [index])
  return (
    <nav className="w-[290px] shrink-0 overflow-auto border-r border-line bg-sunken/60 px-3 py-4 text-[13px]">
      {slides.map((s, i) => {
        const isMonth = s.kind === 'month' || s.kind === 'overview'
        if (s.kind === 'entry' && s.figure > 0) return null
        const label = s.kind === 'brief' ? `Also: ${s.entries.length} smaller ${s.entries.length === 1 ? 'entry' : 'entries'}` : s.kind === 'entry' ? s.entry.title : slideTitle(s)
        const on = i === index || (s.kind === 'entry' && slides[index]?.kind === 'entry' && (slides[index] as { entry: DiaryEntry }).entry.slug === s.entry.slug)
        return (
          <button key={i} ref={on ? active : undefined} type="button" onClick={() => onGo(i)}
            className={cx('flex w-full items-baseline gap-2 rounded-md px-2 text-left leading-snug',
              isMonth ? 'deck-serif mt-3 py-1 text-[15px] font-semibold text-fg first:mt-0' : 'py-[3px]',
              s.kind === 'brief' && 'text-faint italic',
              s.kind === 'entry' && 'text-muted',
              on ? 'bg-accent-soft !text-fg' : 'hover:bg-hover hover:text-fg')}>
            {s.kind === 'entry' && <span className="w-[42px] shrink-0 font-mono text-[11px] text-faint tabular-nums">{shortDay(s.entry.date)}</span>}
            <span className="min-w-0 flex-1">{label}</span>
            {s.kind === 'entry' && figuresOf(s.entry).length > 0 && <span className="shrink-0 text-[11px] text-faint" title="Has figures">▦</span>}
          </button>
        )
      })}
    </nav>
  )
}

/** Progress by month: one segment per month, sized by its slides; a click opens that month. */
function MonthProgress({ slides, index, current, onMonth }: { slides: SlideSpec[]; index: number; current: string; onMonth: (m: string) => void }) {
  const segments: { month: string; start: number; count: number }[] = []
  slides.forEach((s, i) => {
    if (s.kind === 'month') segments.push({ month: s.month, start: i, count: 0 })
    if (segments.length) segments[segments.length - 1].count++
  })
  return (
    <div className="flex min-w-0 flex-1 items-end gap-1">
      {segments.map((seg) => {
        const fill = Math.max(0, Math.min(1, (index - seg.start + 1) / seg.count))
        return (
          <button key={seg.month} type="button" onClick={() => onMonth(seg.month)} title={monthLabel(seg.month)} style={{ flexGrow: seg.count }}
            className="group flex min-w-0 basis-0 flex-col gap-1">
            <span className={cx('truncate text-center text-[10.5px]', seg.month === current ? 'font-semibold text-fg' : 'text-faint group-hover:text-muted')}>
              {monthLabel(seg.month, 'short')}
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-line">
              <span className="block h-full rounded-full bg-run transition-all" style={{ width: `${fill * 100}%` }} />
            </span>
          </button>
        )
      })}
    </div>
  )
}

function SlideFrame({ index, total, print, top, children }: { index: number; total: number; print?: boolean; top?: ReactNode; children: ReactNode }) {
  return (
    <section className={cx('slide mx-auto flex max-w-[1500px] flex-col gap-6 px-16 pt-9 pb-12', print && 'slide-print')}>
      <div className="flex flex-wrap items-center gap-2.5 text-[14px] text-muted">
        {top}
        {print && <span className="ml-auto tabular-nums text-faint">{index + 1} / {total}</span>}
      </div>
      {children}
    </section>
  )
}

function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-[150px] rounded-xl border border-line bg-panel px-5 py-3.5">
      <div className="section-label !text-[11px]">{label}</div>
      <div className="deck-serif mt-0.5 text-[30px] leading-tight font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-[12.5px] text-faint">{sub}</div>}
    </div>
  )
}

/** Runs and tokens of a set of runs, as a row of stat tiles. */
function RunTiles({ stats, label = 'Runs' }: { stats: RunStats; label?: string }) {
  if (!stats.runs) return null
  const top = stats.models.slice(0, 3)
  return (
    <div className="flex flex-wrap gap-3">
      <Stat label={label} value={stats.runs} sub={stats.byDate ? 'started that day' : 'linked'} />
      <Stat label="Tokens used" value={stats.withTokens ? formatTokens(stats.tokens) : '—'}
        sub={stats.withTokens ? `${stats.withTokens < stats.runs ? `${stats.withTokens} of ${stats.runs} runs logged · ` : ''}${formatTokens(stats.output)} generated` : 'no usage logged'} />
      {top.length > 0 && (
        <div className="min-w-[220px] flex-1 rounded-xl border border-line bg-panel px-5 py-3.5">
          <div className="section-label !text-[11px]">Tokens by model</div>
          <div className="mt-1.5 flex flex-col gap-1">
            {top.map(([m, t]) => (
              <div key={m} className="flex items-center gap-2 text-[13px]">
                <span className="w-[190px] truncate font-mono text-muted" title={m}>{m}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line"><span className="block h-full rounded-full bg-run" style={{ width: `${(t / top[0][1]) * 100}%` }} /></span>
                <span className="w-[52px] text-right tabular-nums">{formatTokens(t)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function OverviewSlide({ entries, threads, thread, since, onEntry, ...frame }: {
  index: number; total: number; print?: boolean; entries: DiaryEntry[]; threads: DiaryThread[]; thread?: DiaryThread; since?: DiaryEntry; onEntry: (slug: string) => void
}) {
  const first = entries[0]?.date
  const last = entries[entries.length - 1]?.date
  const used = threads.filter((t) => entries.some((e) => e.threads.includes(t.id)))
  const runs = statsOf(uniqueRuns(entries))
  const figures = entries.reduce((n, e) => n + figuresOf(e).length, 0)
  const months = new Set(entries.map((e) => monthOf(e.date))).size
  return (
    <SlideFrame {...frame}>
      <div>
        <h1 className="deck-serif text-[56px] leading-[1.05] font-semibold tracking-[-0.02em]">
          {since ? `Since the meeting of ${shortDay(since.date)}` : 'Research log'}
          {thread && <> · <span className="font-mono text-[44px]">{thread.id}</span></>}
        </h1>
        <p className="mt-3 max-w-[70ch] text-[20px] leading-snug text-muted">
          {thread?.description ? `${thread.description}. ` : ''}
          {first ? `${dayLabel(first)} to ${dayLabel(last)}.` : ''} Each slide: what was found, the figures, then what was done, decided and planned.
        </p>
      </div>
      {since && hasText(since.sections.decided) && (
        <div className="rounded-2xl border border-line bg-panel px-7 py-5 shadow-[var(--shadow)]">
          <div className="section-label mb-2 !text-[12px]">They asked for</div>
          <Markdown className="text-[20px] leading-snug">{bulletsOf(since.sections.decided).map((i) => `- ${i}`).join('\n')}</Markdown>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <Stat label="Entries" value={entries.length} sub={`${entries.filter((e) => e.brief).length} in brief`} />
        <Stat label="Months" value={months} sub={`${used.length} threads`} />
        <Stat label="Runs" value={runs.runs} sub="linked to entries" />
        <Stat label="Tokens used" value={runs.withTokens ? formatTokens(runs.tokens) : '—'} sub={`${runs.withTokens} runs logged · ${formatTokens(runs.output)} generated`} />
        <Stat label="Figures" value={figures} />
      </div>
      {entries.length > 0 && <ThreadTimeline entries={entries} threads={used} onEntry={onEntry} />}
    </SlideFrame>
  )
}

/** One lane per thread, one dot per entry (by its first thread); filled = own slide, hollow = in brief. */
function ThreadTimeline({ entries, threads, onEntry }: { entries: DiaryEntry[]; threads: DiaryThread[]; onEntry: (slug: string) => void }) {
  const lanes = threads.filter((t) => entries.some((e) => e.threads[0] === t.id))
  const t0 = Date.parse(entries[0].date)
  const t1 = Math.max(t0 + 86_400_000, Date.parse(entries[entries.length - 1].date))
  const W = 1300, LABEL = 200, LANE = 28, TOP = 26
  const x = (date: string) => LABEL + ((Date.parse(date) - t0) / (t1 - t0)) * (W - LABEL - 24)
  const months: string[] = []
  for (let m = monthOf(entries[0].date); m <= monthOf(entries[entries.length - 1].date);) {
    months.push(m)
    const [y, mo] = m.split('-').map(Number)
    m = mo === 12 ? `${y + 1}-01` : `${y}-${String(mo + 1).padStart(2, '0')}`
  }
  const H = TOP + lanes.length * LANE + 26
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Diary entries over time, one lane per thread">
      {months.map((m) => {
        const mx = Math.max(LABEL, x(`${m}-01`))
        return (
          <g key={m}>
            <line x1={mx} x2={mx} y1={TOP - 6} y2={H - 22} stroke="var(--line)" />
            <text x={mx + 4} y={14} fontSize={12} fill="var(--faint)">{monthLabel(m, 'short')}</text>
          </g>
        )
      })}
      {lanes.map((t, i) => {
        const y = TOP + i * LANE + LANE / 2
        return (
          <g key={t.id}>
            <text x={0} y={y + 4} fontSize={13} fill="var(--muted)" fontFamily="ui-monospace, monospace">{t.id}</text>
            <line x1={LABEL} x2={W - 20} y1={y} y2={y} stroke="var(--line)" strokeDasharray="2 4" />
            {entries.filter((e) => e.threads[0] === t.id).map((e) => (
              <g key={e.slug} className="cursor-pointer" onClick={() => onEntry(e.slug)}>
                <title>{`${e.date} · ${e.title}${e.brief ? ' (in brief)' : ''}`}</title>
                <circle cx={x(e.date)} cy={y} r={11} fill="transparent" />
                {e.brief
                  ? <circle cx={x(e.date)} cy={y} r={4.5} fill="var(--bg)" stroke="var(--faint)" strokeWidth={1.5} />
                  : <circle cx={x(e.date)} cy={y} r={6.5} fill={figuresOf(e).length ? 'var(--run)' : 'var(--fg)'} stroke="var(--bg)" strokeWidth={2} />}
              </g>
            ))}
          </g>
        )
      })}
      <g transform={`translate(${LABEL}, ${H - 6})`} fontSize={12} fill="var(--faint)">
        <circle cx={6} cy={-4} r={6} fill="var(--run)" /><text x={18} y={0}>own slide, with figures</text>
        <circle cx={186} cy={-4} r={6} fill="var(--fg)" /><text x={198} y={0}>own slide</text>
        <circle cx={290} cy={-4} r={4.5} fill="var(--bg)" stroke="var(--faint)" strokeWidth={1.5} /><text x={302} y={0}>in brief</text>
      </g>
    </svg>
  )
}

function MonthSlide({ month, entries, onEntry, ...frame }: { index: number; total: number; print?: boolean; month: string; entries: DiaryEntry[]; onEntry: (slug: string) => void }) {
  const runs = statsOf(uniqueRuns(entries))
  const brief = entries.filter((e) => e.brief)
  return (
    <SlideFrame {...frame} top={<span className="section-label !text-[12px]">Chapter</span>}>
      <h1 className="deck-serif text-[60px] leading-[1.05] font-semibold tracking-[-0.02em]">{monthLabel(month)}</h1>
      <div className="flex flex-wrap gap-3">
        <Stat label="Entries" value={entries.length} sub={entries.some((e) => e.brief) ? `${entries.filter((e) => e.brief).length} in brief` : undefined} />
        {runs.runs > 0 && <Stat label="Runs" value={runs.runs} />}
        {runs.withTokens > 0 && <Stat label="Tokens used" value={formatTokens(runs.tokens)} sub={`${formatTokens(runs.output)} generated`} />}
      </div>
      <ol className="flex flex-col">
        {entries.filter((e) => !e.brief).map((e) => {
          const s = runStats(e.runs)
          return (
            <li key={e.slug} className="flex items-baseline gap-4 border-b border-line py-2 last:border-0">
              <span className="w-[64px] shrink-0 font-mono text-[14px] text-faint tabular-nums">{shortDay(e.date)}</span>
              <button type="button" className="text-left text-[19px] leading-snug hover:underline" onClick={() => onEntry(e.slug)}>
                {e.title}
                {figuresOf(e).length > 0 && <span className="ml-2 text-[13px] text-run" title="Has figures">▦ {figuresOf(e).length}</span>}
              </button>
              <span className="ml-auto flex shrink-0 items-baseline gap-3">
                {s.withTokens > 0 && <span className="text-[13px] text-faint tabular-nums">{formatTokens(s.tokens)} tokens</span>}
                {e.threads.slice(0, 1).map((t) => <Tag key={t}>{t}</Tag>)}
              </span>
            </li>
          )
        })}
        {brief.length > 0 && (
          <li className="flex items-baseline gap-4 py-2 text-[16px] text-faint italic">
            <span className="w-[64px] shrink-0" />
            <button type="button" className="text-left hover:underline" onClick={() => onEntry(brief[0].slug)}>
              Also {brief.length} smaller {brief.length === 1 ? 'entry' : 'entries'}: {brief.map((e) => e.title).join(' · ')}
            </button>
          </li>
        )}
      </ol>
    </SlideFrame>
  )
}

function EntryHeader({ entry }: { entry: DiaryEntry }) {
  return (
    <>
      <span className="font-medium text-fg">{dayLabel(entry.date)}</span>
      {entry.threads.map((t) => <Tag key={t}>{t}</Tag>)}
      {entry.reconstructed && <span className="text-[12px] text-faint italic">reconstructed after the fact</span>}
    </>
  )
}

function EntrySlide({ entry, figure, onZoom, ...frame }: { index: number; total: number; print?: boolean; entry: DiaryEntry; figure: number; onZoom: (path: string) => void }) {
  const figures = figuresOf(entry)
  const docs = entry.docs.filter((d) => !figures.includes(d))
  const { did, found, decided, next } = entry.sections
  const stats = runStats(entry.runs)
  const shown = figures[figure]
  if (figure > 0) {
    return (
      <SlideFrame {...frame} top={<EntryHeader entry={entry} />}>
        <h2 className="deck-serif text-[26px] leading-tight font-semibold text-muted">{entry.title} <span className="text-[18px] font-normal text-faint">· figure {figure + 1} of {figures.length}</span></h2>
        <Figure path={shown} onZoom={onZoom} big />
      </SlideFrame>
    )
  }
  const foundBox = hasText(found) && (
    <div className="rounded-2xl border border-line bg-panel px-7 py-5 shadow-[var(--shadow)]">
      <div className="section-label mb-2 !text-[12px]">Found</div>
      <Bullets text={found} limit={frame.print ? undefined : shown ? FOUND_BESIDE_FIGURE : FOUND_SHOWN} className={cx('leading-snug', shown ? 'text-[16px]' : 'text-[20px]')} />
    </div>
  )
  return (
    <SlideFrame {...frame} top={<EntryHeader entry={entry} />}>
      <h1 className="deck-serif text-[42px] leading-[1.1] font-semibold tracking-[-0.015em]">{entry.title}</h1>
      <RunTiles stats={stats} />
      {shown ? (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)]">
          {foundBox || <div />}
          <Figure path={shown} onZoom={onZoom} more={figures.length > 1 ? `${figures.length - 1} more ${figures.length > 2 ? 'figures' : 'figure'} on the next slides` : undefined} />
        </div>
      ) : foundBox}
      {(hasText(decided) || hasText(next)) && (
        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          {([['Decided', decided], ['Next', next]] as const).filter(([, text]) => hasText(text)).map(([label, text]) => (
            <div key={label}>
              <div className="section-label mb-1.5 !text-[12px]">{label}</div>
              <Bullets text={text} limit={frame.print ? undefined : SECTION_SHOWN} className="text-[15px] leading-snug text-muted" />
            </div>
          ))}
        </div>
      )}
      {hasText(did) && <DidToggle text={did} print={frame.print} />}
      {(docs.length > 0 || entry.commits.length > 0) && (
        <div className={cx('border-t border-line pt-3 text-[12.5px] text-faint', frame.print ? 'flex flex-wrap gap-x-6 gap-y-1' : 'truncate')}>
          {entry.commits.length > 0 && <span className="mr-6">commits: <span className="font-mono">{entry.commits.join(' ')}</span></span>}
          {docs.length > 0 && <span title={docs.join('\n')}>docs: <span className="font-mono">{docs.join(' · ')}</span></span>}
        </div>
      )}
    </SlideFrame>
  )
}

function Figure({ path, onZoom, big, more }: { path: string; onZoom: (path: string) => void; big?: boolean; more?: string }) {
  return (
    <figure className="flex flex-col gap-1.5">
      <button type="button" className="cursor-zoom-in" onClick={() => onZoom(path)} title="Enlarge">
        <img src={fileUrl(path)} alt={path} className={cx('w-full rounded-xl border border-line bg-white object-contain shadow-[var(--shadow)]', big ? 'max-h-[70vh]' : 'max-h-[56vh]')} />
      </button>
      <figcaption className="flex gap-3 text-[12px] text-faint">
        <span className="font-mono">{path.split('/').slice(-2).join('/')}</span>
        {more && <span className="ml-auto italic">{more}</span>}
      </figcaption>
    </figure>
  )
}

/** Entries marked `brief`, as compact cards; a card opens to its full text and its figures. */
function BriefSlide({ month, entries, onZoom, ...frame }: { index: number; total: number; print?: boolean; month: string; entries: DiaryEntry[]; onZoom: (path: string) => void }) {
  const [open, setOpen] = useState<string | null>(null)
  const many = entries.length > 6
  return (
    <SlideFrame {...frame} top={<span className="section-label !text-[12px]">In brief</span>}>
      <h1 className="deck-serif text-[40px] leading-[1.1] font-semibold tracking-[-0.015em]">Also in {monthLabel(month)}</h1>
      <div className={cx('grid gap-3 md:grid-cols-2', many && 'xl:grid-cols-3')}>
        {entries.map((e) => {
          const line = bulletsOf(hasText(e.sections.found) ? e.sections.found : e.sections.did)[0] ?? ''
          const s = runStats(e.runs)
          const figures = figuresOf(e)
          const isOpen = open === e.slug
          const toggle = () => setOpen(isOpen ? null : e.slug)
          return (
            <div key={e.slug} role="button" tabIndex={0} onClick={toggle} onKeyDown={(k) => { if (k.key === 'Enter') toggle() }}
              className={cx('flex cursor-pointer flex-col gap-1.5 rounded-xl border border-line bg-panel text-left hover:border-line-strong', many ? 'px-4 py-3' : 'px-5 py-4', isOpen && 'md:col-span-2 xl:col-span-3')}>
              <span className="flex items-baseline gap-3 text-[12.5px] text-faint">
                <span className="font-mono tabular-nums">{shortDay(e.date)}</span>
                <span>{e.threads[0]}</span>
                {figures.length > 0 && <span className="text-run" title="Has figures">▦ {figures.length}</span>}
                {s.withTokens > 0 && <span className="ml-auto tabular-nums">{s.runs} runs · {formatTokens(s.tokens)} tokens</span>}
              </span>
              <span className={cx('leading-snug font-semibold', many ? 'text-[16px]' : 'text-[18px]')}>{e.title}</span>
              {isOpen ? (
                <>
                  <span className="grid gap-x-8 gap-y-3 md:grid-cols-2">
                    {(['did', 'found', 'decided', 'next'] as const).filter((k) => hasText(e.sections[k])).map((k) => (
                      <span key={k} className="block"><span className="section-label block">{k}</span><Markdown className="text-[14.5px] leading-snug">{e.sections[k]}</Markdown></span>
                    ))}
                  </span>
                  {figures.length > 0 && (
                    <span className="flex flex-wrap gap-3">
                      {figures.map((f) => (
                        <button key={f} type="button" className="cursor-zoom-in" title="Enlarge" onClick={(ev) => { ev.stopPropagation(); onZoom(f) }}>
                          <img src={fileUrl(f)} alt={f} className="h-40 rounded-lg border border-line bg-white object-contain" />
                        </button>
                      ))}
                    </span>
                  )}
                </>
              ) : line && <Markdown className={cx('line-clamp-2 leading-snug text-muted', many ? 'text-[13.5px]' : 'text-[14.5px]')}>{line}</Markdown>}
            </div>
          )
        })}
      </div>
    </SlideFrame>
  )
}

/** What was done: folded behind one line on screen (the slide leads with results), open in print. */
function DidToggle({ text, print }: { text: string; print?: boolean }) {
  const [open, setOpen] = useState(false)
  const items = bulletsOf(text)
  if (print || open) {
    return (
      <div>
        <div className="section-label mb-1.5 !text-[12px]">Did</div>
        <Markdown className="text-[15px] leading-snug text-muted">{items.map((i) => `- ${i}`).join('\n')}</Markdown>
      </div>
    )
  }
  return (
    <button type="button" onClick={() => setOpen(true)} className="self-start text-[13.5px] text-faint hover:text-fg">
      ▸ What was done ({items.length} {items.length === 1 ? 'item' : 'items'})
    </button>
  )
}

/** A section's bullets; past `limit`, a "+N more" button shows the rest. */
function Bullets({ text, limit, className }: { text: string; limit?: number; className?: string }) {
  const [all, setAll] = useState(false)
  const items = bulletsOf(text)
  const cut = limit !== undefined && !all && items.length > limit
  return (
    <>
      <Markdown className={className}>{(cut ? items.slice(0, limit) : items).map((i) => `- ${i}`).join('\n')}</Markdown>
      {cut && <button type="button" className="mt-1 text-[13px] text-link hover:underline" onClick={() => setAll(true)}>+ {items.length - limit} more</button>}
    </>
  )
}
