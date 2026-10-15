import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as pdfjsLib from 'pdfjs-dist'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import 'pdfjs-dist/web/pdf_viewer.css'
import 'katex/dist/katex.min.css'
import { api, q } from '../api/client'
import { Button, Card, Empty, ErrorBox, Field, Input, Loading, Notice, Pill, Select, Tabs, cx } from '../components/ui'
import { CURATED_PAPERS, type DossierSection, type ImpactItem } from '../data/papers'
import { drawPdfUnderline, normalizeText, pdfAnchorForRange, rangeForQuote, rangeFromPdfAnchor, type PdfAnchor } from '../lib/paperAnchors'
import { renderResearchMarkdown } from '../lib/researchMarkdown'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.mjs', import.meta.url).href

const BASE = '/paper-investigation'
const STATUSES = ['unread', 'reading', 'finished'] as const
const PRESETS = [
  'Explain this in plain language and define every technical term I need.',
  'What evidence actually supports this claim, and what evidence is missing?',
  'Does this invalidate my thesis contribution, or only force a narrower claim? Be precise.',
  'Design the cleanest experiment that would distinguish this approach from mine.',
]
const SELECTED_KEY = 'puzzlescript.paper-investigation.selected-papers.v1'

interface PaperRecord {
  id: string
  title: string
  authors?: string
  status: (typeof STATUSES)[number]
  source_type?: string
  source_url?: string
  pdf_url?: string
  has_pdf?: boolean
  page_count?: number
  last_page?: number
  annotation_count?: number
  question_count?: number
}

interface Annotation {
  id: string
  quote: string
  page?: number | null
  section?: string
  view?: string
  anchor?: PdfAnchor | null
  comment?: string
  created_at?: string
}

interface Question {
  id: string
  question: string
  answer: string
  annotation_ids?: string[]
  created_at?: string
}

interface Passage {
  quote: string
  page: number | null
  section: string
  view: string
  anchor?: PdfAnchor | null
}

const pdfUrlFor = (paper: PaperRecord) =>
  paper.has_pdf ? `/api/workbench${BASE}/papers/${encodeURIComponent(paper.id)}/pdf` : paper.pdf_url || (paper.id === 'avo' ? CURATED_PAPERS.avo?.sourceUrl ?? '' : '')

function sourceType(paper: PaperRecord): string {
  const kind = { arxiv: 'arXiv paper', upload: 'Uploaded PDF', pdf_url: 'Linked PDF', project: 'Project report' }[paper.source_type ?? ''] ?? 'Paper'
  return `${kind}${paper.page_count ? ` · ${paper.page_count} pages` : ''}`
}

function readSelected(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(SELECTED_KEY) ?? '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

/** Paper investigation: library, PDF reader with underlines, comments and a Codex research copilot. */
export function PapersView() {
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const library = useQuery({ queryKey: ['papers'], queryFn: ({ signal }) => api.get<{ papers: PaperRecord[]; library_root: string }>(`${BASE}/papers`, signal) })
  const papers = library.data?.papers ?? []
  const activeId = params.get('paper') ?? (papers.find((p) => p.id === 'avo')?.id ?? papers[0]?.id ?? '')
  const active = papers.find((p) => p.id === activeId)
  const [filter, setFilter] = useState<'all' | PaperRecord['status']>('all')
  const [compare, setCompare] = useState<Set<string>>(() => new Set(readSelected()))
  const [importing, setImporting] = useState(false)
  useEffect(() => localStorage.setItem(SELECTED_KEY, JSON.stringify([...compare])), [compare])

  const counts = papers.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.status]: (acc[p.status] ?? 0) + 1 }), {})
  const shown = papers.filter((p) => filter === 'all' || p.status === filter)
  const updatePaper = (paper: PaperRecord) =>
    client.setQueryData<{ papers: PaperRecord[]; library_root: string }>(['papers'], (old) => old && { ...old, papers: old.papers.map((p) => (p.id === paper.id ? paper : p)) })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link to="/tools" className="text-[12px] text-muted">← Tools</Link>
          <h1 className="text-[18px] font-semibold tracking-tight">Paper investigation</h1>
          <div className="text-[12px] text-muted">
            {library.data ? `${papers.length} sources · ${counts.reading ?? 0} reading · ${counts.finished ?? 0} finished · ${library.data.library_root}` : 'Local paper library'}
          </div>
        </div>
        <Button variant="primary" onClick={() => setImporting(true)}>Add paper</Button>
      </div>
      {library.isLoading ? <Loading label="Reading the paper library…" /> : library.error ? <ErrorBox error={library.error} retry={() => library.refetch()} /> : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[250px_minmax(0,1fr)_380px]">
          <aside className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-1">
              {(['all', ...STATUSES] as const).map((f) => (
                <Button key={f} size="sm" variant={filter === f ? 'primary' : 'default'} onClick={() => setFilter(f)}>{f}{f !== 'all' && counts[f] ? ` ${counts[f]}` : ''}</Button>
              ))}
            </div>
            <div className="flex max-h-[78vh] flex-col gap-1.5 overflow-auto">
              {shown.map((paper) => (
                <div key={paper.id} className={cx('rounded-md border px-2.5 py-2', paper.id === activeId ? 'border-accent bg-accent-soft' : 'border-line bg-panel')}>
                  <button type="button" onClick={() => setParams({ paper: paper.id })} className="block w-full text-left">
                    <Pill tone={paper.status === 'reading' ? 'accent' : paper.status === 'finished' ? 'ok' : 'neutral'}>{paper.status}</Pill>
                    <div className="mt-1 text-[12.5px] leading-snug font-medium">{paper.title}</div>
                    <div className="text-[11px] text-muted">
                      {paper.page_count ? (paper.last_page ? `p. ${paper.last_page}/${paper.page_count}` : `${paper.page_count} pages`) : 'source saved'} · {paper.annotation_count ?? 0} underlines · {paper.question_count ?? 0} questions
                    </div>
                  </button>
                  <label className="mt-1 flex items-center gap-1.5 text-[11.5px] text-muted">
                    <input
                      type="checkbox"
                      checked={compare.has(paper.id) || paper.id === activeId}
                      disabled={paper.id === activeId}
                      onChange={(e) => setCompare((s) => { const n = new Set(s); if (e.target.checked) n.add(paper.id); else n.delete(paper.id); return n })}
                    />
                    Include in questions
                  </label>
                </div>
              ))}
              {!shown.length && <div className="p-3 text-[12px] text-faint">No papers in this reading state.</div>}
            </div>
          </aside>
          {active ? (
            <PaperWorkspace key={active.id} paper={active} comparePapers={[...new Set([active.id, ...[...compare].filter((id) => papers.some((p) => p.id === id))])]} onPaper={updatePaper} />
          ) : (
            <Empty title="No paper selected">Add a paper to start an investigation.</Empty>
          )}
        </div>
      )}
      {importing && <ImportDialog onClose={() => setImporting(false)} onImported={(paper) => { setImporting(false); client.invalidateQueries({ queryKey: ['papers'] }); setParams({ paper: paper.id }) }} />}
    </div>
  )
}

function PaperWorkspace({ paper, comparePapers, onPaper }: { paper: PaperRecord; comparePapers: string[]; onPaper: (p: PaperRecord) => void }) {
  const curated = CURATED_PAPERS[paper.id]
  const detail = useQuery({
    queryKey: ['paper', paper.id],
    queryFn: ({ signal }) => api.get<{ paper: PaperRecord; annotations: Annotation[]; questions: Question[] }>(`${BASE}/papers/${encodeURIComponent(paper.id)}`, signal),
  })
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  useEffect(() => {
    if (detail.data) {
      setAnnotations(detail.data.annotations ?? [])
      setQuestions(detail.data.questions ?? [])
    }
  }, [detail.data])
  const [linked, setLinked] = useState<Set<string>>(new Set())
  const [passage, setPassage] = useState<Passage | null>(null)
  const [toolbar, setToolbar] = useState<{ left: number; top: number } | null>(null)
  const [tab, setTab] = useState<'source' | 'dossier'>(pdfUrlFor(paper) ? 'source' : 'dossier')
  const [message, setMessage] = useState('')
  const [draft, setDraft] = useState('')
  const readerRef = useRef<HTMLDivElement>(null)
  const pdfUrl = pdfUrlFor(paper)

  const toggleLink = useCallback((id: string) => setLinked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n }), [])

  const captureSelection = () => {
    const selection = window.getSelection()
    if (!selection || selection.isCollapsed || !selection.rangeCount) return
    const range = selection.getRangeAt(0)
    const base = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE ? (range.commonAncestorContainer as Element) : range.commonAncestorContainer.parentElement
    const surface = base?.closest<HTMLElement>('.pdf-page, [data-annotatable]')
    if (!surface || !readerRef.current?.contains(surface)) return
    const quote = selection.toString().replace(/\s+/g, ' ').trim()
    if (quote.length < 3) return
    const isPage = surface.matches('.pdf-page')
    setPassage({
      quote: quote.slice(0, 5000),
      page: surface.dataset.pageNumber ? Number(surface.dataset.pageNumber) : null,
      section: surface.dataset.sectionLabel || (isPage ? `${curated?.label ?? paper.title} page ${surface.dataset.pageNumber}` : 'Investigation note'),
      view: isPage ? 'source' : surface.dataset.view ?? 'dossier',
      anchor: isPage ? pdfAnchorForRange(range, surface) : null,
    })
    const rect = [...range.getClientRects()].filter((r) => r.width > 1 && r.height > 1).at(-1)
    if (rect) setToolbar({ left: Math.min(Math.max(12, rect.left), window.innerWidth - 200), top: rect.top > 60 ? rect.top - 40 : rect.bottom + 8 })
  }

  const clearPassage = () => {
    setPassage(null)
    setToolbar(null)
    window.getSelection()?.removeAllRanges()
  }

  const saveAnnotation = async () => {
    if (!passage) return
    const id = globalThis.crypto?.randomUUID?.() ?? `annotation-${Date.now()}`
    const annotation: Annotation = { id, ...passage, anchor: passage.anchor ?? undefined, comment: '', created_at: new Date().toISOString() }
    setAnnotations((a) => [annotation, ...a])
    setLinked((s) => new Set(s).add(id))
    clearPassage()
    setMessage('Underline saved and attached. Ask your question on the right.')
    try {
      const saved = await api.post<{ annotation: Annotation }>(`${BASE}/papers/${encodeURIComponent(paper.id)}/annotations`, annotation)
      setAnnotations((a) => a.map((x) => (x.id === id ? saved.annotation : x)))
      onPaper({ ...paper, annotation_count: (paper.annotation_count ?? 0) + 1 })
    } catch (error) {
      setMessage(`Underline is visible but could not be saved: ${(error as Error).message}`)
    }
  }

  const deleteAnnotation = async (id: string) => {
    try {
      await api.del(`${BASE}/papers/${encodeURIComponent(paper.id)}/annotations/${encodeURIComponent(id)}`)
      setAnnotations((a) => a.filter((x) => x.id !== id))
      setLinked((s) => { const n = new Set(s); n.delete(id); return n })
      onPaper({ ...paper, annotation_count: Math.max(0, (paper.annotation_count ?? 1) - 1) })
    } catch (error) {
      setMessage(`Underline could not be deleted: ${(error as Error).message}`)
    }
  }

  const commentTimers = useRef(new Map<string, number>())
  const saveComment = (id: string, comment: string) => {
    setAnnotations((a) => a.map((x) => (x.id === id ? { ...x, comment } : x)))
    window.clearTimeout(commentTimers.current.get(id))
    commentTimers.current.set(id, window.setTimeout(() => {
      api.patch(`${BASE}/papers/${encodeURIComponent(paper.id)}/annotations/${encodeURIComponent(id)}`, { comment })
        .catch((error: Error) => setMessage(`Comment could not be saved: ${error.message}`))
    }, 450))
  }

  const setStatus = async (status: string) => {
    try {
      const result = await api.patch<{ paper: PaperRecord }>(`${BASE}/papers/${encodeURIComponent(paper.id)}`, { status })
      onPaper(result.paper)
    } catch (error) {
      setMessage(`Reading status could not be saved: ${(error as Error).message}`)
    }
  }

  const progressTimer = useRef<number>(0)
  const onPage = (page: number) => {
    if (!paper.has_pdf || page === paper.last_page) return
    window.clearTimeout(progressTimer.current)
    progressTimer.current = window.setTimeout(() => {
      api.patch<{ paper: PaperRecord }>(`${BASE}/papers/${encodeURIComponent(paper.id)}`, { last_page: page }).then((r) => onPaper(r.paper)).catch(() => undefined)
    }, 700)
  }

  // Dossier underlines: mark the first block containing each saved non-PDF quote.
  useEffect(() => {
    const container = readerRef.current
    if (!container || tab !== 'dossier') return
    container.querySelectorAll('.paper-underline').forEach((e) => e.classList.remove('paper-underline'))
    const blocks = [...container.querySelectorAll('[data-annotatable] p, [data-annotatable] li, [data-annotatable] h3')]
    for (const annotation of annotations.filter((a) => !a.page)) {
      const needle = normalizeText(annotation.quote)
      blocks.find((b) => normalizeText(b.textContent ?? '').includes(needle))?.classList.add('paper-underline')
    }
  }, [annotations, tab])

  useEffect(() => {
    const hide = () => setToolbar(null)
    window.addEventListener('resize', hide)
    return () => window.removeEventListener('resize', hide)
  }, [])

  const askAbout = (annotation: Annotation) => {
    setLinked((s) => new Set(s).add(annotation.id))
    setPassage({ quote: annotation.quote, page: annotation.page ?? null, section: annotation.section ?? '', view: annotation.view ?? 'source' })
    setDraft(annotation.comment ? `Explain this passage and evaluate my comment: ${annotation.comment}` : 'Explain this passage and tell me exactly why it matters for my thesis.')
  }

  return (
    <>
      <div className="flex min-w-0 flex-col gap-2">
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11.5px] text-muted">{curated?.type ?? sourceType(paper)}</div>
              <h2 className="text-[15px] leading-snug font-semibold">{paper.title || curated?.title}</h2>
              <div className="text-[12px] text-muted">{paper.authors || curated?.authors || 'Authors not recorded'}</div>
            </div>
            <div className="flex items-center gap-2">
              <Select value={paper.status} onChange={(e) => setStatus(e.target.value)} className="h-7 text-[12px]">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
              {(paper.source_url || pdfUrl) && <a href={paper.source_url || pdfUrl} target="_blank" rel="noreferrer" className="text-[12px]">Source ↗</a>}
            </div>
          </div>
          {curated && (
            <div className="mt-2 rounded-md bg-sunken px-3 py-2 text-[12.5px]">
              <div className="font-medium">{curated.verdict}</div>
              <div className="text-muted">{curated.verdictDetail}</div>
            </div>
          )}
        </Card>
        <Tabs value={tab} onChange={setTab} tabs={[{ id: 'source', label: 'Source PDF', hidden: !pdfUrl }, { id: 'dossier', label: curated ? 'Dossier & thesis impact' : 'Dossier' }]} />
        <div
          ref={readerRef}
          onMouseUp={() => window.setTimeout(captureSelection, 0)}
          onKeyUp={(e) => { if (e.key === 'Shift' || e.key.startsWith('Arrow')) window.setTimeout(captureSelection, 0) }}
          className="min-w-0"
        >
          {tab === 'source' && pdfUrl ? (
            <PdfReader url={pdfUrl} title={paper.title} annotations={annotations} linked={linked} onToggleLink={toggleLink} onPage={onPage} onScroll={() => setToolbar(null)} initialPage={paper.last_page} />
          ) : (
            <Dossier sections={curated?.dossier} impact={curated?.impact} pageCount={paper.page_count} />
          )}
        </div>
        {toolbar && passage && (
          <div className="fixed z-40 flex gap-1 rounded-md border border-line bg-panel p-1 shadow-lg" style={{ left: toolbar.left, top: toolbar.top }}>
            <Button size="sm" variant="primary" onClick={saveAnnotation}>Underline + attach</Button>
            <Button size="sm" variant="ghost" onClick={clearPassage}>✕</Button>
          </div>
        )}
      </div>
      <aside className="flex min-w-0 flex-col gap-3">
        {detail.isLoading ? <Loading /> : detail.error ? <ErrorBox error={detail.error} /> : (
          <>
            <Copilot
              paper={paper}
              label={curated?.label ?? paper.title}
              questions={questions}
              comparePapers={comparePapers}
              linked={linked}
              passage={passage}
              draft={draft}
              setDraft={setDraft}
              annotations={annotations}
              onUnlink={toggleLink}
              onAnswered={(question) => { setQuestions((qs) => [question, ...qs]); setLinked(new Set()); onPaper({ ...paper, question_count: (paper.question_count ?? 0) + 1 }) }}
              message={message}
              setMessage={setMessage}
            />
            <Card title={`Underlines · ${annotations.length} saved`}>
              {passage && (
                <div className="mb-2 rounded-md border border-accent/40 bg-accent-soft p-2 text-[12px]">
                  <div className="mb-1 text-[11px] font-medium text-accent">Selected passage</div>
                  <div className="line-clamp-4">{passage.quote}</div>
                  <div className="mt-1.5 flex gap-1.5"><Button size="sm" variant="primary" onClick={saveAnnotation}>Underline + attach</Button><Button size="sm" variant="ghost" onClick={clearPassage}>Clear</Button></div>
                </div>
              )}
              {!annotations.length && !passage && <div className="text-[12px] text-faint">Drag across text in the paper; a button appears beside the selection.</div>}
              <div className="flex max-h-[44vh] flex-col gap-2 overflow-auto">
                {annotations.map((a) => {
                  const asked = questions.filter((qq) => qq.annotation_ids?.includes(a.id)).length
                  return (
                    <div key={a.id} className={cx('rounded-md border p-2', linked.has(a.id) ? 'border-accent' : 'border-line')}>
                      <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
                        <span>{a.page ? `Page ${a.page}` : a.section}</span>
                        <button type="button" onClick={() => window.confirm('Delete this underline?') && deleteAnnotation(a.id)} className="hover:text-bad">Delete</button>
                      </div>
                      <blockquote className="border-l-2 border-warn pl-2 text-[12px]">{a.quote}</blockquote>
                      <textarea rows={2} value={a.comment ?? ''} onChange={(e) => saveComment(a.id, e.target.value)} placeholder="Why does this matter? What did it change?" className="mt-1.5 w-full rounded border border-line bg-panel p-1.5 text-[12px] focus:border-accent focus:outline-none" />
                      <div className="flex items-center justify-between gap-2 text-[11.5px]">
                        <label className="flex items-center gap-1 text-muted"><input type="checkbox" checked={linked.has(a.id)} onChange={() => toggleLink(a.id)} /> Link to next question</label>
                        <button type="button" onClick={() => askAbout(a)} className="text-accent hover:underline">Ask about this</button>
                      </div>
                      {asked > 0 && <div className="text-[11px] text-faint">{asked} linked question{asked === 1 ? '' : 's'}</div>}
                    </div>
                  )
                })}
              </div>
            </Card>
          </>
        )}
      </aside>
    </>
  )
}

function Dossier({ sections, impact, pageCount }: { sections?: DossierSection[]; impact?: ImpactItem[]; pageCount?: number }) {
  const list = sections ?? [{
    label: 'Library record', title: 'Build the investigation from the source', tone: 'mechanism', locator: pageCount ? `${pageCount} PDF pages` : 'Saved source',
    paragraphs: ['This paper is saved locally with extracted text, reading progress, underlines, comments, and Codex questions.', 'Underline a passage and ask a question to create a source-linked investigation trail. Add your own thesis consequence as a comment on the evidence that changed your view.'],
  }]
  const impacts = impact ?? [{ status: 'experiment', title: 'Thesis impact is not pre-written', body: 'Link the decisive passages to Codex questions, then record what survives, what changes, and which experiment would settle the disagreement.' }]
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {list.map((s) => (
          <article key={s.title} data-annotatable data-section-label={s.title} data-view="dossier" className="rounded-lg border border-line bg-panel p-3 text-[13px]">
            <div className="flex justify-between gap-2 text-[11px] text-faint"><span className="font-medium tracking-wide uppercase">{s.label}</span><span>{s.locator}</span></div>
            <h3 className="mt-1 mb-1.5 text-[13.5px] font-semibold">{s.title}</h3>
            {s.paragraphs?.map((p, i) => <p key={i} className="mb-1.5 leading-relaxed">{p}</p>)}
            {s.bullets && <ul className="list-disc pl-5">{s.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
          </article>
        ))}
      </div>
      <h3 className="mt-1 text-[13px] font-semibold">Thesis impact</h3>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {impacts.map((item) => (
          <article key={item.title} data-annotatable data-section-label={item.title} data-view="impact" className="rounded-lg border border-line bg-panel p-3 text-[13px]">
            <Pill tone={item.status === 'threat' ? 'bad' : item.status === 'change' ? 'warn' : item.status === 'survives' ? 'ok' : 'accent'}>{item.status}</Pill>
            <h3 className="mt-1.5 mb-1 text-[13.5px] font-semibold">{item.title}</h3>
            <p className="leading-relaxed">{item.body}</p>
          </article>
        ))}
      </div>
    </div>
  )
}

/** pdf.js pages with a selectable text layer; underlines are redrawn from saved anchors. */
function PdfReader({ url, title, annotations, linked, onToggleLink, onPage, onScroll, initialPage }: {
  url: string
  title: string
  annotations: Annotation[]
  linked: Set<string>
  onToggleLink: (id: string) => void
  onPage: (page: number) => void
  onScroll: () => void
  initialPage?: number
}) {
  const container = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<{ status: 'loading' | 'ready' | 'error'; error?: string; pages: number; version: number }>({ status: 'loading', pages: 0, version: 0 })
  const restoredPage = useRef(false)

  const fitPages = useCallback(() => {
    const element = container.current
    if (!element) return
    const width = Math.max(280, element.clientWidth - 24)
    element.querySelectorAll<HTMLElement>('.pdf-page').forEach((page) => {
      const rendered = Number(page.dataset.renderWidth)
      if (!rendered) return
      const scale = Math.min(1, width / rendered)
      page.dataset.displayScale = String(scale)
      page.style.zoom = String(scale)
    })
  }, [])

  useEffect(() => {
    const element = container.current
    if (!element) return
    let cancelled = false
    element.replaceChildren()
    setState({ status: 'loading', pages: 0, version: 0 })
    ;(async () => {
      try {
        const pdf = await pdfjsLib.getDocument({ url }).promise
        if (cancelled) return
        for (let number = 1; number <= pdf.numPages; number += 1) {
          const page = await pdf.getPage(number)
          if (cancelled) return
          const viewport = page.getViewport({ scale: 1.3 })
          const wrapper = document.createElement('article')
          wrapper.className = 'pdf-page'
          wrapper.dataset.pageNumber = String(number)
          wrapper.dataset.renderWidth = String(viewport.width)
          wrapper.style.width = `${viewport.width}px`
          wrapper.style.height = `${viewport.height}px`
          wrapper.style.setProperty('--scale-factor', String(viewport.scale))
          const canvas = document.createElement('canvas')
          const ratio = Math.min(window.devicePixelRatio || 1, 2)
          canvas.width = Math.floor(viewport.width * ratio)
          canvas.height = Math.floor(viewport.height * ratio)
          canvas.style.width = `${viewport.width}px`
          canvas.style.height = `${viewport.height}px`
          wrapper.appendChild(canvas)
          element.appendChild(wrapper)
          fitPages()
          await page.render({ canvas, canvasContext: canvas.getContext('2d', { alpha: false })!, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] }).promise
          const textLayer = new TextLayerBuilder({ pdfPage: page, onAppend: (layer: HTMLElement) => wrapper.appendChild(layer) })
          // The old page omitted `images` (image hit-testing); pdf.js treats it as optional at runtime.
          await textLayer.render({ viewport, images: null } as unknown as Parameters<TextLayerBuilder['render']>[0])
          if (number === 1 || number === pdf.numPages) setState({ status: 'ready', pages: pdf.numPages, version: number })
        }
      } catch (error) {
        if (!cancelled) setState({ status: 'error', error: (error as Error).message, pages: 0, version: 0 })
      }
    })()
    return () => { cancelled = true }
  }, [url, fitPages])

  // Redraw underlines whenever pages, annotations or links change.
  useEffect(() => {
    const element = container.current
    if (!element) return
    element.querySelectorAll('[data-pdf-underline]').forEach((u) => u.remove())
    for (const annotation of annotations) {
      if (!annotation.page) continue
      const page = element.querySelector<HTMLElement>(`.pdf-page[data-page-number="${annotation.page}"]`)
      if (!page) continue
      const range = rangeFromPdfAnchor(page, annotation.anchor) ?? rangeForQuote([...page.querySelectorAll('.textLayer span')], annotation.quote)
      if (range) drawPdfUnderline(page, range, annotation.id, linked.has(annotation.id))
    }
  }, [annotations, linked, state.version])

  // Return to the last read page once it is rendered.
  useEffect(() => {
    if (restoredPage.current || !initialPage || initialPage < 2) return
    const page = container.current?.querySelector<HTMLElement>(`.pdf-page[data-page-number="${initialPage}"]`)
    if (page && container.current) {
      restoredPage.current = true
      container.current.scrollTop = page.offsetTop - 8
    }
  }, [state.version, initialPage])

  useEffect(() => {
    const element = container.current
    if (!element) return
    let timer = 0
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => { fitPages(); setState((s) => ({ ...s, version: s.version + 0.001 })) }, 180)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [fitPages])

  const handleScroll = () => {
    onScroll()
    const element = container.current
    if (!element) return
    const top = element.getBoundingClientRect().top
    const nearest = [...element.querySelectorAll<HTMLElement>('.pdf-page')]
      .map((page) => ({ page, distance: Math.abs(page.getBoundingClientRect().top - top - 12) }))
      .sort((a, b) => a.distance - b.distance)[0]?.page
    const number = Number(nearest?.dataset.pageNumber ?? 0)
    if (number) onPage(number)
  }

  return (
    <div className="relative">
      {state.status === 'loading' && <div className="absolute top-2 left-2 z-10"><Pill tone="neutral">Loading PDF…</Pill></div>}
      {state.status === 'error' && <ErrorBox error={`The in-page PDF could not be loaded: ${state.error}`} />}
      <div
        ref={container}
        aria-label={title}
        onScroll={handleScroll}
        onClick={(e) => { const id = (e.target as HTMLElement).closest<HTMLElement>('[data-pdf-underline]')?.dataset.pdfUnderline; if (id) onToggleLink(id) }}
        onKeyDown={(e) => { const target = e.target as HTMLElement; if ((e.key === 'Enter' || e.key === ' ') && target.dataset.pdfUnderline) { e.preventDefault(); onToggleLink(target.dataset.pdfUnderline) } }}
        className="flex h-[78vh] flex-col items-center gap-3 overflow-auto rounded-lg border border-line bg-sunken p-3"
      />
    </div>
  )
}

function Copilot({ paper, label, questions, comparePapers, linked, passage, draft, setDraft, annotations, onUnlink, onAnswered, message, setMessage }: {
  paper: PaperRecord
  label: string
  questions: Question[]
  comparePapers: string[]
  linked: Set<string>
  passage: Passage | null
  draft: string
  setDraft: (v: string) => void
  annotations: Annotation[]
  onUnlink: (id: string) => void
  onAnswered: (q: Question) => void
  message: string
  setMessage: (v: string) => void
}) {
  const status = useQuery({ queryKey: ['codex-status'], queryFn: ({ signal }) => api.get<{ available?: boolean; logged_in?: boolean }>('/codex/status', signal), staleTime: 60_000, retry: false })
  const ready = Boolean(status.data?.available && status.data?.logged_in)
  const [pending, setPending] = useState<string | null>(null)
  const thread = useRef<HTMLDivElement>(null)
  const history = useMemo(() => questions.slice().reverse().flatMap((qq) => [{ role: 'user', content: qq.question }, { role: 'assistant', content: qq.answer }]), [questions])
  useEffect(() => { thread.current?.scrollTo(0, thread.current.scrollHeight) }, [history.length, pending])
  const linkedAnnotations = annotations.filter((a) => linked.has(a.id))

  const ask = async () => {
    const question = draft.trim()
    if (!question || pending) return
    setPending(question)
    setDraft('')
    const annotationIds = [...linked]
    setMessage(`Auditing ${comparePapers.length} source${comparePapers.length === 1 ? '' : 's'} and ${annotationIds.length} linked underline${annotationIds.length === 1 ? '' : 's'}…`)
    try {
      const result = await api.post<{ answer: string; question_id: string }>(`${BASE}/ask`, {
        paper_ids: comparePapers, annotation_ids: annotationIds, question, selected_passage: passage?.quote ?? '', history: history.slice(-8),
      })
      onAnswered({ id: result.question_id, question, answer: result.answer, annotation_ids: annotationIds, created_at: new Date().toISOString() })
      setMessage('Answer and evidence links saved in each selected paper folder.')
    } catch (error) {
      setMessage(`The research copilot failed: ${(error as Error).message}`)
      setDraft(question)
    } finally {
      setPending(null)
    }
  }

  return (
    <Card title="Research copilot" actions={<Pill tone={ready ? 'ok' : 'warn'}>{status.isLoading ? 'checking…' : ready ? 'Codex ready' : 'Codex unavailable'}</Pill>} bodyClass="flex flex-col gap-2 p-3">
      <div ref={thread} className="flex max-h-[38vh] flex-col gap-2 overflow-auto">
        <div className="rounded-md bg-sunken p-2 text-[12px] text-muted">
          Context: {label}{comparePapers.length > 1 ? ` + ${comparePapers.length - 1} more papers` : ''}. Link underlines or include several papers; answers keep claim, evidence, missing control and thesis consequence separate.
        </div>
        {history.map((m, i) => (
          <div key={i} className={cx('rounded-md p-2 text-[12.5px]', m.role === 'user' ? 'ml-6 bg-accent-soft' : 'border border-line')}>
            <div className="mb-0.5 text-[10.5px] font-medium text-faint uppercase">{m.role === 'user' ? 'You' : 'Codex'}</div>
            {m.role === 'user' ? <p className="whitespace-pre-wrap">{m.content}</p> : <div className="prose-md" dangerouslySetInnerHTML={{ __html: renderResearchMarkdown(m.content) }} />}
          </div>
        ))}
        {pending && (
          <>
            <div className="ml-6 rounded-md bg-accent-soft p-2 text-[12.5px] whitespace-pre-wrap">{pending}</div>
            <div className="rounded-md border border-line p-2 text-[12px] text-muted"><span className="pulse-dot mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-accent" />Thinking…</div>
          </>
        )}
      </div>
      {linkedAnnotations.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {linkedAnnotations.map((a) => (
            <button key={a.id} type="button" onClick={() => onUnlink(a.id)} title="Remove link" className="max-w-full truncate rounded bg-accent-soft px-1.5 py-px text-[11px] text-accent">{a.quote.slice(0, 70)} ×</button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        {PRESETS.map((p) => <button key={p} type="button" onClick={() => setDraft(p)} className="rounded border border-line px-1.5 py-px text-left text-[11px] text-muted hover:text-fg">{p.split(/[,.?]/)[0]}…</button>)}
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); ask() } }}
        rows={3}
        placeholder={`Ask about ${paper.title.slice(0, 40)}… (Ctrl+Enter)`}
        className="rounded-md border border-line-strong bg-panel p-2 text-[12.5px] focus:border-accent focus:outline-none"
      />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] text-muted">{message}</span>
        <Button variant="primary" disabled={!draft.trim() || Boolean(pending)} onClick={ask}>{pending ? 'Thinking…' : 'Ask Codex'}</Button>
      </div>
    </Card>
  )
}

function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: (paper: PaperRecord) => void }) {
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [authors, setAuthors] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file && !url.trim()) { setError('Paste an arXiv/PDF link or choose a PDF file.'); return }
    setBusy(true)
    setError(null)
    try {
      let result: { paper: PaperRecord }
      if (file) {
        const response = await fetch(`/api/workbench${BASE}/papers/upload${q({ filename: file.name, title, authors })}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`)
        result = payload
      } else {
        result = await api.post<{ paper: PaperRecord }>(`${BASE}/papers/import`, { url: url.trim(), title, authors })
      }
      onImported(result.paper)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <form onSubmit={submit} className="flex w-full max-w-lg flex-col gap-3 rounded-lg border border-line bg-panel p-4 shadow-xl">
        <h2 className="text-[15px] font-semibold">Add a paper</h2>
        <Field label="arXiv or PDF link"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://arxiv.org/abs/…" disabled={Boolean(file)} /></Field>
        <Field label="…or upload a PDF"><input type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Title (optional)"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Authors (optional)"><Input value={authors} onChange={(e) => setAuthors(e.target.value)} /></Field>
        </div>
        {busy && <Notice>Downloading, extracting selectable text and creating the paper folder…</Notice>}
        {error ? <ErrorBox error={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save paper'}</Button>
        </div>
      </form>
    </div>
  )
}
