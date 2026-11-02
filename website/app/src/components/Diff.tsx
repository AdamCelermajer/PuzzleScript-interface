import { diffLines, type DiffLine } from '../lib/events'
import { cx } from './ui'

const LINE_STYLE: Record<DiffLine['kind'], string> = {
  add: 'bg-ok-soft text-ok',
  del: 'bg-bad-soft text-bad',
  hunk: 'text-accent',
  head: 'text-faint',
  same: 'text-fg/80',
}

/** A unified diff, coloured line by line like a code review. */
export function DiffView({ diff, note, className }: { diff: string; note?: string; className?: string }) {
  const lines = diffLines(diff)
  const added = lines.filter((l) => l.kind === 'add').length
  const removed = lines.filter((l) => l.kind === 'del').length
  return (
    <div className={cx('flex flex-col gap-1', className)}>
      <div className="text-[11px] text-muted">
        <span className="text-ok">+{added}</span> <span className="text-bad">−{removed}</span>
        {note && <span className="ml-2 text-faint">· {note}</span>}
      </div>
      <pre className="max-h-[480px] overflow-auto rounded-md bg-sunken py-1.5 font-mono text-[11.5px] leading-[1.5]">
        {lines.map((line, i) => (
          <div key={i} className={cx('px-2.5 whitespace-pre-wrap break-words', LINE_STYLE[line.kind])}>{line.text || ' '}</div>
        ))}
      </pre>
    </div>
  )
}
