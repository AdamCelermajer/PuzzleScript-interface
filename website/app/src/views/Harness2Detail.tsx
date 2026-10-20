import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, q } from '../api/client'
import type { RunRecord } from '../api/types'
import { Card, ErrorBox, Loading, cx } from '../components/ui'
import { BaselineDetail } from './BaselineDetail'

const ROLE: Record<string, string> = { base: 'starting harness', inv: 'general edit', dom: 'game-specific edit', agg: 'composed', c: 'sequential step', final: 'fresh run of the adopted harness' }
const role = (label: string) => ROLE[label.replace(/\d+$/, '')] ?? ''

/** Harness²: every rollout is a full direct-player run under rollouts/<label>; pick one to replay. */
export function Harness2Detail({ runId, live }: { runId: string; live?: boolean }) {
  const record = useQuery({
    queryKey: ['record', runId, 0],
    queryFn: ({ signal }) => api.get<RunRecord>(`/record${q({ run: runId, events_limit: 0 })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
  const [picked, setPicked] = useState<string | null>(null)
  if (record.isLoading) return <Loading label="Reading rollouts…" />
  if (record.error) return <ErrorBox error={record.error} retry={() => record.refetch()} />
  const rollouts = record.data?.rollouts ?? []
  const adoption = record.data?.adoption
  const label = picked ?? rollouts.at(-1)?.label ?? null
  return (
    <div className="flex flex-col gap-4">
      <Card title="Rollouts" actions={adoption?.adopted_label ? <span className="text-[12px] text-muted">adopted {adoption.adopted_label} · best {adoption.best_of_pool_levels ?? '—'} levels</span> : undefined}>
        {rollouts.length ? (
          <div className="flex flex-wrap gap-1.5">
            {rollouts.map((r) => {
              const levels = r.result?.levels_completed ?? r.latest_transition?.after?.levels_completed
              const actions = r.result?.action_count ?? r.latest_transition?.action_index
              return (
                <button key={r.label} type="button" onClick={() => setPicked(r.label)} title={role(r.label)}
                  className={cx('flex flex-col rounded-md border px-2.5 py-1 text-left', r.label === label ? 'border-accent bg-accent-soft' : 'border-line-strong hover:bg-sunken')}>
                  <span className={cx('font-mono text-[12px]', r.label === label && 'text-accent')}>{r.label}{r.label === adoption?.adopted_label ? ' ★' : ''}</span>
                  <span className="text-[11px] text-muted">{String(levels ?? 0)} levels · {String(actions ?? 0)} actions{r.result ? '' : ' · playing'}</span>
                </button>
              )
            })}
          </div>
        ) : <div className="text-[12px] text-faint">No rollout has started yet.</div>}
        <div className="mt-2 text-[11.5px] text-muted">base = starting harness · inv / dom = general and game-specific edits · agg = composed · final = fresh run of the adopted harness (the reported result).</div>
      </Card>
      {label && <BaselineDetail key={label} runId={`${runId}/rollouts/${label}`} live={live} notes={false} />}
    </div>
  )
}
