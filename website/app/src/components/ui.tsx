import { useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import type { OutcomeTone, ProcessTone } from '../lib/status'

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

type Tone = ProcessTone | OutcomeTone | 'accent' | 'neutral' | 'warn' | 'ok' | 'bad'

const TONES: Record<string, string> = {
  running: 'bg-run-soft text-run',
  queued: 'bg-neutral-soft text-muted',
  paused: 'bg-warn-soft text-warn',
  finished: 'bg-neutral-soft text-fg',
  failed: 'bg-bad-soft text-bad',
  stopped: 'bg-neutral-soft text-muted',
  unconfirmed: 'bg-transparent text-faint border border-dashed border-line-strong',
  attention: 'bg-warn-soft text-warn',
  solved: 'bg-ok-soft text-ok',
  partial: 'bg-accent-soft text-accent',
  unsolved: 'bg-neutral-soft text-muted',
  pending: 'bg-transparent text-faint border border-line',
  none: 'bg-transparent text-faint',
  accent: 'bg-accent-soft text-accent',
  neutral: 'bg-neutral-soft text-muted',
  warn: 'bg-warn-soft text-warn',
  ok: 'bg-ok-soft text-ok',
  bad: 'bg-bad-soft text-bad',
}

export function Pill({ tone, children, title, dot }: { tone: Tone; children: ReactNode; title?: string; dot?: boolean }) {
  return (
    <span title={title} className={cx('inline-flex items-center gap-1 rounded-full px-2 py-px text-[11.5px] font-medium whitespace-nowrap', TONES[tone])}>
      {dot && <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

export function Tag({ children, title, active, onClick }: { children: ReactNode; title?: string; active?: boolean; onClick?: () => void }) {
  const Comp = onClick ? 'button' : 'span'
  return (
    <Comp
      type={onClick ? 'button' : undefined}
      title={title}
      onClick={onClick}
      className={cx(
        'inline-flex items-center rounded px-1.5 py-px text-[11.5px] whitespace-nowrap border',
        active ? 'border-accent bg-accent-soft text-accent' : 'border-line bg-sunken text-muted',
        onClick && 'cursor-pointer hover:border-line-strong',
      )}
    >
      {children}
    </Comp>
  )
}

type ButtonVariant = 'primary' | 'default' | 'ghost' | 'danger'

export function Button({ variant = 'default', size = 'md', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-45',
        size === 'sm' ? 'h-6 px-2 text-[12px]' : 'h-8 px-3 text-[13px]',
        variant === 'primary' && 'bg-accent text-accent-fg hover:opacity-90',
        variant === 'default' && 'border border-line-strong bg-panel text-fg hover:bg-sunken',
        variant === 'ghost' && 'text-muted hover:bg-sunken hover:text-fg',
        variant === 'danger' && 'border border-line-strong bg-panel text-bad hover:bg-bad-soft',
        className,
      )}
    />
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx('h-8 rounded-md border border-line-strong bg-panel px-2 text-[13px] text-fg placeholder:text-faint focus:border-accent focus:outline-none', className)} />
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cx('h-8 rounded-md border border-line-strong bg-panel px-2 text-[13px] text-fg focus:border-accent focus:outline-none', className)}>
      {children}
    </select>
  )
}

export function Card({ title, actions, children, className, bodyClass }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={cx('rounded-lg border border-line bg-panel', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-3 py-2">
          <h2 className="text-[13px] font-semibold">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={cx('p-3', bodyClass)}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate text-[18px] font-semibold tracking-tight">{title}</h1>
        {subtitle && <div className="mt-0.5 text-[12.5px] text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-[13px] text-muted">
      <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-accent" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-bad/30 bg-bad-soft px-3 py-2 text-[13px] text-bad">
      <span className="break-words">{message}</span>
      {retry && <Button size="sm" onClick={retry}>Retry</Button>}
    </div>
  )
}

export function Notice({ tone = 'neutral', children }: { tone?: 'neutral' | 'warn' | 'ok'; children: ReactNode }) {
  return (
    <div className={cx('rounded-md px-3 py-2 text-[12.5px]', tone === 'warn' ? 'bg-warn-soft text-warn' : tone === 'ok' ? 'bg-ok-soft text-ok' : 'bg-sunken text-muted')}>{children}</div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-6 py-10 text-center">
      <div className="text-[13.5px] font-medium">{title}</div>
      {children && <div className="max-w-md text-[12.5px] text-muted">{children}</div>}
    </div>
  )
}

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx('flex flex-col gap-1', className)}>
      <span className="text-[12px] font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="text-[11.5px] text-faint">{hint}</span>}
    </label>
  )
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; disabled?: boolean }) {
  return (
    <label className={cx('inline-flex cursor-pointer items-center gap-2 text-[13px]', disabled && 'opacity-50')}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx('relative h-4 w-7 rounded-full transition-colors', checked ? 'bg-accent' : 'bg-line-strong')}
      >
        <span className={cx('absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all', checked ? 'left-3.5' : 'left-0.5')} />
      </button>
      {label}
    </label>
  )
}

/** Multi-select chips (modes, efforts, world-model conditions). */
export function ChipGroup<T extends string>({ options, value, onChange, labels, titles, single }: {
  options: readonly T[]
  value: T[]
  onChange: (v: T[]) => void
  labels?: Partial<Record<T, string>>
  titles?: Partial<Record<T, string>>
  single?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const on = value.includes(option)
        return (
          <button
            key={option}
            type="button"
            title={titles?.[option]}
            onClick={() => onChange(single ? [option] : on ? value.filter((v) => v !== option) : [...value, option])}
            className={cx('h-7 rounded-md border px-2.5 text-[12.5px]', on ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong bg-panel text-muted hover:text-fg')}
          >
            {labels?.[option] ?? option}
          </button>
        )
      })}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode; hidden?: boolean }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-0.5 border-b border-line">
      {tabs.filter((t) => !t.hidden).map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={cx('-mb-px border-b-2 px-3 py-1.5 text-[13px]', value === tab.id ? 'border-accent font-medium text-fg' : 'border-transparent text-muted hover:text-fg')}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

export function Collapsible({ title, children, defaultOpen = false, right }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean; right?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-md border border-line">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-[12.5px] hover:bg-sunken">
        <span className="flex items-center gap-1.5 font-medium"><span className="text-faint">{open ? '▾' : '▸'}</span>{title}</span>
        {right}
      </button>
      {open && <div className="border-t border-line p-3">{children}</div>}
    </div>
  )
}

export function KeyValues({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-[12.5px]">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words">{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Pre({ children, className }: { children: ReactNode; className?: string }) {
  return <pre className={cx('max-h-[480px] overflow-auto rounded-md bg-sunken p-2.5 font-mono text-[11.5px] leading-[1.5] whitespace-pre-wrap break-words', className)}>{children}</pre>
}

export function Mono({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return <span title={title} className={cx('font-mono text-[12px]', className)}>{children}</span>
}
