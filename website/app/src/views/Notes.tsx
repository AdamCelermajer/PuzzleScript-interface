import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { Markdown } from '../components/Markdown'
import { Button, Card, Empty, ErrorBox, Loading, Notice, PageHeader, Tabs } from '../components/ui'

interface NotesResponse {
  files: { file: string; markdown: string }[]
}

/** docs/notes/*.md: GET /notes lists the allowlisted files, POST /notes {file, markdown} saves one. */
export function NotesView() {
  const notes = useQuery({ queryKey: ['notes'], queryFn: ({ signal }) => api.get<NotesResponse>('/notes', signal) })
  const [params, setParams] = useSearchParams()
  const files = notes.data?.files ?? []
  const file = params.get('file') ?? files[0]?.file ?? ''
  const current = files.find((f) => f.file === file)
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-4">
      <Link to="/tools" className="text-[12px] text-muted">← Tools</Link>
      <PageHeader title="Notes" subtitle="docs/notes/ · markdown notebooks" />
      {notes.isLoading ? <Loading label="Reading notes…" /> : notes.error ? <ErrorBox error={notes.error} retry={() => notes.refetch()} /> : !files.length ? (
        <Empty title="No notes files found" />
      ) : (
        <>
          <Tabs value={file} onChange={(f) => setParams({ file: f }, { replace: true })} tabs={files.map((f) => ({ id: f.file, label: f.file.replace(/\.md$/, '') }))} />
          {current && <NoteEditor key={current.file} file={current.file} markdown={current.markdown} />}
        </>
      )}
    </div>
  )
}

function NoteEditor({ file, markdown }: { file: string; markdown: string }) {
  const client = useQueryClient()
  const [text, setText] = useState(markdown)
  const [editing, setEditing] = useState(false)
  const dirty = text !== markdown
  const save = useMutation({
    mutationFn: () => api.post<{ saved: boolean }>('/notes', { file, markdown: text }),
    onSuccess: () => {
      client.setQueryData<NotesResponse>(['notes'], (old) => old && { files: old.files.map((f) => (f.file === file ? { ...f, markdown: text } : f)) })
    },
  })

  // Ctrl/Cmd+S saves while this note is open.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        if (dirty && !save.isPending) save.mutate()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dirty, save])

  // Warn before leaving the page with unsaved edits.
  useEffect(() => {
    if (!dirty) return
    const onUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [dirty])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button variant={editing ? 'default' : 'primary'} onClick={() => setEditing(!editing)}>{editing ? 'Preview only' : 'Edit'}</Button>
        {editing && <Button variant="primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</Button>}
        {editing && dirty && <Button variant="ghost" onClick={() => setText(markdown)}>Discard changes</Button>}
        <span className="text-[11.5px] text-faint">{dirty ? 'Unsaved changes · Ctrl+S saves' : save.isSuccess ? 'Saved' : `docs/notes/${file}`}</span>
      </div>
      {save.error && <ErrorBox error={save.error} />}
      {save.isSuccess && !dirty && <Notice tone="ok">Saved docs/notes/{file}</Notice>}
      {editing ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck
            className="min-h-[68vh] rounded-lg border border-line-strong bg-panel p-3 font-mono text-[12.5px] leading-[1.55] focus:border-accent focus:outline-none"
          />
          <Card className="min-h-[68vh] overflow-auto"><Markdown className="text-[13px]">{text}</Markdown></Card>
        </div>
      ) : (
        <Card><Markdown className="text-[13.5px]">{text || '*Empty note*'}</Markdown></Card>
      )}
    </div>
  )
}
