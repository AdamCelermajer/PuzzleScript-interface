import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useBenchmarks, useCatalog } from '../api/hooks'
import { gameHref, runHref } from '../lib/runs'
import { shortId } from '../lib/format'
import { cx } from './ui'
import { useTheme, type ThemeChoice } from '../theme'

const NAV: { to: string; label: string; icon: ReactNode; end?: boolean }[] = [
  { to: '/', label: 'Results', icon: <Icon d="M2.5 2.5h4v4h-4zM9.5 2.5h4v4h-4zM2.5 9.5h4v4h-4zM9.5 9.5h4v4h-4z" />, end: true },
  { to: '/board', label: 'Board', icon: <Icon d="M2.5 3h3v10h-3zM6.5 3h3v6h-3zM10.5 3h3v8h-3z" /> },
  { to: '/runs', label: 'Runs', icon: <Icon d="M3 4h10M3 8h10M3 12h6" /> },
  { to: '/launch', label: 'Launch', icon: <Icon d="M8 3v10M3 8h10" /> },
  { to: '/compare', label: 'Compare', icon: <Icon d="M3 13V8M8 13V3M13 13V6" /> },
  { to: '/benchmarks', label: 'Benchmarks', icon: <Icon d="M2.5 4.5h11v8h-11zM5 4.5V3h6v1.5M6 8.5h1M9.5 8h.01M10.5 9h.01" /> },
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
  const [theme, setTheme] = useTheme()
  return (
    <div className="flex h-full">
      <aside className="flex w-[208px] shrink-0 flex-col border-r border-line bg-bg">
        <div className="flex h-14 items-center gap-2.5 px-4">
          <span className="grid h-6 w-6 grid-cols-3 gap-[2px] overflow-hidden rounded-md bg-accent p-[4px]">
            {[1, 0, 1, 0, 1, 0, 1, 1, 1].map((on, i) => <span key={i} className={on ? 'bg-accent-fg' : ''} />)}
          </span>
          <div className="leading-tight">
            <div className="text-[13.5px] font-semibold tracking-tight">Workbench</div>
            <div className="text-[11px] text-faint">PuzzleScript research</div>
          </div>
        </div>
        <nav className="flex flex-col gap-px px-2 pt-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] hover:no-underline',
                  isActive ? 'bg-hover font-medium text-fg' : 'text-muted hover:bg-hover hover:text-fg',
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto p-3">
          <ThemeSwitch value={theme} onChange={setTheme} />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-bg px-8">
          <GlobalSearch />
        </header>
        <main className="min-h-0 flex-1 overflow-auto px-8 py-7">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function ThemeSwitch({ value, onChange }: { value: ThemeChoice; onChange: (v: ThemeChoice) => void }) {
  const options: { id: ThemeChoice; label: string; d: string }[] = [
    { id: 'system', label: 'System', d: 'M2.5 3.5h11v7.5h-11zM6 13.5h4M8 11v2.5' },
    { id: 'light', label: 'Light', d: 'M8 5.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1' },
    { id: 'dark', label: 'Dark', d: 'M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z' },
  ]
  return (
    <div className="flex rounded-lg border border-line bg-panel p-0.5" role="radiogroup" aria-label="Theme">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          title={`${o.label} theme`}
          onClick={() => onChange(o.id)}
          className={cx('flex flex-1 items-center justify-center rounded-md py-1', value === o.id ? 'bg-hover text-fg' : 'text-faint hover:text-fg')}
        >
          <Icon d={o.d} />
        </button>
      ))}
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
        className="h-8 w-full rounded-md border border-line bg-panel px-3 text-[13px] placeholder:text-faint focus:border-line-strong focus:ring-2 focus:ring-fg/10 focus:outline-none"
      />
      {open && results.length > 0 && (
        <div className="absolute top-9 z-30 w-full overflow-hidden rounded-lg border border-line bg-raised shadow-xl">
          {results.map((r, i) => (
            <button
              key={r.key}
              type="button"
              onMouseEnter={() => setCursor(i)}
              onClick={() => go(r.href)}
              className={cx('flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-[12.5px]', i === cursor && 'bg-hover')}
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
