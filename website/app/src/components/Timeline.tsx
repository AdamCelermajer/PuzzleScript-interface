import { useMemo, useState } from 'react'
import { KIND_LABEL, type EventKind, type TimelineItem } from '../lib/events'
import { dateTime } from '../lib/format'
import { Button, Empty, Input, cx } from './ui'

const KIND_STYLE: Record<EventKind, string> = {
  message: 'text-accent',
  prompt: 'text-muted',
  reasoning: 'text-faint',
  command: 'text-fg',
  file_change: 'text-ok',
  tool: 'text-fg',
  image: 'text-accent',
  usage: 'text-faint',
  error: 'text-bad',
  turn_end: 'text-faint',
  environment: 'text-warn',
  other: 'text-faint',
}

/** Normalized agent event timeline: kind filter chips, search, collapsible items. */
/** `pinned` holds the pin keys of this list; `onPin` toggles one (absent = no pin buttons). */
export function Timeline({ items, emptyText = 'No agent events recorded', footer, pinned, onPin }: {
  items: TimelineItem[]
  emptyText?: string
  footer?: React.ReactNode
  pinned?: (item: TimelineItem) => boolean
  onPin?: (item: TimelineItem) => void
}) {
  const kinds = useMemo(() => [...new Set(items.map((i) => i.kind))], [items])
  const [hidden, setHidden] = useState<Set<EventKind>>(new Set(['usage', 'turn_end']))
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [allOpen, setAllOpen] = useState(false)
  const [newestFirst, setNewestFirst] = useState(true)
  const needle = search.trim().toLowerCase()
  const filtered = items.filter((i) => !hidden.has(i.kind) && (!needle || `${i.title} ${i.summary} ${i.input ?? ''} ${i.body ?? ''}`.toLowerCase().includes(needle)))
  const shown = newestFirst ? [...filtered].reverse() : filtered
  const counts = items.reduce<Record<string, number>>((acc, i) => ({ ...acc, [i.kind]: (acc[i.kind] ?? 0) + 1 }), {})

  if (!items.length) return <Empty title={emptyText} />
  let lastTurn: number | null = null
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {kinds.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(kind)) n.delete(kind); else n.add(kind); return n })}
            className={cx('h-6 rounded border px-2 text-[11.5px]', hidden.has(kind) ? 'border-line text-faint line-through' : 'border-line-strong text-fg')}
          >
            {KIND_LABEL[kind]} <span className="text-faint">{counts[kind]}</span>
          </button>
        ))}
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search events…" className="ml-auto h-7 w-52" />
        <Button size="sm" variant="ghost" onClick={() => setNewestFirst(!newestFirst)} title="Order of events">{newestFirst ? 'Newest first' : 'Oldest first'}</Button>
        <Button size="sm" variant="ghost" onClick={() => { setAllOpen(!allOpen); setExpanded(new Set()) }}>{allOpen ? 'Collapse all' : 'Expand all'}</Button>
      </div>
      <div className="flex flex-col rounded-md border border-line">
        {shown.map((item) => {
          const turnHeader = item.turn !== null && item.turn !== lastTurn
          lastTurn = item.turn
          const open = allOpen !== expanded.has(item.id)
          const detail = Boolean(item.body || item.input)
          return (
            <div key={item.id}>
              {turnHeader && <div className="sticky top-0 z-[1] border-b border-line bg-sunken px-3 py-0.5 text-[11px] font-medium text-muted">Turn {item.turn}</div>}
              <div className="border-b border-line last:border-b-0">
                <div className="flex items-stretch">
                <button
                  type="button"
                  disabled={!detail}
                  onClick={() => setExpanded((e) => { const n = new Set(e); if (n.has(item.id)) n.delete(item.id); else n.add(item.id); return n })}
                  className="flex min-w-0 flex-1 items-baseline gap-2 px-3 py-1.5 text-left hover:bg-sunken disabled:cursor-default"
                >
                  <span className="w-3 shrink-0 text-[11px] text-faint">{detail ? (open ? '▾' : '▸') : ''}</span>
                  <span className={cx('w-28 shrink-0 truncate text-[12px] font-medium', KIND_STYLE[item.kind])}>{item.title}</span>
                  <span className="min-w-0 flex-1 truncate text-[12.5px] text-fg/90">{item.summary || <span className="text-faint">—</span>}</span>
                  {item.meta && <span className={cx('shrink-0 text-[11px] tabular-nums', /failed|error|exit [1-9-]/i.test(item.meta) ? 'text-bad' : 'text-faint')}>{item.meta}</span>}
                  {item.at && <span className="shrink-0 text-[11px] text-faint" title={dateTime(item.at)}>{timeOnly(item.at)}</span>}
                </button>
                {onPin && (
                  <button type="button" onClick={() => onPin(item)} title={pinned?.(item) ? 'Unpin' : 'Pin this event'} aria-label={pinned?.(item) ? 'Unpin' : 'Pin'}
                    className={cx('shrink-0 px-2 text-[13px] hover:text-accent', pinned?.(item) ? 'text-accent' : 'text-faint')}>
                    {pinned?.(item) ? '★' : '☆'}
                  </button>
                )}
                </div>
                {open && detail && (
                  <div className="flex flex-col gap-1.5 px-3 pb-2 pl-8">
                    {item.input && <pre className="max-h-64 overflow-auto rounded bg-sunken p-2 font-mono text-[11.5px] whitespace-pre-wrap break-words">{item.input}</pre>}
                    {item.body && <pre className={cx('max-h-[420px] overflow-auto rounded p-2 text-[12px] whitespace-pre-wrap break-words', item.input ? 'bg-sunken font-mono text-[11.5px] text-muted' : 'bg-sunken/60')}>{item.body}</pre>}
                  </div>
                )}
              </div>
            </div>
          )
        })}
        {!shown.length && <div className="p-4 text-center text-[12px] text-faint">No events match the filters</div>}
      </div>
      {footer}
    </div>
  )
}

function timeOnly(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
