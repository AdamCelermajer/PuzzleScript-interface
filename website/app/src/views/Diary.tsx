import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, q } from '../api/client'
import type { DiaryEntry, DiaryThread } from '../api/types'
import { Markdown } from '../components/Markdown'
import { Button, Card, Empty, ErrorBox, Field, Input, Loading, Notice, PageHeader, Pill, Tag, cx } from '../components/ui'
import { SECTIONS, entrySlug, entryText, newEntryText, previewParts, today } from '../lib/diary'
import { runHref } from '../lib/runs'

function useThreads() {
  return useQuery({ queryKey: ['diary-threads'], queryFn: ({ signal }) => api.get<{ threads: DiaryThread[] }>('/diary/threads', signal), staleTime: 60_000 })
}

export function DiaryView() {
  const [params, setParams] = useSearchParams()
  const thread = params.get('thread') ?? ''
  const entries = useQuery({
    queryKey: ['diary', thread],
    queryFn: ({ signal }) => api.get<{ entries: DiaryEntry[]; errors: { file?: string; error?: string }[] }>(`/diary${q({ thread })}`, signal),
  })
  const threads = useThreads()
  const sorted = useMemo(() => [...(entries.data?.entries ?? [])].sort((a, b) => b.date.localeCompare(a.date) || b.slug.localeCompare(a.slug)), [entries.data])
  const info = threads.data?.threads.find((t) => t.id === thread)
  const exportQuery = q({ thread })
  return (
    <div className="mx-auto flex max-w-[980px] flex-col gap-4">
      <PageHeader
        title={info ? <>Diary · <span className="font-mono">{info.id}</span></> : 'Diary'}
        subtitle={info ? `${info.description || 'Unregistered thread'} · ${info.status} · ${info.entries} entries, ${info.first ?? '—'} to ${info.last ?? '—'}` : 'Dated research entries in docs/diary/ — Did / Found / Decided / Next'}
        actions={
          <>
            <a href={`/api/workbench/diary/export${q({ thread, format: 'html' })}`} target="_blank" rel="noreferrer" title="Entries since the last meeting entry; print from the new tab">
              <Button>Since last meeting · print</Button>
            </a>
            <a href={`/api/workbench/diary/export${exportQuery ? exportQuery + '&' : '?'}format=md`} download>
              <Button variant="ghost">Download .md</Button>
            </a>
            <Link to="/diary/new"><Button variant="primary">New entry</Button></Link>
          </>
        }
      />
      {threads.data && (
        <div className="flex flex-wrap gap-1.5">
          <Tag active={!thread} onClick={() => setParams({})}>all threads</Tag>
          {threads.data.threads.filter((t) => t.entries > 0).map((t) => (
            <Tag key={t.id} title={`${t.description} (${t.status})`} active={t.id === thread} onClick={() => setParams(t.id === thread ? {} : { thread: t.id })}>
              {t.id} <span className="ml-1 text-faint">{t.entries}</span>
            </Tag>
          ))}
        </div>
      )}
      {entries.data?.errors?.length ? <Notice tone="warn">{entries.data.errors.length} diary files could not be parsed: {entries.data.errors.map((e) => e.file ?? e.error).join(', ')}</Notice> : null}
      {entries.isLoading ? <Loading label="Reading the diary…" /> : entries.error ? <ErrorBox error={entries.error} retry={() => entries.refetch()} /> : !sorted.length ? (
        <Empty title="No entries">{thread ? 'No entry is tagged with this thread.' : <Link to="/diary/new">Write the first entry.</Link>}</Empty>
      ) : (
        <ol className="relative flex flex-col gap-3 border-l border-line pl-5">
          {sorted.map((entry) => <EntryCard key={entry.slug} entry={entry} activeThread={thread} onThread={(t) => setParams({ thread: t })} />)}
        </ol>
      )}
    </div>
  )
}

function EntryCard({ entry, activeThread, onThread }: { entry: DiaryEntry; activeThread: string; onThread: (t: string) => void }) {
  const did = entry.sections.did.split('\n').filter((l) => l.trim()).slice(0, 3).join('\n')
  return (
    <li className="relative">
      <span className="absolute top-2 -left-[25px] h-2 w-2 rounded-full border-2 border-panel bg-accent" />
      <div className="rounded-lg border border-line bg-panel px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[12px] text-muted">{entry.date}</span>
          <Link to={`/diary/${entry.slug}`} className="text-[14px] font-semibold text-fg">{entry.title}</Link>
          {entry.reconstructed && <Pill tone="neutral" >reconstructed</Pill>}
          <span className="ml-auto flex flex-wrap gap-1">
            {entry.threads.map((t) => <Tag key={t} active={t === activeThread} onClick={() => onThread(t)}>{t}</Tag>)}
          </span>
        </div>
        {did && <Markdown className="mt-1.5 text-[12.5px] text-muted">{did}</Markdown>}
        {entry.runs.length > 0 && <div className="mt-1 text-[11.5px] text-faint">{entry.runs.length} linked runs</div>}
      </div>
    </li>
  )
}

export function DiaryEntryView() {
  const { slug = '' } = useParams()
  const entry = useQuery({ queryKey: ['diary-entry', slug], queryFn: ({ signal }) => api.get<DiaryEntry>(`/diary/${encodeURIComponent(slug)}`, signal) })
  const e = entry.data
  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <Link to="/diary" className="text-[12px] text-muted">← Diary</Link>
      {entry.isLoading ? <Loading /> : entry.error ? <ErrorBox error={entry.error} /> : e && (
        <>
          <PageHeader
            title={e.title}
            subtitle={<span className="flex flex-wrap items-center gap-1.5"><span className="font-mono">{e.date}</span>{e.threads.map((t) => <Link key={t} to={`/diary?thread=${t}`}><Tag>{t}</Tag></Link>)}{e.reconstructed && <Pill tone="neutral">reconstructed after the fact</Pill>}</span>}
            actions={<Link to={`/diary/${e.slug}/edit`}><Button>Edit</Button></Link>}
          />
          {e.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
          <Card>
            {SECTIONS.map((s) => (
              <section key={s} className="mb-3 last:mb-0">
                <h2 className="mb-1 border-b border-line pb-0.5 text-[13.5px] font-semibold">{s}</h2>
                <Markdown className="text-[13px]">{e.sections[s.toLowerCase() as keyof DiaryEntry['sections']] || '—'}</Markdown>
              </section>
            ))}
          </Card>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Card title={`Runs (${e.runs.length})`}>
              {e.runs.length ? (
                <ul className="flex flex-col gap-1.5 text-[12.5px]">
                  {e.runs.map((r) => (
                    <li key={r.id} className="min-w-0">
                      {r.found ? <Link to={runHref(r.id)} className="font-mono text-[11.5px] break-all">{r.id}</Link> : <span className="font-mono text-[11.5px] break-all text-faint">{r.id} (not found)</span>}
                      <div className="text-[11.5px] text-muted">{r.linked === 'date' ? 'started that day' : 'linked'}{r.outcome ? ` · ${r.mode} · ${r.harness} · ${r.model} · ${r.outcome}` : ''}</div>
                    </li>
                  ))}
                </ul>
              ) : <span className="text-[12px] text-faint">No runs linked or started that day.</span>}
            </Card>
            <Card title="Commits & docs">
              <div className="flex flex-col gap-1 text-[12.5px]">
                {e.commits.map((c) => <span key={c} className="font-mono">{c}</span>)}
                {e.docs.map((d) => <span key={d} className="font-mono text-[11.5px] break-all text-muted">{d}</span>)}
                {!e.commits.length && !e.docs.length && <span className="text-faint">None recorded.</span>}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

export function DiaryEditView() {
  const { slug } = useParams()
  const creating = !slug
  const existing = useQuery({
    queryKey: ['diary-entry', slug],
    enabled: !creating,
    queryFn: ({ signal }) => api.get<DiaryEntry>(`/diary/${encodeURIComponent(slug!)}`, signal),
  })
  const threads = useThreads()
  if (!creating && existing.isLoading) return <Loading />
  if (!creating && existing.error) return <ErrorBox error={existing.error} />
  return <Editor key={slug ?? 'new'} slug={slug} initial={existing.data ? entryText(existing.data) : null} threads={threads.data?.threads ?? []} />
}

function Editor({ slug, initial, threads }: { slug?: string; initial: string | null; threads: DiaryThread[] }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const [date, setDate] = useState(today())
  const [title, setTitle] = useState('')
  const [chosen, setChosen] = useState<string[]>([])
  const [text, setText] = useState(initial ?? '')
  const creating = !slug
  const started = Boolean(text)
  const targetSlug = slug ?? entrySlug(date, title)
  const save = useMutation({
    mutationFn: () => api.put<{ created: boolean; entry: DiaryEntry; warnings: string[] }>(`/diary/${encodeURIComponent(targetSlug)}`, { text }),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['diary'] })
      client.invalidateQueries({ queryKey: ['diary-threads'] })
      client.setQueryData(['diary-entry', result.entry.slug], result.entry)
      navigate(`/diary/${result.entry.slug}`)
    },
  })
  const preview = previewParts(text)
  return (
    <div className="flex flex-col gap-4">
      <Link to={slug ? `/diary/${slug}` : '/diary'} className="text-[12px] text-muted">← {slug ? 'Entry' : 'Diary'}</Link>
      <PageHeader
        title={creating ? 'New diary entry' : `Edit · ${slug}`}
        subtitle="Raw markdown with front matter. The body must contain exactly ## Did, ## Found, ## Decided, ## Next."
        actions={started && <Button variant="primary" disabled={save.isPending || (creating && !title.trim())} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</Button>}
      />
      {creating && !started && (
        <Card title="Start from the template">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Date"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Title" className="min-w-72 flex-1"><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What happened" /></Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {threads.map((t) => <Tag key={t.id} title={t.description} active={chosen.includes(t.id)} onClick={() => setChosen(chosen.includes(t.id) ? chosen.filter((x) => x !== t.id) : [...chosen, t.id])}>{t.id}</Tag>)}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Button variant="primary" disabled={!title.trim() || !chosen.length} onClick={() => setText(newEntryText(date, title.trim(), chosen))}>Use template</Button>
            <span className="font-mono text-[11.5px] text-faint">{entrySlug(date, title || 'title')}.md</span>
          </div>
        </Card>
      )}
      {save.error && <ErrorBox error={save.error} />}
      {started && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); save.mutate() } }}
            spellCheck
            className={cx('min-h-[65vh] rounded-lg border border-line-strong bg-panel p-3 font-mono text-[12.5px] leading-[1.55] focus:border-accent focus:outline-none')}
          />
          <Card title={preview.title || 'Preview'} className="min-h-[65vh]">
            <Markdown className="text-[13px]">{preview.body}</Markdown>
          </Card>
        </div>
      )}
      {started && <div className="text-[11.5px] text-faint">Ctrl+Enter saves. Saved to docs/diary/{targetSlug}.md.</div>}
    </div>
  )
}
