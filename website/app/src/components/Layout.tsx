import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useBenchmarks, useCatalog } from '../api/hooks'
import { gameHref, runHref } from '../lib/runs'
import { shortId } from '../lib/format'
import { cx } from './ui'

const NAV: { to: string; label: string; icon: ReactNode }[] = [
  { to: '/runs', label: 'Runs', icon: <Icon d="M3 4h10M3 8h10M3 12h6" /> },
  { to: '/launch', label: 'Launch', icon: <Icon d="M8 3v10M3 8h10" /> },
  { to: '/compare', label: 'Compare', icon: <Icon d="M3 13V8M8 13V3M13 13V6" /> },
  { to: '/benchmarks', label: 'Benchmarks', icon: <Icon d="M3 3h4v4H3zM9 3h4v4H9zM3 9h4v4H3zM9 9h4v4H9z" /> },
  { to: '/diary', label: 'Diary', icon: <Icon d="M4 2.5h7.5v11H4zM6 5.5h3.5M6 8h3.5" /> },
  { to: '/tools', label: 'Tools', icon: <Icon d="M10.5 2.5a3 3 0 0 0-2.8 4L3 11.2 4.8 13l4.7-4.7a3 3 0 0 0 4-2.8l-1.8 1-1.7-1.7 1-1.8z" /> },
]

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  )
}

export function Layout() {
  const location = useLocation()
  const runsActive = location.pathname === '/' || location.pathname.startsWith('/runs')
  return (
    <div className="flex h-full">
      <aside className="flex w-[188px] shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex h-12 items-center gap-2 border-b border-line px-4">
          <span className="grid h-5 w-5 grid-cols-2 gap-px overflow-hidden rounded-sm">
            <span className="bg-accent" /><span className="bg-line-strong" /><span className="bg-line-strong" /><span className="bg-accent" />
          </span>
          <span className="text-[13.5px] font-semibold tracking-tight">Workbench</span>
        </div>
        <nav className="flex flex-col gap-0.5 p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] hover:no-underline',
                  isActive || (item.to === '/runs' && runsActive) ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:bg-sunken hover:text-fg',
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-line px-4 py-2 text-[11px] text-faint">PuzzleScript research</div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-panel px-5">
          <GlobalSearch />
        </header>
        <main className="min-h-0 flex-1 overflow-auto px-6 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** Run id / game search across the catalog and the benchmark list. */
function GlobalSearch() {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const navigate = useNavigate()
  const { views } = useCatalog(30_000)
  const benchmarks = useBenchmarks()
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === '/' && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault()
        input.current?.focus()
      }
    }
    const onClick = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onClick)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onClick)
    }
  }, [])

  const results = useMemo(() => {
    const needle = text.trim().toLowerCase()
    if (needle.length < 2) return []
    const games = (benchmarks.data?.games ?? [])
      .filter((g) => `${g.game_id} ${g.title}`.toLowerCase().includes(needle))
      .slice(0, 5)
      .map((g) => ({ key: `g:${g.game_id}`, label: g.title, sub: g.game_id, kind: 'Game', href: gameHref(g.game_id) }))
    const runs = views
      .filter((r) => `${r.id} ${r.game} ${r.model}`.toLowerCase().includes(needle))
      .slice(0, 7)
      .map((r) => ({ key: `r:${r.id}`, label: shortId(r.id, 3), sub: `${r.game} · ${r.model}`, kind: 'Run', href: runHref(r.id) }))
    return [...games, ...runs, { key: 'all', label: `All runs matching “${text.trim()}”`, sub: '', kind: '', href: `/runs?q=${encodeURIComponent(text.trim())}` }]
  }, [text, views, benchmarks.data])

  const go = (href: string) => {
    setOpen(false)
    setText('')
    navigate(href)
  }

  return (
    <div ref={box} className="relative w-full max-w-[460px]">
      <input
        ref={input}
        value={text}
        placeholder="Search runs and games   /"
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
          setCursor(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)) }
          if (e.key === 'Enter' && results[cursor]) go(results[cursor].href)
          if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
        }}
        className="h-8 w-full rounded-md border border-line bg-sunken px-3 text-[13px] placeholder:text-faint focus:border-accent focus:bg-panel focus:outline-none"
      />
      {open && results.length > 0 && (
        <div className="absolute top-9 z-30 w-full overflow-hidden rounded-md border border-line bg-panel shadow-lg">
          {results.map((r, i) => (
            <button
              key={r.key}
              type="button"
              onMouseEnter={() => setCursor(i)}
              onClick={() => go(r.href)}
              className={cx('flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-[12.5px]', i === cursor && 'bg-sunken')}
            >
              {r.kind && <span className="w-9 shrink-0 text-[11px] text-faint">{r.kind}</span>}
              <span className="truncate font-medium">{r.label}</span>
              <span className="truncate text-[11.5px] text-muted">{r.sub}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
