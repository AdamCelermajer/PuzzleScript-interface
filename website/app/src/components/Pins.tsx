import { useState } from 'react'
import { Link } from 'react-router-dom'
import { usePinActions } from '../api/hooks'
import type { Pin } from '../api/types'
import { dateTime } from '../lib/format'
import { runHref } from '../lib/runs'
import { Button, Empty, ErrorBox, cx } from './ui'

/** Pinned events with their copied text and an editable note; `showRun` links each to its run. */
export function PinList({ pins, showRun = false, empty = 'Nothing pinned yet. Use ☆ on any agent timeline event.' }: { pins: Pin[]; showRun?: boolean; empty?: string }) {
  const actions = usePinActions()
  if (!pins.length) return <Empty title={empty} />
  return (
    <div className="flex flex-col gap-2">
      {actions.note.error ? <ErrorBox error={actions.note.error} /> : null}
      {actions.remove.error ? <ErrorBox error={actions.remove.error} /> : null}
      {[...pins].reverse().map((pin) => <PinCard key={pin.id} pin={pin} showRun={showRun} onNote={(note) => actions.note.mutate({ id: pin.id, note })} onRemove={() => actions.remove.mutate(pin.id)} />)}
    </div>
  )
}

function PinCard({ pin, showRun, onNote, onRemove }: { pin: Pin; showRun: boolean; onNote: (note: string) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState(pin.note)
  const long = pin.text.length > 600 || pin.text.split('\n').length > 8
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-2 text-[12px]">
        <span className="text-accent">★</span>
        <span className="font-medium">{pin.title || pin.kind}</span>
        {pin.turn !== null && <span className="text-muted">turn {pin.turn}</span>}
        {pin.context && <span className="font-mono text-[11px] text-muted">{pin.context}</span>}
        {showRun && <Link to={runHref(pin.run)} className="min-w-0 truncate font-mono text-[11px]">{pin.run}</Link>}
        <span className="ml-auto text-[11px] text-faint" title={pin.at ? `event ${dateTime(pin.at)}` : undefined}>pinned {dateTime(pin.created_at)}</span>
        <Button size="sm" variant="ghost" onClick={() => window.confirm('Remove this pin?') && onRemove()}>Unpin</Button>
      </div>
      <pre className={cx('mt-1.5 overflow-auto rounded bg-sunken/60 p-2 text-[12px] whitespace-pre-wrap break-words', !open && long && 'max-h-40')}>{pin.text}</pre>
      {long && <button type="button" className="text-[11.5px] text-link" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Show all'}</button>}
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== pin.note && onNote(note)}
        placeholder="Your note (saved when you click away)"
        rows={note ? 2 : 1}
        className="mt-1.5 w-full resize-y rounded-md border border-line bg-transparent px-2 py-1 text-[12.5px] outline-none focus:border-accent"
      />
    </div>
  )
}
