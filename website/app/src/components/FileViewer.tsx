import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { readableFile } from '../lib/files'
import { Markdown } from './Markdown'
import { Card, ErrorBox, Loading, Pre, cx } from './ui'

/** A run's saved files: pick one on the left, read it rendered on the right (raw link kept). */
export function FileViewer({ files, url }: { files: string[]; url: (file: string) => string }) {
  const [file, setFile] = useState(files[0] ?? '')
  const image = file.endsWith('.png')
  const content = useQuery({
    queryKey: ['run-file', url(file)],
    enabled: Boolean(file) && !image,
    queryFn: ({ signal }) => api.text(url(file), signal),
    staleTime: 10_000,
  })
  const view = content.data === undefined ? null : readableFile(file, content.data)
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-[260px_minmax(0,1fr)]">
      <div className="flex max-h-[70vh] flex-col gap-0.5 overflow-auto">
        {files.map((f) => (
          <button key={f} type="button" onClick={() => setFile(f)} title={f}
            className={cx('truncate rounded px-2 py-1 text-left font-mono text-[12px]', f === file ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-sunken')}>
            {f}
          </button>
        ))}
      </div>
      <Card title={<span className="font-mono text-[12.5px]">{file}</span>} actions={<a href={url(file)} target="_blank" rel="noreferrer" className="text-[12px]">raw ↗</a>}>
        {image ? <img src={url(file)} alt={file} className="max-h-[60vh] w-auto [image-rendering:pixelated]" />
          : content.isLoading ? <Loading />
            : content.error ? <ErrorBox error={content.error} />
              : view?.kind === 'markdown' ? <Markdown>{view.text}</Markdown>
                : <>
                  {view?.note && <div className="mb-1 text-[11.5px] text-muted">{view.note}</div>}
                  <Pre className="max-h-[65vh]">{view?.text ?? ''}</Pre>
                </>}
      </Card>
    </div>
  )
}
