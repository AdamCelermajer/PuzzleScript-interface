import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { isRealtime, isUrl, label, parseScorecard, type BoardCard, type Rating, type Scorecard } from '../lib/board'
import { cx } from './ui'

/** Slides and the PDF export show this many prior-work rows; the card page shows all. */
const PRIOR_ROWS_ON_SLIDE = 12

const RATING_STYLE: Record<Rating, string> = {
  strong: 'bg-ok-soft text-ok',
  partial: 'bg-warn-soft text-warn',
  weak: 'bg-bad-soft text-bad',
  'no evidence': 'bg-neutral-soft text-faint',
}

/** Renders a card's JSON artifact, or a quiet note while it does not exist yet. */
export function ArtifactView({ card, large }: { card: BoardCard; large?: boolean }) {
  const artifact = useQuery({
    queryKey: ['board-artifact', card.slug, card.artifact],
    enabled: Boolean(card.artifact),
    queryFn: ({ signal }) => api.get<unknown>(`/board/${encodeURIComponent(card.slug)}/artifact`, signal),
    retry: false,
    refetchInterval: (query) => (query.state.error ? 30_000 : false),
  })
  if (!card.artifact) return null
  if (artifact.isLoading) return <div className="text-[13px] text-faint">Loading {card.artifact}…</div>
  if (artifact.error) {
    const missing = artifact.error instanceof ApiError && artifact.error.status === 404
    return (
      <div className="rounded-lg border border-dashed border-line-strong px-4 py-3 text-[13px] text-muted">
        {missing ? 'Artifact not written yet: ' : 'Artifact could not be read: '}<span className="font-mono text-[12px]">{card.artifact}</span>
        {!missing && <div className="mt-1 text-[12px] text-bad">{(artifact.error as Error).message}</div>}
      </div>
    )
  }
  const scorecard = parseScorecard(artifact.data)
  if (scorecard) return <ScorecardTable data={scorecard} large={large} />
  if (isRealtime(artifact.data)) return <RealtimeView data={artifact.data} slug={card.slug} large={large} />
  return <pre className="max-h-96 overflow-auto rounded-lg bg-sunken p-3 text-[12px] whitespace-pre-wrap">{JSON.stringify(artifact.data, null, 2)}</pre>
}

function ScorecardTable({ data, large }: { data: Scorecard; large?: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  const active = open ? (() => { const [model, capability] = open.split('|'); return { model, capability, cell: data.cell(model, capability) } })() : null
  return (
    <div className="flex flex-col gap-3">
      <table className={cx('w-full border-separate border-spacing-0', large ? 'text-[17px]' : 'text-[13px]')}>
        <thead>
          <tr>
            <th className="border-b border-line px-3 py-2 text-left section-label">Capability</th>
            {data.models.map((m) => <th key={m} className="border-b border-line px-3 py-2 text-left font-semibold">{m}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.capabilities.map((capability) => (
            <tr key={capability}>
              <td className="border-b border-line px-3 py-2 font-medium">{capability}</td>
              {data.models.map((model) => {
                const key = `${model}|${capability}`
                const cell = data.cell(model, capability)
                return (
                  <td key={key} className="border-b border-line px-3 py-2">
                    <button
                      type="button"
                      onClick={() => setOpen(open === key ? null : key)}
                      title={cell.evidence.join('\n') || 'No evidence recorded'}
                      className={cx('rounded-md px-2 py-0.5 font-medium whitespace-nowrap', RATING_STYLE[cell.rating], open === key && 'ring-2 ring-fg/30', large ? 'text-[15px]' : 'text-[12px]')}
                    >
                      {cell.rating}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap gap-3 text-[12px] text-muted">
        {(Object.keys(RATING_STYLE) as Rating[]).map((r) => <span key={r} className="inline-flex items-center gap-1.5"><span className={cx('rounded px-1.5 py-px text-[11px]', RATING_STYLE[r])}>{r}</span></span>)}
        <span className="text-faint">Click a cell for its evidence.</span>
      </div>
      {active && (
        <div className={cx('rounded-lg border border-line bg-sunken p-3', large ? 'text-[16px]' : 'text-[13px]')}>
          <div className="mb-1 font-semibold">{active.model} · {active.capability} — <span className={cx('rounded px-1.5', RATING_STYLE[active.cell.rating])}>{active.cell.rating}</span></div>
          {active.cell.evidence.length ? <ul className="list-disc pl-5">{active.cell.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul> : <div className="text-faint">No evidence recorded.</div>}
          {active.cell.sources.length > 0 && <div className="mt-1 text-[12px] text-faint">Sources: {active.cell.sources.map((s, i) => <span key={i} className="mr-2 font-mono">{s}</span>)}</div>}
        </div>
      )}
      {data.interventions.length > 0 && (
        <div>
          <div className="section-label mb-1">Candidate interventions</div>
          <ol className={cx('flex flex-col gap-1 pl-5', large ? 'text-[16px]' : 'text-[13px]')} style={{ listStyle: 'decimal' }}>
            {data.interventions.map((item, i) => {
              if (!item || typeof item !== 'object') return <li key={i}>{String(item)}</li>
              const r = item as Record<string, unknown>
              const detail = [r.evidence, r.test && typeof r.test === 'object' ? `Test: ${JSON.stringify(r.test)}` : r.test].filter(Boolean).map(String).join('\n\n')
              return (
                <li key={i} title={detail || undefined}>
                  <span className="font-medium">{label(item)}</span>
                  {typeof r.capability === 'string' && <span className="ml-2 rounded bg-neutral-soft px-1.5 py-px text-[0.8em] text-muted">{r.capability}</span>}
                  {typeof r.description === 'string' && <span className="text-muted"> — {r.description}</span>}
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </div>
  )
}

/** A string, or an object rendered as "name — other fields". */
function Item({ value }: { value: unknown }) {
  if (value === null || typeof value !== 'object') return <>{String(value ?? '')}</>
  const record = value as Record<string, unknown>
  const name = label(value)
  const rest = Object.entries(record).filter(([k, v]) => !['name', 'title', 'label', 'id'].includes(k) && v !== null && v !== '')
  return (
    <>
      <span className="font-medium">{name}</span>
      {rest.map(([k, v]) => <span key={k} className="text-muted"> · {k.replaceAll('_', ' ')}: {typeof v === 'object' ? (Array.isArray(v) ? v.map(label).join(', ') : JSON.stringify(v)) : String(v)}</span>)}
    </>
  )
}

function RealtimeView({ data, slug, large }: { data: Record<string, unknown>; slug: string; large?: boolean }) {
  const text = large ? 'text-[16px]' : 'text-[13px]'
  const environments = Array.isArray(data.environments) ? (data.environments as Record<string, unknown>[]) : []
  const prior = Array.isArray(data.prior_work) ? (data.prior_work as Record<string, unknown>[]) : []
  const framework = (data.framework && typeof data.framework === 'object' ? data.framework : {}) as Record<string, unknown>
  const pitch = (data.pitch && typeof data.pitch === 'object' ? data.pitch : {}) as Record<string, unknown>
  const show = (part: string) => !['realtime-prior-work', 'realtime-environments', 'realtime-framework'].includes(slug) || slug === `realtime-${part}`
  const envColumns = [...new Set(environments.flatMap((e) => Object.keys(e)))].filter((k) => !['name', 'recommended'].includes(k)).slice(0, 5)
  return (
    <div className={cx('flex flex-col gap-4', text)}>
      {show('prior-work') && Object.keys(pitch).length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(pitch).map(([who, value]) => (
            <div key={who} className="rounded-lg border border-line p-3"><div className="section-label mb-1">Pitch for {who}</div><Item value={value} /></div>
          ))}
        </div>
      )}
      {show('prior-work') && prior.length > 0 && (
        <table className="w-full border-separate border-spacing-0">
          <thead><tr>{['Group', 'Work', 'Year', 'One line'].map((h) => <th key={h} className="border-b border-line px-2 py-1.5 text-left section-label">{h}</th>)}</tr></thead>
          <tbody>
            {(large ? prior.slice(0, PRIOR_ROWS_ON_SLIDE) : prior).map((p, i) => (
              <tr key={i}>
                <td className="border-b border-line px-2 py-1.5 align-top font-medium">{String(p.group ?? '')}</td>
                <td className="border-b border-line px-2 py-1.5 align-top">{typeof p.link === 'string' && isUrl(p.link) ? <a className="link" href={p.link} target="_blank" rel="noreferrer">{String(p.title ?? p.link)}</a> : String(p.title ?? '')}</td>
                <td className="border-b border-line px-2 py-1.5 align-top tabular-nums text-muted">{String(p.year ?? '')}</td>
                <td className="border-b border-line px-2 py-1.5 align-top text-muted">{String(p.one_line ?? '')}</td>
              </tr>
            ))}
            {large && prior.length > PRIOR_ROWS_ON_SLIDE && (
              <tr><td colSpan={4} className="px-2 py-1.5 text-muted">+{prior.length - PRIOR_ROWS_ON_SLIDE} more works in {[...new Set(prior.map((p) => String(p.group ?? '')))].filter(Boolean).length} groups — full table on the card and in the notes</td></tr>
            )}
          </tbody>
        </table>
      )}
      {show('environments') && environments.length > 0 && (
        <table className="w-full border-separate border-spacing-0">
          <thead><tr><th className="border-b border-line px-2 py-1.5 text-left section-label">Environment</th>{envColumns.map((c) => <th key={c} className="border-b border-line px-2 py-1.5 text-left section-label">{c.replaceAll('_', ' ')}</th>)}</tr></thead>
          <tbody>
            {environments.map((e, i) => (
              <tr key={i} className={e.recommended ? 'bg-ok-soft/50' : undefined}>
                <td className="border-b border-line px-2 py-1.5 align-top font-medium">{String(e.name ?? '')}{e.recommended ? <span className="ml-2 rounded bg-ok-soft px-1.5 py-px text-[11px] text-ok">recommended</span> : null}</td>
                {envColumns.map((c) => <td key={c} className="border-b border-line px-2 py-1.5 align-top text-muted">{Array.isArray(e[c]) ? (e[c] as unknown[]).map(label).join(', ') : typeof e[c] === 'object' && e[c] ? JSON.stringify(e[c]) : String(e[c] ?? '')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {show('framework') && (Array.isArray(framework.components) || Boolean(framework.first_experiment)) && (
        <div className="flex flex-col gap-3">
          {Array.isArray(framework.components) && (
            <div className="grid gap-2 md:grid-cols-2">
              {(framework.components as unknown[]).map((c, i) => <div key={i} className="rounded-lg border border-line p-3"><Item value={c} /></div>)}
            </div>
          )}
          {framework.first_experiment ? <div className="rounded-lg border border-line bg-sunken p-3"><div className="section-label mb-1">First experiment</div><Item value={framework.first_experiment} /></div> : null}
        </div>
      )}
    </div>
  )
}
