import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, q } from '../api/client'
import { useBenchmarks, useCatalog, useFrameworks, useHarnesses } from '../api/hooks'
import type { Effort, Framework, FrameworkOption, Harness, LaunchResult, Preview } from '../api/types'
import { Button, Card, ChipGroup, Collapsible, Empty, ErrorBox, Field, Input, Loading, Notice, PageHeader, Pill, Select, Toggle, cx } from '../components/ui'
import { gameName } from '../lib/format'
import {
  DEFAULT_FORM, budgetText, buildRunRequest, estimateRuns, formProblems, frameworkChoices, groupPreview, isMulti, modelFitsHarness,
  providerPinApplies, recentModels, requestKey, usesOptimizer, withFrameworks, type FrameworkForm, type LaunchForm, type OptionField,
} from '../lib/launch'
import { harnessColor } from '../components/identity'

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'xhigh', 'max']
// v2: frameworks replaced the fixed baseline / baseline-plus / campaign modes.
const STORAGE = 'workbench.launch.form.v2'

function loadForm(): LaunchForm {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE) ?? 'null')
    return saved ? { ...DEFAULT_FORM, ...saved } : DEFAULT_FORM
  } catch {
    return DEFAULT_FORM
  }
}

export function LaunchView() {
  const harnesses = useHarnesses()
  const benchmarks = useBenchmarks()
  const frameworkList = useFrameworks()
  const frameworks = useMemo(() => frameworkList.data ?? [], [frameworkList.data])
  const catalog = useCatalog(30000)
  const recent = useMemo(() => recentModels(catalog.views), [catalog.views])
  const [saved, setForm] = useState<LaunchForm>(loadForm)
  const form = useMemo(() => (frameworks.length ? withFrameworks(saved, frameworks) : saved), [saved, frameworks])
  const navigate = useNavigate()
  const client = useQueryClient()
  const set = <K extends keyof LaunchForm>(key: K, value: LaunchForm[K]) => setForm(() => ({ ...form, [key]: value }))
  const setFramework = (id: string, entry: FrameworkForm) => set('frameworks', { ...form.frameworks, [id]: entry })

  useEffect(() => localStorage.setItem(STORAGE, JSON.stringify(form)), [form])

  const request = useMemo(() => buildRunRequest(form, frameworks), [form, frameworks])
  const key = requestKey(request)
  const problems = formProblems(form, frameworks)
  const list = harnesses.data ?? []
  const estimate = estimateRuns(form, list, frameworks)

  const preview = useMutation({ mutationFn: (body: typeof request) => api.post<Preview>('/runs/preview', body) })
  const [previewKey, setPreviewKey] = useState('')
  const launch = useMutation({
    mutationFn: (body: typeof request) => api.post<LaunchResult>('/runs', body),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['catalog'] })
      navigate(`/runs${q({ job: result.job_id })}`)
    },
  })
  const previewFresh = preview.data && previewKey === key && !preview.isPending

  const runPreview = () => {
    setPreviewKey(key)
    preview.mutate(request)
  }

  // Drop selected models that no selected harness can run any more.
  const selectedHarnesses = list.filter((h) => form.harnesses.includes(h.id))
  const strayModels = form.models.filter((m) => !selectedHarnesses.some((h) => modelFitsHarness(h, m)))

  const optimizer = usesOptimizer(form, frameworks)
  const choices = frameworkChoices(form, frameworks).length
  const pinApplies = providerPinApplies(form)
  const playable = (benchmarks.data?.games ?? []).filter((g) => g.status === 'playable')

  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-4">
      <PageHeader title="Launch" subtitle="One request expands into a run matrix: games × frameworks × harness/model × efforts × repeats." />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex flex-col gap-4">
          <Card title="1 · Frameworks">
            {frameworkList.isLoading ? <Loading label="Loading frameworks…" /> : frameworkList.error ? <ErrorBox error={frameworkList.error} retry={() => frameworkList.refetch()} /> : (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {frameworks.map((framework) => (
                  <FrameworkCard key={framework.id} framework={framework} entry={form.frameworks[framework.id]} onChange={(entry) => setFramework(framework.id, entry)} />
                ))}
              </div>
            )}
            {choices > 1 && <div className="mt-2 text-[11.5px] text-muted">The {choices} framework choices share game, model, effort and repeat, so their runs are directly comparable (same match id). Picking several values of an option launches one run per value.</div>}
          </Card>

          <Card title="2 · Harness and model">
            {harnesses.isLoading ? <Loading label="Checking harness readiness…" /> : harnesses.error ? <ErrorBox error={harnesses.error} retry={() => harnesses.refetch()} /> : (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
                  {list.map((h) => (
                    <HarnessCard key={h.id} harness={h} on={form.harnesses.includes(h.id)} onToggle={(on) => set('harnesses', on ? [...form.harnesses, h.id] : form.harnesses.filter((x) => x !== h.id))} />
                  ))}
                </div>
                {selectedHarnesses.map((h) => (
                  <ModelPicker key={h.id} harness={h} recent={recent} value={form.models} onChange={(models) => set('models', models)} />
                ))}
                {!selectedHarnesses.length && <div className="text-[12px] text-faint">Pick a harness to choose models.</div>}
                {strayModels.length > 0 && (
                  <Notice tone="warn">
                    No selected harness runs {strayModels.join(', ')}.{' '}
                    <button type="button" className="underline" onClick={() => set('models', form.models.filter((m) => !strayModels.includes(m)))}>Remove</button>
                  </Notice>
                )}
                <Field label="Effort">
                  <ChipGroup options={EFFORTS} value={form.efforts} onChange={(v) => set('efforts', v)} />
                </Field>
              </div>
            )}
          </Card>

          <Card title="3 · Games">
            <GamePicker games={playable.map((g) => ({ id: g.game_id, title: g.title, tier: g.tier, levels: g.levels }))} loading={benchmarks.isLoading} error={benchmarks.error} value={form.games} onChange={(v) => set('games', v)} />
          </Card>

          {optimizer && (
            <Card title="4 · Optimizer">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label="Optimizer model" hint="The outer agent: AVO's optimizer, Harness²'s improver (edits the player's harness files). Empty = same as each player model.">
                  <Select value={form.optimizerModel} onChange={(e) => set('optimizerModel', e.target.value)}>
                    <option value="">Same as player</option>
                    {[...new Set([...form.models, ...selectedHarnesses.flatMap((h) => (h.manual_model_ids ? [] : h.models.map((m) => m.id)))])].map((m) => <option key={m} value={m}>{m}</option>)}
                  </Select>
                </Field>
                <Field label="Optimizer effort">
                  <Select value={form.optimizerEffort} onChange={(e) => set('optimizerEffort', e.target.value as Effort | '')}>
                    <option value="">Same as player</option>
                    {EFFORTS.map((e) => <option key={e} value={e}>{e}</option>)}
                  </Select>
                </Field>
              </div>
            </Card>
          )}

          <Card title={`${optimizer ? 5 : 4} · Wall time and scheduling`}>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Wall time" hint="Clock-time cap; the run stops when it runs out. Harness² applies it to each player run and improver session." className="col-span-2">
                <div className="flex items-center gap-3">
                  <Toggle checked={form.unlimitedWall} onChange={(v) => set('unlimitedWall', v)} label="Unlimited" />
                  {!form.unlimitedWall && (
                    <span className="flex items-center gap-1.5">
                      <Input type="number" min={0.1} step={0.5} value={form.wallHours} onChange={(e) => set('wallHours', Number(e.target.value))} className="w-24" />
                      <span className="text-muted">hours per run</span>
                    </span>
                  )}
                </div>
              </Field>
              <Field label="Repeats" hint="Independent attempts">
                <Input type="number" min={1} max={20} value={form.repeats} onChange={(e) => set('repeats', Number(e.target.value))} />
              </Field>
              <Field label="Parallel" hint="Runs at once (1–6)">
                <Input type="number" min={1} max={6} value={form.parallel} onChange={(e) => set('parallel', Number(e.target.value))} />
              </Field>
              {pinApplies && (
                <Field label="OpenRouter provider pin" hint="Optional upstream slug, e.g. deepinfra">
                  <Input value={form.provider} onChange={(e) => set('provider', e.target.value)} placeholder="any" />
                </Field>
              )}
              <Field label="Label" hint="Becomes part of the batch folder" className="col-span-2">
                <Input value={form.label} maxLength={80} onChange={(e) => set('label', e.target.value)} placeholder="e.g. modality-qwen-harness-ladder" />
              </Field>
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-3 xl:sticky xl:top-0 xl:self-start">
          <Card title="Matrix" actions={<span className="text-[12px] text-muted">≤ {estimate} runs</span>}>
            <div className="flex flex-col gap-2">
              {problems.length > 0 ? (
                <ul className="list-disc pl-4 text-[12.5px] text-muted">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
              ) : (
                <div className="text-[12.5px] text-muted">Preview asks the API for the exact run list. No model calls happen until Launch.</div>
              )}
              <div className="flex gap-2">
                <Button onClick={runPreview} disabled={problems.length > 0 || preview.isPending}>{preview.isPending ? 'Previewing…' : previewFresh ? 'Refresh preview' : 'Preview'}</Button>
                <Button
                  variant="primary"
                  disabled={!previewFresh || launch.isPending || !preview.data?.count}
                  title={previewFresh ? '' : 'Preview the current selection first'}
                  onClick={() => window.confirm(`Launch ${preview.data?.count} runs? This starts paid model calls.`) && launch.mutate(request)}
                >
                  {launch.isPending ? 'Launching…' : previewFresh ? `Launch ${preview.data?.count} runs` : 'Launch'}
                </Button>
              </div>
              {preview.data && previewKey !== key && <div className="text-[11.5px] text-warn">Selection changed since the last preview.</div>}
              {preview.error && <ErrorBox error={preview.error} />}
              {launch.error && <ErrorBox error={launch.error} />}
            </div>
          </Card>
          {preview.data && previewKey === key && <PreviewList preview={preview.data} />}
        </div>
      </div>
    </div>
  )
}

function FrameworkCard({ framework, entry, onChange }: { framework: Framework; entry?: FrameworkForm; onChange: (entry: FrameworkForm) => void }) {
  if (!entry) return null
  const setValue = (name: string, value: OptionField) => onChange({ ...entry, values: { ...entry.values, [name]: value } })
  return (
    <div className={cx('flex flex-col gap-2 rounded-md border px-3 py-2', entry.on ? 'border-accent bg-accent-soft' : 'border-line-strong')}>
      <button type="button" onClick={() => onChange({ ...entry, on: !entry.on })} className="text-left">
        <div className={cx('text-[13px] font-medium', entry.on && 'text-accent')}>{entry.on ? '✓ ' : ''}{framework.label}</div>
        <div className="text-[11.5px] text-muted">{framework.description}</div>
      </button>
      {entry.on && framework.options.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {framework.options.map((option) => (
            <OptionInput key={option.name} option={option} value={entry.values[option.name]} onChange={(value) => setValue(option.name, value)} />
          ))}
        </div>
      )}
    </div>
  )
}

function OptionInput({ option, value, onChange }: { option: FrameworkOption; value: OptionField; onChange: (value: OptionField) => void }) {
  const label = option.name.replaceAll('_', ' ')
  if (isMulti(option)) {
    // Several values = one matched run per value.
    const values: (string | boolean)[] = option.kind === 'bool' ? [false, true] : option.choices
    const picked = Array.isArray(value) ? value : []
    const text = (v: string | boolean) => (typeof v === 'boolean' ? (v ? 'on' : 'off') : v)
    return (
      <Field label={label} hint={option.help} className="col-span-2">
        <ChipGroup options={values.map(text)} value={picked.map(text)} onChange={(chosen) => onChange(values.filter((v) => chosen.includes(text(v))))} />
      </Field>
    )
  }
  if (option.kind === 'int') {
    return (
      <Field label={label} hint={option.help}>
        <Input type="number" min={option.minimum ?? undefined} max={option.maximum ?? undefined} value={Number(value)} onChange={(e) => onChange(Number(e.target.value))} />
      </Field>
    )
  }
  return (
    <Field label={label} hint={option.help}>
      <Input value={String(value)} onChange={(e) => onChange(e.target.value)} />
    </Field>
  )
}

function HarnessCard({ harness, on, onToggle }: { harness: Harness; on: boolean; onToggle: (on: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onToggle(!on)}
      className={cx('flex flex-col gap-1 rounded-md border px-3 py-2 text-left', on ? 'border-accent bg-accent-soft' : 'border-line-strong hover:bg-sunken')}
      title={harness.missing.length ? `Missing: ${harness.missing.join('; ')}` : 'Credentials and image present'}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2 text-[13px] font-medium"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: harnessColor(harness.id) }} />{harness.label}{on ? ' ✓' : ''}</span>
        {harness.ready ? <Pill tone="ok">ready</Pill> : <Pill tone="warn">not ready</Pill>}
      </div>
      <div className="text-[11.5px] text-muted">{harness.id} · {harness.providers.join(', ')}</div>
      {!harness.ready && <div className="text-[11px] text-warn">{harness.missing.join(' · ')}</div>}
    </button>
  )
}

function ModelPicker({ harness, recent, value, onChange }: { harness: Harness; recent: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const [search, setSearch] = useState('')
  const [freeOnly, setFreeOnly] = useState(false)
  const [manual, setManual] = useState('')
  const big = harness.models.length > 24
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((m) => m !== id) : [...value, id])
  const needle = search.trim().toLowerCase()
  const shown = harness.models.filter((m) => (!freeOnly || m.free) && (!needle || `${m.id} ${m.label}`.toLowerCase().includes(needle)))
  const picked = value.filter((m) => modelFitsHarness(harness, m))
  const recentHere = recent.filter((m) => modelFitsHarness(harness, m)).slice(0, 8)
  return (
    <div className="rounded-md border border-line p-2.5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[12px] font-medium">{harness.label} models</span>
        {picked.map((m) => (
          <span key={m} className="inline-flex items-center gap-1 rounded bg-accent-soft px-1.5 py-px font-mono text-[11.5px] text-accent">
            {m}
            <button type="button" onClick={() => toggle(m)} aria-label={`Remove ${m}`} className="text-accent/70 hover:text-accent">×</button>
          </span>
        ))}
      </div>
      {(big || harness.manual_model_ids) && recentHere.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11.5px] text-faint">Recent</span>
          {recentHere.map((m) => (
            <button key={m} type="button" onClick={() => toggle(m)} className={cx('h-7 rounded-md border px-2 font-mono text-[11.5px]', value.includes(m) ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-muted hover:text-fg')}>
              {m}
            </button>
          ))}
        </div>
      )}
      {harness.model_catalogs?.filter((c) => !c.available || c.stale).map((c) => (
        <div key={c.provider} className="mb-2"><Notice tone="warn">{c.provider} catalog {c.available ? 'is stale' : 'unavailable'}{c.warning ? `: ${c.warning}` : ''}</Notice></div>
      ))}
      {big ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={`Search ${harness.models.length} models…`} className="w-64" />
            <Toggle checked={freeOnly} onChange={setFreeOnly} label="Free only" />
          </div>
          {needle || freeOnly ? (
            <div className="max-h-56 overflow-auto rounded border border-line">
              <table className="data-table">
                <thead><tr><th /><th>Model</th><th>Context</th><th>$/M in · out</th></tr></thead>
                <tbody>
                  {shown.slice(0, 80).map((m) => (
                    <tr key={m.id} className={cx(value.includes(m.id) && 'selected')} onClick={() => toggle(m.id)} style={{ cursor: 'pointer' }}>
                      <td><input type="checkbox" readOnly checked={value.includes(m.id)} /></td>
                      <td><div className="font-mono text-[11.5px]">{m.id}</div><div className="text-[11px] text-faint">{m.label}</div></td>
                      <td className="text-[12px] text-muted">{m.context ? `${Math.round(m.context / 1000)}k` : '—'}</td>
                      <td className="text-[12px] whitespace-nowrap text-muted">{m.free ? 'free' : `${m.input_price ?? '—'} · ${m.output_price ?? '—'}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {shown.length > 80 && <div className="p-1.5 text-center text-[11.5px] text-faint">{shown.length - 80} more; refine the search</div>}
              {!shown.length && <div className="p-3 text-center text-[12px] text-faint">No catalog model matches</div>}
            </div>
          ) : (
            <div className="text-[11.5px] text-faint">Type to search the public catalogs.</div>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {harness.models.map((m) => (
            <button key={m.id} type="button" onClick={() => toggle(m.id)} className={cx('h-7 rounded-md border px-2 font-mono text-[11.5px]', value.includes(m.id) ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-muted hover:text-fg')}>
              {m.id}
            </button>
          ))}
        </div>
      )}
      {harness.manual_model_ids && (
        <form
          className="mt-2 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            const id = manual.trim()
            if (id && !value.includes(id)) onChange([...value, id])
            setManual('')
          }}
        >
          <Input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="Manual id: openrouter/vendor/model or nanogpt/model" className="w-96" />
          <Button size="sm" type="submit" disabled={!manual.trim()}>Add</Button>
        </form>
      )}
    </div>
  )
}

function GamePicker({ games, loading, error, value, onChange }: {
  games: { id: string; title: string; tier: string | null; levels: number | null }[]
  loading: boolean
  error: unknown
  value: string[]
  onChange: (v: string[]) => void
}) {
  const [search, setSearch] = useState('')
  if (loading) return <Loading label="Loading benchmark games…" />
  if (error) return <ErrorBox error={error} />
  const needle = search.trim().toLowerCase()
  const shown = games.filter((g) => !needle || `${g.id} ${g.title}`.toLowerCase().includes(needle))
  const byId = new Map(games.map((g) => [g.id, g]))
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {value.map((id) => (
          <span key={id} className="inline-flex items-center gap-1 rounded bg-accent-soft px-1.5 py-px text-[12px] text-accent">
            {byId.get(id)?.title ?? id}
            <button type="button" onClick={() => onChange(value.filter((v) => v !== id))} aria-label={`Remove ${id}`}>×</button>
          </span>
        ))}
        {!value.length && <span className="text-[12px] text-faint">No game selected</span>}
        {value.length > 0 && <Button size="sm" variant="ghost" onClick={() => onChange([])}>Clear</Button>}
      </div>
      <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={`Search ${games.length} playable games…`} className="w-72" />
      <div className="max-h-56 overflow-auto rounded border border-line">
        {shown.length ? (
          <table className="data-table">
            <thead><tr><th /><th>Game</th><th>Tier</th><th>Levels</th></tr></thead>
            <tbody>
              {shown.map((g) => {
                const on = value.includes(g.id)
                return (
                  <tr key={g.id} className={cx(on && 'selected')} style={{ cursor: 'pointer' }} onClick={() => onChange(on ? value.filter((v) => v !== g.id) : [...value, g.id])}>
                    <td><input type="checkbox" readOnly checked={on} /></td>
                    <td><span className="font-medium">{g.title}</span> <span className="font-mono text-[11px] text-faint">{g.id}</span></td>
                    <td className="text-muted">{g.tier ?? '—'}</td>
                    <td className="text-muted">{g.levels ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : <Empty title="No game matches" />}
      </div>
    </div>
  )
}

function PreviewList({ preview }: { preview: Preview }) {
  return (
    <Card title={`${preview.count} runs · ${preview.parallel} at once`} bodyClass="p-0">
      {preview.warnings.length > 0 && <div className="flex flex-col gap-1 p-2">{preview.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}</div>}
      <div className="max-h-[56vh] overflow-auto">
        {groupPreview(preview.runs).map(([game, rows]) => (
          <div key={game} className="border-t border-line first:border-t-0">
            <div className="bg-sunken px-3 py-1 text-[12px] font-medium">{gameName(game)}</div>
            {rows.map((row, i) => (
              <div key={i} className="border-t border-line px-3 py-1.5 text-[12px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Pill tone="accent">{row.variant}</Pill>
                  <span className="text-muted">{row.harness}</span>
                  <span className="font-mono text-[11.5px]">{row.model}</span>
                  <span className="text-faint">· {row.effort}</span>
                  <span className="ml-auto text-[11px] text-faint">#{row.repeat} · {row.match_id}</span>
                </div>
                <div className="text-[11px] text-muted">
                  {budgetText(row)}
                  {row.optimizer_model && row.optimizer_model !== row.model ? ` · optimizer ${row.optimizer_model}` : ''}
                </div>
                <CommandLine command={row.command} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  )
}

function CommandLine({ command }: { command: string[] }): ReactNode {
  return (
    <div className="mt-1">
      <Collapsible title={<span className="text-[11px] text-faint">command</span>}>
        <code className="block font-mono text-[10.5px] break-all whitespace-pre-wrap text-muted">{command.join(' ')}</code>
      </Collapsible>
    </div>
  )
}
