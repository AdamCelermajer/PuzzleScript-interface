import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, q } from '../api/client'
import { DiffView } from '../components/Diff'
import { Button, Empty, ErrorBox, Loading, Pre } from '../components/ui'
import { bytes } from '../lib/format'

/** workbench/record_routes.py /record/agent_files: every file the player wrote, version by version. */
interface Version { at: number; label: string; t: string; status: 'added' | 'changed' | 'deleted'; size: number }
export interface AgentFileList { recorded: boolean; files: { path: string; versions: Version[] }[] }
interface VersionText { label: string; status: string; size: number; text: string | null; previous_label: string | null; diff: string }

export function useAgentFiles(runId: string, live?: boolean) {
  return useQuery({
    queryKey: ['agent-files', runId],
    queryFn: ({ signal }) => api.get<AgentFileList>(`/record/agent_files${q({ run: runId })}`, signal),
    refetchInterval: live ? 5000 : false,
  })
}

/** Every file in the player's folder that it created or changed, and how each one changed move by move. */
export function AgentFiles({ runId, live }: { runId: string; live?: boolean }) {
  const list = useAgentFiles(runId, live)
  const [path, setPath] = useState('')
  const [picked, setPicked] = useState<number | null>(null)  // null = the latest version
  if (list.isLoading) return <Loading label="Reading the player's files…" />
  if (list.error) return <ErrorBox error={list.error} />
  const files = list.data?.files ?? []
  if (!files.length) return <Empty title="No files written yet">Every file the player creates or changes in its folder appears here.</Empty>
  const file = files.find((f) => f.path === path) ?? files[0]
  const versions = file.versions
  const at = versions.some((v) => v.at === picked) ? picked! : versions[versions.length - 1].at
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      <div className="flex flex-col gap-0.5">
        {files.map((f) => {
          const last = f.versions[f.versions.length - 1]
          return (
            <button key={f.path} onClick={() => { setPath(f.path); setPicked(null) }}
                    className={`rounded px-2 py-1.5 text-left ${f.path === file.path ? 'bg-hover' : 'hover:bg-hover'}`}>
              <div className={`font-mono text-[12.5px] break-all ${last.status === 'deleted' ? 'text-faint line-through' : ''}`}>{f.path}</div>
              <div className="text-[11px] text-faint">{f.versions.length} version{f.versions.length > 1 ? 's' : ''} · last {last.label}</div>
            </button>
          )
        })}
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {versions.map((v) => (
            <Button key={v.at} size="sm" variant={v.at === at ? 'primary' : 'default'} onClick={() => setPicked(v.at)}
                    title={`${v.status} · ${bytes(v.size)} · ${v.t}`}>
              {v.label}{v.status !== 'changed' ? ` (${v.status})` : ''}
            </Button>
          ))}
        </div>
        <Version key={`${file.path}@${at}`} runId={runId} path={file.path} at={at} />
      </div>
    </div>
  )
}

function Version({ runId, path, at }: { runId: string; path: string; at: number }) {
  const [whole, setWhole] = useState(false)
  const one = useQuery({
    queryKey: ['agent-file', runId, path, at],
    queryFn: ({ signal }) => api.get<VersionText>(`/record/agent_files/version${q({ run: runId, file: path, at })}`, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
  if (one.isLoading) return <Loading />
  if (one.error) return <ErrorBox error={one.error} />
  const v = one.data!
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        <span>{path} · {v.label} · {v.status} · {bytes(v.size)}</span>
        {v.text !== null && <Button size="sm" variant={whole ? 'primary' : 'default'} onClick={() => setWhole(!whole)}>{whole ? 'whole file' : 'changes'}</Button>}
      </div>
      {v.status !== 'deleted' && v.text === null ? <div className="text-[12.5px] text-muted">Too large to keep a copy.</div>
        : whole && v.text !== null ? <Pre>{v.text}</Pre>
        : <DiffView diff={v.diff} note={v.previous_label ? `vs ${v.previous_label}` : 'first version'} />}
    </div>
  )
}
