import * as pdfjsLib from 'pdfjs-dist/build/pdf.mjs'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import DOMPurify from 'dompurify'
import katex from 'katex'
import { marked } from 'marked'
import 'pdfjs-dist/web/pdf_viewer.css'
import 'katex/dist/katex.min.css'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.mjs',
  import.meta.url,
).href

const root = document.querySelector('[data-paper-investigation]')

const papers = {
  avo: {
    label: 'AVO',
    type: 'Preprint · 12 pages · submitted 25 Mar 2026',
    title: 'AVO: Agentic Variation Operators for Autonomous Evolutionary Search',
    authors: 'Terry Chen, Zhifan Ye, Bing Xu, Zihao Ye, and collaborators · NVIDIA',
    sourceUrl: 'https://arxiv.org/pdf/2603.24517',
    verdict: 'Threatens fixed search orchestration, not diagnostic evaluation.',
    verdictDetail: 'AVO is evidence that the agent itself can own variation, testing, repair, and strategy shifts. It does not test whether the resulting knowledge is correct, transferable, or diagnosable in unfamiliar interactive worlds.',
    dossier: [
      {
        label: 'Core move',
        title: 'The coding agent becomes the variation operator',
        tone: 'claim',
        paragraphs: [
          'Earlier LLM-evolution systems keep sampling and population logic outside the model: a fixed framework selects parents, asks for one generated candidate, evaluates it, and updates the archive. AVO moves that whole variation step inside a long-running coding-agent loop.',
          'Its formal change is from Vary(P) = Generate(Sample(P)) to Vary(P) = Agent(P, K, f): the agent can inspect the full committed lineage P, consult a domain knowledge base K, invoke the scoring function f, edit code, diagnose failures, and decide when a candidate is worth committing.',
        ],
        locator: 'Sections 2.1 and 3.1, pp. 3–4',
      },
      {
        label: 'Actual system',
        title: 'A monotonic single lineage plus a stagnation supervisor',
        tone: 'mechanism',
        paragraphs: [
          'The evaluated instantiation is not a population with crossover. It starts from one seed kernel and keeps a new version only when it passes correctness and matches or improves the best committed benchmark score.',
          'Unsuccessful edits remain inside the agent trajectory but outside the published lineage. A supervisor watches for stalls or repetitive non-improving work and redirects the main agent toward fresh optimization directions.',
        ],
        locator: 'Sections 3.2–3.3, p. 5',
      },
      {
        label: 'Evidence',
        title: 'Seven days, 40 commits, more than 500 attempted directions',
        tone: 'evidence',
        paragraphs: [
          'An internally developed general-purpose coding agent, powered by unspecified frontier LLMs, optimized forward-pass attention kernels on NVIDIA B200 hardware. The agent had editing, shell, documentation, profiling, and persistent conversation-memory tools.',
          'Across a seven-day MHA run it produced 40 committed versions while exploring more than 500 internal optimization directions. The paper reports causal MHA gains of 0.4–3.5% over cuDNN and 5.0–10.5% over FlashAttention-4 across four tested sequence lengths. Shorter non-causal cases were within measurement noise; longer cases gained 1.8–2.4% over cuDNN.',
        ],
        locator: 'Sections 4.1–4.4, pp. 5–8',
      },
      {
        label: 'Transfer test',
        title: 'MHA optimizations adapted to GQA in about 30 minutes',
        tone: 'evidence',
        paragraphs: [
          'The evolved MHA kernel was then adapted by the agent to two grouped-query attention layouts. The paper reports gains across all tested GQA configurations, reaching 7.0% over cuDNN and 9.3% over FlashAttention-4 in the best causal case.',
          'This is useful engineering transfer within the same kernel family and hardware stack. It is not evidence of cross-domain transfer, new-task learning, or retention across an ordered curriculum.',
        ],
        locator: 'Section 4.3, pp. 6–7',
      },
      {
        label: 'Mechanistic evidence',
        title: 'Three optimization steps received local ablations',
        tone: 'evidence',
        bullets: [
          'Branchless accumulator rescaling plus a lighter fence: +8.1% non-causal, +1.6% causal geomean from v19 to v20.',
          'Overlap correction work with the second matrix-multiply stage: +1.1% non-causal, +0.4% causal from v29 to v30.',
          'Move registers from softmax warps to spilling correction warps: +2.1% non-causal and about 0% causal from v32 to v33.',
        ],
        locator: 'Section 5 and Table 1, pp. 8–10',
      },
      {
        label: 'Missing controls',
        title: 'The paper does not isolate why AVO wins',
        tone: 'limitation',
        bullets: [
          'No matched comparison against the same model in a fixed single-turn or fixed-workflow search harness.',
          'No ablation of full-lineage access, documentation access, persistent memory, testing tools, or the stagnation supervisor.',
          'The internal agent, model mixture, prompts, compute cost, complete failed trajectory, and evolved kernel code are not specified or released in the paper.',
          'One seven-day trajectory, one kernel family, one GPU generation, forward pass only, and a narrow BF16/head-dimension benchmark do not establish domain generality.',
          'The same benchmark suite guides evolution and final reporting, so the GQA adaptation is the stronger—but still nearby—generalization check.',
        ],
        locator: 'Critical reading of Sections 3–6',
      },
    ],
    impact: [
      {
        status: 'survives',
        title: 'Your benchmark contribution survives',
        body: 'PuzzleScript-World is an evaluation protocol: independent solving, goal-recognition, transition-prediction, and warm/cold transfer scores. AVO proposes a search operator and does not supply those diagnostics.',
      },
      {
        status: 'change',
        title: 'The agent architecture should become less prescriptive',
        body: 'Do not make periodic rule induction or a fixed orchestration loop part of the scientific claim. Treat agent-owned timing, tool use, repair, and strategy shifts as one harness condition.',
      },
      {
        status: 'baseline',
        title: 'AVO becomes a strong harness baseline',
        body: 'Compare a fixed rule-learning loop with a persistent agentic loop under the same model, observation, game, and budget. Score both on completion, exact next-state prediction, transfer, actions, tokens, time, and cost.',
      },
      {
        status: 'caution',
        title: 'Do not call the local client an AVO reproduction',
        body: 'The public paper omits the internal agent configuration. Your implementation can faithfully test AVO-inspired principles, but it cannot claim to reproduce NVIDIA’s unpublished system.',
      },
    ],
  },
  vista: {
    label: 'VISTA',
    type: 'Official project report · published 5 Aug 2026 · no paper released',
    title: 'VISTA: A Visual Harness for Reasoning in an Interactive World',
    authors: 'Qiushi Han, Keya Hu, Linlu Qiu, Cathy Wu, and Kaiming He · MIT',
    sourceUrl: 'https://vista-research.github.io/',
    verdict: 'Directly challenges necessity, not usefulness, of executable rules.',
    verdictDetail: 'VISTA shows that a strong multimodal model with lossless frame recall and free-form notes can solve all 25 public ARC-AGI-3 games without synthesizing an executable world model. It does not show what the agent learned, which harness component caused the gain, or whether the result generalizes to private games.',
    dossier: [
      {
        label: 'Publication status',
        title: 'There is no paper yet',
        tone: 'limitation',
        paragraphs: [
          'The authoritative source is an MIT project webpage dated 5 August 2026. It includes the method description, exact short prompt, per-game scores, and public replays, but it is not a peer-reviewed or arXiv paper.',
        ],
        locator: 'Official VISTA project report',
      },
      {
        label: 'Core move',
        title: 'Use fuzzy language reasoning instead of an executable program',
        tone: 'claim',
        paragraphs: [
          'VISTA gives a general-purpose multimodal model the rendered PNG observation, available actions, status, and progress. The model reasons in unrestricted natural language and records a compact, revisable game model in GUIDE.md, with WORKING.md as a level scratchpad.',
          'The authors explicitly contrast this with program-based agents that reconstruct state, transitions, and goals as executable code. Their claim is not that programs are impossible; it is that an implicit natural-language model can be sufficient for action selection on these games.',
        ],
        locator: 'Section 2, “Language reasoning”',
      },
      {
        label: 'Memory mechanism',
        title: 'Every returned frame remains available at full fidelity',
        tone: 'mechanism',
        paragraphs: [
          'The harness stores every environment frame with its turn and frame index. The agent can use inspect to revisit complete frames, intermediate animation frames, or cropped regions, and read_pixels to obtain exact colors.',
          'This is an external, lossless visual store—not ordinary context-window memory. The model chooses what old evidence to retrieve. Across context compaction, the frames, action history, and notes remain available.',
        ],
        locator: 'Section 2, “Lossless visual memory,” and Section 3',
      },
      {
        label: 'Prompt and loop',
        title: 'One short prompt, predict before play, revise after observation',
        tone: 'mechanism',
        paragraphs: [
          'The prompt asks the agent to complete the game with few actions, maintain a compact revisable model, state the expected visual result before each play call, describe all visible changes afterward, and keep durable versus working notes separate.',
          'One agent continues from the first observation to game completion. Looking back is optional and selected by the model rather than forced at a fixed point in the loop.',
        ],
        locator: 'Section 3, “The Complete Pipeline”',
      },
      {
        label: 'Evidence',
        title: 'Perfect completion with Opus; near-perfect RHAE with Sol',
        tone: 'evidence',
        paragraphs: [
          'The same prompt, tools, model, and reasoning effort were used across all 25 public games within each backend. Opus 5.0 at xhigh reports 100.00 RHAE. GPT-5.6 Sol at max reports 98.27, completes 25/25 games, and has 22 perfect game scores.',
          'RHAE charges environment actions but treats reasoning, read-only inspection, tokens, time, and tool calls as free. VISTA therefore demonstrates action efficiency, not total compute or economic efficiency.',
        ],
        locator: 'Section 4, “VISTA Results on ARC-AGI-3”',
      },
      {
        label: 'Missing controls',
        title: 'The result does not identify the causal ingredient',
        tone: 'limitation',
        bullets: [
          'No matched ablation removes lossless visual memory, notes, prediction-before-action, context continuation, or the coding-agent shell one at a time.',
          'System-level comparisons use different harnesses, models, efforts, and sometimes fallback procedures; they are rankings, not causal ablations.',
          'The representation check covers only Level 1 of two games in independent trajectories, so it does not establish broad invariance across text, 2D, and 3D inputs.',
          'All results are on public games. The authors explicitly say newer models may have seen them during training and that the private set is the real generalization test.',
          'Without an executable model, high task score alone cannot reveal whether the internal mechanics or goal hypothesis was correct, incomplete, or merely sufficient for the chosen actions.',
        ],
        locator: 'Critical reading of Sections 4–5',
      },
    ],
    impact: [
      {
        status: 'threat',
        title: 'A necessity claim is no longer defensible',
        body: 'You cannot claim that explicit executable rule learning is required to solve unfamiliar public ARC-AGI-3 games efficiently. VISTA is a direct counterexample at the system level.',
      },
      {
        status: 'survives',
        title: 'Your central diagnostic question becomes stronger',
        body: 'VISTA’s score cannot tell whether its natural-language model is faithful, which component helped, why a failure occurred, or what transferred. Those are exactly the gaps your separated protocol measures.',
      },
      {
        status: 'change',
        title: 'Explicit rules should be a treatment, not the thesis',
        body: 'Position verified executable rules as one architectural intervention to test against free-form notes, visual memory, and hybrids—not as the assumed correct representation.',
      },
      {
        status: 'experiment',
        title: 'The decisive experiment is now obvious',
        body: 'Use the same model and action budget across: minimal agent, VISTA-style notes plus visual recall, executable rules plus verification, and a hybrid. Measure actions, prediction fidelity, belief revision, transfer, tokens, time, and cost.',
      },
    ],
  },
}

const storageKeys = {
  legacyAnnotations: 'puzzlescript.paper-investigation.annotations.v1',
  legacyChats: 'puzzlescript.paper-investigation.chats.v1',
  paper: 'puzzlescript.paper-investigation.active-paper.v1',
  selectedPapers: 'puzzlescript.paper-investigation.selected-papers.v1',
}

let activePaperId = localStorage.getItem(storageKeys.paper) || 'avo'
let paperRecords = {}
let annotations = []
let questions = []
let selectedPaperIds = new Set(readStorage(storageKeys.selectedPapers, [activePaperId]))
let selectedAnnotationIds = new Set()
let selectedPassage = null
let selectedRange = null
let pdfPromise = null
let renderedPdfPaperId = ''
let pdfRenderToken = 0
let pdfResizeTimer = null
let libraryFilter = 'all'
let libraryAvailable = false
const commentSaveTimers = new Map()
let progressSaveTimer = null

function readStorage(key, fallback) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key))
    return parsed ?? fallback
  } catch {
    return fallback
  }
}

function writeStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]))
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, { cache: 'no-store', ...options })
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || `${response.status} ${response.statusText}`)
  return payload
}

function paperLabel(title, fallback) {
  if (papers[fallback]?.label) return papers[fallback].label
  const words = String(title || fallback).split(/\s+/).filter(Boolean)
  const acronym = words.slice(0, 5).map((word) => word[0]).join('').toUpperCase()
  return acronym.length >= 2 ? acronym : String(title || fallback).slice(0, 18)
}

function paperDetails(paperId) {
  const record = paperRecords[paperId] || {}
  const curated = papers[paperId] || {}
  const pageCount = record.page_count || 0
  const sourceType = record.source_type === 'arxiv'
    ? 'arXiv paper'
    : record.source_type === 'upload'
      ? 'Uploaded PDF'
      : record.source_type === 'pdf_url'
        ? 'Linked PDF'
        : record.source_type === 'project'
          ? 'Project report'
          : 'Paper'
  const genericDossier = [{
    label: 'Library record',
    title: 'Build the investigation from the source',
    tone: 'mechanism',
    paragraphs: [
      'This paper is saved locally with extracted text, reading progress, underlines, comments, and Codex questions.',
      'Underline a passage and ask a question to create a source-linked investigation trail. Add your own thesis consequence as a comment on the evidence that changed your view.',
    ],
    locator: pageCount ? `${pageCount} PDF pages` : 'Saved source',
  }]
  const genericImpact = [{
    status: 'experiment',
    title: 'Thesis impact is not pre-written',
    body: 'Link the decisive passages to Codex questions, then record what survives, what changes, and which experiment would settle the disagreement.',
  }]
  return {
    id: paperId,
    ...record,
    ...curated,
    label: curated.label || paperLabel(record.title, paperId),
    type: curated.type || `${sourceType}${pageCount ? ` · ${pageCount} pages` : ''}`,
    title: record.title || curated.title || paperId,
    authors: record.authors || curated.authors || 'Authors not recorded',
    sourceUrl: record.source_url || record.pdf_url || curated.sourceUrl || '',
    pdfUrl: record.has_pdf
      ? `/api/workbench/paper-investigation/papers/${encodeURIComponent(paperId)}/pdf`
      : record.pdf_url || (paperId === 'avo' ? curated.sourceUrl : ''),
    status: record.status || 'unread',
    dossier: curated.dossier || genericDossier,
    impact: curated.impact || genericImpact,
    verdict: curated.verdict || 'Investigation in progress.',
    verdictDetail: curated.verdictDetail || 'The source is in your library. Use linked underlines and questions to decide precisely how it changes the thesis.',
  }
}

function comparisonSelection() {
  selectedPaperIds.add(activePaperId)
  return [...selectedPaperIds].filter((paperId) => paperRecords[paperId] || papers[paperId])
}

function renderLibrary() {
  const records = Object.values(paperRecords)
  const filtered = records.filter((paper) => libraryFilter === 'all' || paper.status === libraryFilter)
  const counts = records.reduce((summary, paper) => {
    summary[paper.status] = (summary[paper.status] || 0) + 1
    return summary
  }, {})
  const summary = root.querySelector('[data-library-summary]')
  summary.textContent = libraryAvailable
    ? `${records.length} sources · ${counts.reading || 0} reading · ${counts.finished || 0} finished · saved in ${root.dataset.libraryRoot || 'the workspace paper library'}`
    : 'Start the full Workbench to save papers and research history in workspace folders.'
  root.querySelector('[data-paper-library-list]').innerHTML = filtered.map((record) => {
    const selected = selectedPaperIds.has(record.id)
    const pageLabel = record.page_count
      ? record.last_page
        ? `Page ${record.last_page} of ${record.page_count}`
        : `${record.page_count} pages`
      : record.source_type === 'project' ? 'Project report' : 'Source saved'
    return `
      <article class="paper-library-card ${record.id === activePaperId ? 'active' : ''}" data-library-paper="${escapeHtml(record.id)}">
        <button type="button" data-paper-select="${escapeHtml(record.id)}">
          <span class="paper-status ${escapeHtml(record.status)}">${escapeHtml(record.status)}</span>
          <strong>${escapeHtml(record.title)}</strong>
          <small>${escapeHtml(pageLabel)} · ${record.annotation_count || 0} underlines · ${record.question_count || 0} questions</small>
        </button>
        <label><input type="checkbox" data-compare-paper="${escapeHtml(record.id)}" ${selected ? 'checked' : ''} /> Include in Codex questions</label>
      </article>
    `
  }).join('') || '<p class="annotation-empty">No papers in this reading state.</p>'
}

async function loadPaperState(paperId) {
  if (!libraryAvailable) {
    annotations = readStorage(storageKeys.legacyAnnotations, []).filter((item) => item.paperId === paperId)
    questions = []
    return
  }
  const payload = await apiRequest(`/api/workbench/paper-investigation/papers/${encodeURIComponent(paperId)}`)
  paperRecords[paperId] = payload.paper
  annotations = payload.annotations || []
  questions = payload.questions || []
}

async function activatePaper(paperId) {
  if (!paperRecords[paperId] && !papers[paperId]) return
  activePaperId = paperId
  selectedPaperIds.add(paperId)
  localStorage.setItem(storageKeys.paper, paperId)
  writeStorage(storageKeys.selectedPapers, [...selectedPaperIds])
  await loadPaperState(paperId)
  renderLibrary()
  renderPaper()
}

async function loadLibrary() {
  try {
    const payload = await apiRequest('/api/workbench/paper-investigation/papers')
    paperRecords = Object.fromEntries(payload.papers.map((paper) => [paper.id, paper]))
    root.dataset.libraryRoot = payload.library_root
    libraryAvailable = true
    if (!paperRecords[activePaperId]) activePaperId = paperRecords.avo ? 'avo' : payload.papers[0]?.id
  } catch {
    paperRecords = Object.fromEntries(Object.entries(papers).map(([id, paper]) => [id, {
      id,
      title: paper.title,
      authors: paper.authors,
      source_url: paper.sourceUrl,
      pdf_url: id === 'avo' ? paper.sourceUrl : '',
      status: 'reading',
      page_count: id === 'avo' ? 12 : 0,
      annotation_count: 0,
      question_count: 0,
    }]))
    libraryAvailable = false
  }
  comparisonSelection()
  renderLibrary()
}

function dossierCard(section) {
  const paragraphs = (section.paragraphs || [])
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join('')
  const bullets = section.bullets?.length
    ? `<ul>${section.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join('')}</ul>`
    : ''
  return `
    <article class="dossier-card ${escapeHtml(section.tone)}" data-annotatable data-section-label="${escapeHtml(section.title)}">
      <header>
        <span>${escapeHtml(section.label)}</span>
        <small>${escapeHtml(section.locator)}</small>
      </header>
      <h3>${escapeHtml(section.title)}</h3>
      ${paragraphs}${bullets}
    </article>
  `
}

function impactCard(item) {
  return `
    <article class="impact-card ${escapeHtml(item.status)}" data-annotatable data-section-label="${escapeHtml(item.title)}">
      <span>${escapeHtml(item.status)}</span>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.body)}</p>
    </article>
  `
}

function renderPaper() {
  if (!root) return
  const paper = paperDetails(activePaperId)
  localStorage.setItem(storageKeys.paper, activePaperId)

  root.querySelectorAll('[data-paper-select]').forEach((button) => {
    const active = button.dataset.paperSelect === activePaperId
    button.classList.toggle('active', active)
    button.setAttribute('aria-pressed', String(active))
  })
  root.querySelector('[data-paper-type]').textContent = paper.type
  root.querySelector('[data-paper-title]').textContent = paper.title
  root.querySelector('[data-paper-authors]').textContent = paper.authors
  root.querySelector('[data-paper-source]').href = paper.sourceUrl
  root.querySelector('[data-paper-verdict]').textContent = paper.verdict
  root.querySelector('[data-paper-verdict-detail]').textContent = paper.verdictDetail
  root.querySelector('[data-reading-status]').value = paper.status
  const sourceLink = root.querySelector('[data-paper-source]')
  sourceLink.href = paper.sourceUrl || paper.pdfUrl || '#'
  sourceLink.hidden = !paper.sourceUrl && !paper.pdfUrl

  const hasPdf = Boolean(paper.pdfUrl)
  root.querySelector('[data-pdf-reader]').hidden = !hasPdf
  root.querySelector('[data-vista-source]').hidden = hasPdf
  root.querySelector('[data-source-loading]').hidden = !hasPdf || (renderedPdfPaperId === activePaperId && Boolean(root.querySelector('[data-pdf-reader]').childElementCount))
  if (hasPdf) {
    renderPaperPdf(paper)
  } else {
    const source = root.querySelector('[data-vista-source]')
    source.querySelector('strong').textContent = `${paper.label} does not have a saved PDF.`
    source.querySelector('p').textContent = paper.sourceUrl
      ? 'Open the saved source page, or import a PDF later. Your dossier, comments, and questions remain attached to this source.'
      : 'Upload a PDF to make this source selectable page by page.'
    const link = source.querySelector('a')
    link.href = paper.sourceUrl || '#'
    link.textContent = 'Open the saved source'
    link.hidden = !paper.sourceUrl
  }

  clearSelectedPassage()
  renderChat()
  renderAnnotations()
  restoreVisibleUnderlines()
}

function availablePdfWidth(container) {
  const containerStyle = getComputedStyle(container)
  const horizontalPadding = parseFloat(containerStyle.paddingLeft) + parseFloat(containerStyle.paddingRight)
  return Math.max(280, container.clientWidth - horizontalPadding - 6)
}

function fitRenderedPdfPages() {
  const container = root.querySelector('[data-pdf-reader]')
  const availableWidth = availablePdfWidth(container)
  container.querySelectorAll('.pdf-page').forEach((page) => {
    const renderedWidth = Number(page.dataset.renderWidth)
    if (!renderedWidth) return
    const displayScale = Math.min(1, availableWidth / renderedWidth)
    page.dataset.displayScale = String(displayScale)
    page.style.zoom = String(displayScale)
  })
  restorePdfUnderlines()
}

async function renderPaperPdf(paper) {
  const container = root.querySelector('[data-pdf-reader]')
  if (renderedPdfPaperId === paper.id && container.childElementCount) return
  if (pdfPromise && renderedPdfPaperId === paper.id) return pdfPromise
  const renderToken = ++pdfRenderToken
  renderedPdfPaperId = paper.id
  pdfPromise = null
  container.replaceChildren()
  container.hidden = false
  pdfPromise = (async () => {
    try {
      const pdf = await pdfjsLib.getDocument({ url: paper.pdfUrl }).promise
      if (renderedPdfPaperId !== paper.id || renderToken !== pdfRenderToken) return
      container.setAttribute('aria-label', `${paper.title}, ${pdf.numPages} pages`)
      const firstPage = await pdf.getPage(1)
      const availableWidth = availablePdfWidth(container)
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = pageNumber === 1 ? firstPage : await pdf.getPage(pageNumber)
        const viewport = page.getViewport({ scale: 1.3 })
        const wrapper = document.createElement('article')
        wrapper.className = 'pdf-page'
        wrapper.dataset.pageNumber = String(pageNumber)
        wrapper.style.width = `${viewport.width}px`
        wrapper.style.height = `${viewport.height}px`
        wrapper.style.setProperty('--scale-factor', viewport.scale)
        wrapper.dataset.renderWidth = String(viewport.width)
        wrapper.dataset.displayScale = String(Math.min(1, availableWidth / viewport.width))
        wrapper.style.zoom = wrapper.dataset.displayScale
        wrapper.setAttribute('aria-label', `Page ${pageNumber}`)

        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d', { alpha: false })
        const ratio = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        canvas.style.width = `${viewport.width}px`
        canvas.style.height = `${viewport.height}px`
        wrapper.appendChild(canvas)
        if (renderedPdfPaperId !== paper.id || renderToken !== pdfRenderToken) return
        container.appendChild(wrapper)

        await page.render({
          canvasContext: context,
          viewport,
          transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
        }).promise

        const textLayer = new TextLayerBuilder({
          pdfPage: page,
          onAppend: (layer) => wrapper.appendChild(layer),
        })
        await textLayer.render({ viewport })
      }
      root.querySelector('[data-source-loading]').hidden = true
      restorePdfUnderlines()
    } catch (error) {
      if (renderedPdfPaperId !== paper.id) return
      const loading = root.querySelector('[data-source-loading]')
      loading.hidden = false
      loading.querySelector('strong').textContent = 'The in-page PDF could not be loaded'
      loading.querySelector('p').textContent = `Open the arXiv source directly, or retry with an internet connection. ${error.message}`
    }
  })()
  return pdfPromise
}

function installTabs() {
  root.querySelectorAll('[data-reader-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      const selected = button.dataset.readerTab
      root.querySelectorAll('[data-reader-tab]').forEach((tab) => {
        tab.classList.toggle('active', tab === button)
      })
      root.querySelectorAll('[data-reader-panel]').forEach((panel) => {
        const active = panel.dataset.readerPanel === selected
        panel.classList.toggle('active', active)
        panel.hidden = !active
      })
      window.setTimeout(restoreVisibleUnderlines, 0)
    })
  })
}

function captureSelection() {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  const source = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
    ? range.commonAncestorContainer
    : range.commonAncestorContainer.parentElement
  const surface = source?.closest('.pdf-page, .dossier-card, .impact-card')
  if (!surface || !root.contains(surface)) return
  const quote = selection.toString().replace(/\s+/g, ' ').trim()
  if (quote.length < 3) return

  selectedRange = range.cloneRange()
  selectedPassage = {
    quote: quote.slice(0, 5000),
    page: surface.dataset.pageNumber ? Number(surface.dataset.pageNumber) : null,
    section: surface.dataset.sectionLabel || (surface.matches('.pdf-page') ? `${paperDetails(activePaperId).label} page ${surface.dataset.pageNumber}` : 'Investigation note'),
    view: surface.matches('.pdf-page') ? 'source' : surface.matches('.impact-card') ? 'impact' : 'dossier',
  }
  renderSelectedPassage()
  showSelectionToolbar(range)
}

function hideSelectionToolbar() {
  root.querySelector('[data-selection-toolbar]').hidden = true
}

function showSelectionToolbar(range) {
  const toolbar = root.querySelector('[data-selection-toolbar]')
  const rect = [...range.getClientRects()].filter((item) => item.width > 1 && item.height > 1).at(-1)
  if (!rect) return
  toolbar.hidden = false
  const toolbarRect = toolbar.getBoundingClientRect()
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - toolbarRect.width - 12)
  const above = rect.top - toolbarRect.height - 9
  const top = above >= 12 ? above : Math.min(window.innerHeight - toolbarRect.height - 12, rect.bottom + 9)
  toolbar.style.left = `${left}px`
  toolbar.style.top = `${top}px`
}

function renderUnderlineGuide() {
  const hasSelection = Boolean(selectedPassage)
  const hasLinkedUnderline = selectedAnnotationIds.size > 0
  root.querySelectorAll('[data-underline-step]').forEach((step) => {
    const name = step.dataset.underlineStep
    const complete = (name === 'select' && (hasSelection || hasLinkedUnderline))
      || (name === 'save' && hasLinkedUnderline)
    const current = (name === 'select' && !hasSelection && !hasLinkedUnderline)
      || (name === 'save' && hasSelection && !hasLinkedUnderline)
      || (name === 'ask' && hasLinkedUnderline)
    step.classList.toggle('complete', complete)
    step.classList.toggle('current', current)
  })
}

function renderSelectedPassage() {
  const box = root.querySelector('[data-selected-passage]')
  const paragraph = box.querySelector('p')
  const save = box.querySelector('[data-save-annotation]')
  const clear = box.querySelector('[data-clear-selection]')
  if (!selectedPassage) {
    paragraph.textContent = 'Drag across text in the paper. A button will appear beside your selection.'
    save.hidden = true
    clear.hidden = true
    box.classList.remove('has-selection')
    renderUnderlineGuide()
    return
  }
  paragraph.textContent = selectedPassage.quote
  save.hidden = false
  clear.hidden = false
  box.classList.add('has-selection')
  renderUnderlineGuide()
}

function clearSelectedPassage() {
  selectedPassage = null
  selectedRange = null
  window.getSelection()?.removeAllRanges()
  hideSelectionToolbar()
  renderSelectedPassage()
}

function textOffsetWithin(element, container, offset) {
  const range = document.createRange()
  range.selectNodeContents(element)
  try {
    range.setEnd(container, offset)
    return range.toString().length
  } catch {
    return null
  }
}

function textPointAt(element, offset) {
  if (!element) return null
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
  let remaining = offset
  let node = walker.nextNode()
  let lastNode = null
  while (node) {
    lastNode = node
    if (remaining <= node.textContent.length) return { node, offset: remaining }
    remaining -= node.textContent.length
    node = walker.nextNode()
  }
  return lastNode ? { node: lastNode, offset: lastNode.textContent.length } : null
}

function pdfAnchorForRange(range, page) {
  const spans = [...page.querySelectorAll('.textLayer span')]
  const startElement = range.startContainer.nodeType === Node.ELEMENT_NODE
    ? range.startContainer
    : range.startContainer.parentElement
  const endElement = range.endContainer.nodeType === Node.ELEMENT_NODE
    ? range.endContainer
    : range.endContainer.parentElement
  const startSpan = startElement?.closest('.textLayer span')
  const endSpan = endElement?.closest('.textLayer span')
  const startSpanIndex = spans.indexOf(startSpan)
  const endSpanIndex = spans.indexOf(endSpan)
  if (startSpanIndex < 0 || endSpanIndex < 0) return null
  const startOffset = textOffsetWithin(startSpan, range.startContainer, range.startOffset)
  const endOffset = textOffsetWithin(endSpan, range.endContainer, range.endOffset)
  if (startOffset === null || endOffset === null) return null
  return { startSpan: startSpanIndex, startOffset, endSpan: endSpanIndex, endOffset }
}

function rangeFromPdfAnchor(page, anchor) {
  if (!anchor) return null
  const spans = [...page.querySelectorAll('.textLayer span')]
  const start = textPointAt(spans[anchor.startSpan], anchor.startOffset)
  const end = textPointAt(spans[anchor.endSpan], anchor.endOffset)
  if (!start || !end) return null
  const range = document.createRange()
  range.setStart(start.node, start.offset)
  range.setEnd(end.node, end.offset)
  return range
}

function drawPdfUnderline(page, range, annotationId) {
  const pageRect = page.getBoundingClientRect()
  const displayScale = Number(page.dataset.displayScale) || 1
  const rects = [...range.getClientRects()]
    .filter((rect) => rect.width > 1 && rect.height > 1)
    .map((rect) => ({
      left: (rect.left - pageRect.left) / displayScale,
      right: (rect.right - pageRect.left) / displayScale,
      bottom: (rect.bottom - pageRect.top) / displayScale,
    }))

  const lines = []
  rects.forEach((rect) => {
    const previous = lines.at(-1)
    if (previous && Math.abs(previous.bottom - rect.bottom) < 2 && rect.left - previous.right < 5) {
      previous.right = Math.max(previous.right, rect.right)
      return
    }
    lines.push({ ...rect })
  })

  lines.forEach((line) => {
    const underline = document.createElement('span')
    underline.className = 'pdf-underline-segment'
    underline.classList.toggle('linked', selectedAnnotationIds.has(annotationId))
    underline.dataset.pdfUnderline = annotationId
    underline.setAttribute('role', 'button')
    underline.setAttribute('tabindex', '0')
    underline.setAttribute('aria-label', 'Link or unlink this underline from the next Codex question')
    underline.title = 'Click to link or unlink this underline from the next Codex question'
    underline.style.left = `${line.left}px`
    underline.style.top = `${line.bottom - 2}px`
    underline.style.width = `${line.right - line.left}px`
    page.appendChild(underline)
  })
}

function applyCurrentUnderline() {
  if (!selectedRange) return
  const base = selectedRange.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
    ? selectedRange.commonAncestorContainer
    : selectedRange.commonAncestorContainer.parentElement
  const page = base?.closest('.pdf-page')
  if (page) {
    return pdfAnchorForRange(selectedRange, page)
  }
  const block = base?.closest('p, li, h3')
  if (block) block.classList.add('paper-underline')
  return null
}

async function saveCurrentAnnotation() {
  if (!selectedPassage) return
  const id = globalThis.crypto?.randomUUID?.() || `annotation-${Date.now()}`
  const anchor = applyCurrentUnderline()
  const annotation = {
    id,
    paper_id: activePaperId,
    paperId: activePaperId,
    ...selectedPassage,
    ...(anchor ? { anchor } : {}),
    comment: '',
    created_at: new Date().toISOString(),
  }
  annotations.unshift(annotation)
  selectedAnnotationIds.add(id)
  renderAnnotations()
  clearSelectedPassage()
  restoreVisibleUnderlines()
  root.querySelector('[data-copilot-message]').textContent = 'Underline saved and attached. Ask your question below.'
  if (!libraryAvailable) {
    const legacy = readStorage(storageKeys.legacyAnnotations, [])
    writeStorage(storageKeys.legacyAnnotations, [annotation, ...legacy.filter((item) => item.id !== id)])
    return
  }
  try {
    const payload = await apiRequest(
      `/api/workbench/paper-investigation/papers/${encodeURIComponent(activePaperId)}/annotations`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(annotation),
      },
    )
    annotations = annotations.map((item) => item.id === id ? payload.annotation : item)
    paperRecords[activePaperId].annotation_count = annotations.length
    renderLibrary()
    renderAnnotations()
  } catch (error) {
    root.querySelector('[data-copilot-message]').textContent = `Underline is visible but could not be saved: ${error.message}`
  }
}

function annotationCard(annotation) {
  const location = annotation.page ? `Page ${annotation.page}` : annotation.section
  const linkedQuestions = questions.filter((question) => question.annotation_ids?.includes(annotation.id)).length
  return `
    <article class="annotation-card" data-annotation-id="${escapeHtml(annotation.id)}">
      <header>
        <span>${escapeHtml(paperDetails(activePaperId).label)} · ${escapeHtml(location)}</span>
        <button type="button" data-delete-annotation aria-label="Delete underline">Delete</button>
      </header>
      <blockquote>${escapeHtml(annotation.quote)}</blockquote>
      <label>
        Your comment
        <textarea rows="2" data-annotation-comment placeholder="Why does this matter? What did it change?">${escapeHtml(annotation.comment || annotation.note || '')}</textarea>
      </label>
      <div class="annotation-card-actions">
        <label><input type="checkbox" data-link-annotation ${selectedAnnotationIds.has(annotation.id) ? 'checked' : ''} /> Link to next question</label>
        <button type="button" data-ask-annotation>Ask Codex about this</button>
      </div>
      ${linkedQuestions ? `<small>${linkedQuestions} linked Codex question${linkedQuestions === 1 ? '' : 's'}</small>` : ''}
    </article>
  `
}

function renderAnnotations() {
  const visible = annotations.filter((annotation) => (annotation.paper_id || annotation.paperId) === activePaperId)
  root.querySelector('[data-annotation-count]').textContent = `${visible.length} saved`
  root.querySelector('[data-annotation-empty]').hidden = visible.length > 0
  root.querySelector('[data-annotation-list]').innerHTML = visible.map(annotationCard).join('')
  renderLinkedUnderlines()
}

function renderLinkedUnderlines() {
  const box = root.querySelector('[data-linked-underlines]')
  const linked = annotations.filter((annotation) => selectedAnnotationIds.has(annotation.id))
  if (linked.length === 0) {
    box.innerHTML = '<span>Linked to next question</span><p>No passage attached yet. Drag over text and choose “Underline + attach.” For an old mark: gold means saved; click it and it turns teal when attached.</p>'
    root.querySelectorAll('[data-pdf-underline]').forEach((segment) => segment.classList.remove('linked'))
    renderUnderlineGuide()
    return
  }
  box.innerHTML = `
    <span>${linked.length} underline${linked.length === 1 ? '' : 's'} linked to the next question</span>
    <div>${linked.map((annotation) => `<button type="button" data-unlink-annotation="${escapeHtml(annotation.id)}" title="Remove link">${escapeHtml(annotation.quote.slice(0, 90))} ×</button>`).join('')}</div>
    <p>Teal marks in the paper are attached. Ask Codex below, or select more passages first.</p>
  `
  root.querySelectorAll('[data-pdf-underline]').forEach((segment) => {
    segment.classList.toggle('linked', selectedAnnotationIds.has(segment.dataset.pdfUnderline))
  })
  renderUnderlineGuide()
}

function toggleAnnotationLink(annotationId) {
  if (!annotations.some((annotation) => annotation.id === annotationId)) return
  if (selectedAnnotationIds.has(annotationId)) selectedAnnotationIds.delete(annotationId)
  else selectedAnnotationIds.add(annotationId)
  renderAnnotations()

  const count = selectedAnnotationIds.size
  root.querySelector('[data-copilot-message]').textContent = count
    ? `${count} underline${count === 1 ? '' : 's'} linked to the next Codex question.`
    : 'No underlines linked to the next Codex question.'
}

function normalizeText(value) {
  return String(value).replace(/\s+/g, ' ').trim().toLowerCase()
}

function rangeForQuote(elements, quote) {
  const mappedCharacters = []
  let previousEnd = null

  elements.forEach((element) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
    const nodes = []
    let node = walker.nextNode()
    while (node) {
      nodes.push(node)
      node = walker.nextNode()
    }
    if (nodes.length === 0) return

    if (previousEnd && mappedCharacters.at(-1)?.character !== ' ') {
      mappedCharacters.push({
        character: ' ',
        start: previousEnd,
        end: { node: nodes[0], offset: 0 },
      })
    }

    nodes.forEach((textNode) => {
      for (let offset = 0; offset < textNode.textContent.length; offset += 1) {
        const character = textNode.textContent[offset]
        const start = { node: textNode, offset }
        const end = { node: textNode, offset: offset + 1 }
        if (/\s/.test(character)) {
          if (mappedCharacters.length > 0 && mappedCharacters.at(-1).character !== ' ') {
            mappedCharacters.push({ character: ' ', start, end })
          }
        } else {
          mappedCharacters.push({ character: character.toLowerCase(), start, end })
        }
        previousEnd = end
      }
    })
  })

  const needle = normalizeText(quote)
  const startIndex = mappedCharacters.map((item) => item.character).join('').indexOf(needle)
  if (!needle || startIndex < 0) return null
  const first = mappedCharacters[startIndex]
  const last = mappedCharacters[startIndex + needle.length - 1]
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.start.node, first.start.offset)
  range.setEnd(last.end.node, last.end.offset)
  return range
}

function restorePdfUnderlines() {
  root.querySelectorAll('[data-pdf-underline]').forEach((underline) => underline.remove())
  annotations
    .filter((annotation) => (annotation.paper_id || annotation.paperId) === activePaperId && annotation.page)
    .forEach((annotation) => {
      const page = root.querySelector(`.pdf-page[data-page-number="${annotation.page}"]`)
      if (!page) return
      const anchoredRange = rangeFromPdfAnchor(page, annotation.anchor)
      if (anchoredRange) {
        drawPdfUnderline(page, anchoredRange, annotation.id)
        return
      }
      const spans = [...(page?.querySelectorAll('.textLayer span') || [])]
      const quoteRange = rangeForQuote(spans, annotation.quote)
      if (quoteRange) drawPdfUnderline(page, quoteRange, annotation.id)
    })
}

function restoreSummaryUnderlines() {
  root.querySelectorAll('.dossier-card .paper-underline, .impact-card.paper-underline, .impact-card .paper-underline')
    .forEach((element) => element.classList.remove('paper-underline'))
  annotations
    .filter((annotation) => (annotation.paper_id || annotation.paperId) === activePaperId && !annotation.page)
    .forEach((annotation) => {
      const blocks = root.querySelectorAll('.dossier-card p, .dossier-card li, .impact-card p, .impact-card h3')
      const needle = normalizeText(annotation.quote)
      const match = [...blocks].find((block) => normalizeText(block.textContent).includes(needle))
      match?.classList.add('paper-underline')
    })
}

function restoreVisibleUnderlines() {
  restorePdfUnderlines()
  restoreSummaryUnderlines()
}

function chatForActivePaper() {
  return questions
    .slice()
    .reverse()
    .flatMap((question) => [
      { role: 'user', content: question.question },
      { role: 'assistant', content: question.answer },
    ])
    .slice(-16)
}

function renderResearchMarkdown(content) {
  const math = []
  const preserveMath = (source, displayMode) => {
    const placeholder = `CODEXMATHPLACEHOLDER${math.length}END`
    math.push({ placeholder, source: source.trim(), displayMode })
    return placeholder
  }
  const markdown = String(content || '')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, source) => preserveMath(source, true))
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, source) => preserveMath(source, false))

  let html = DOMPurify.sanitize(marked.parse(markdown, { gfm: true, breaks: true }))
  math.forEach(({ placeholder, source, displayMode }) => {
    const rendered = katex.renderToString(source, {
      displayMode,
      throwOnError: false,
      trust: false,
      strict: 'ignore',
    })
    const className = displayMode ? 'copilot-math copilot-math-block' : 'copilot-math'
    html = html.replaceAll(placeholder, `<span class="${className}">${rendered}</span>`)
  })
  return DOMPurify.sanitize(html)
}

function renderMessageBody(message) {
  if (message.role === 'assistant') {
    return `<div class="copilot-message-body">${renderResearchMarkdown(message.content)}</div>`
  }
  return `<p>${escapeHtml(message.content)}</p>`
}

function renderChat() {
  const thread = root.querySelector('[data-copilot-thread]')
  const messages = chatForActivePaper()
  const paper = paperDetails(activePaperId)
  const intro = `
    <article class="copilot-message assistant">
      <span class="copilot-message-label">Investigation brief</span>
      <p>I know the saved source context for ${escapeHtml(paper.label)}. Link underlines or select several papers; I will keep the claim, evidence, missing control, and thesis consequence separate.</p>
    </article>
  `
  thread.innerHTML = intro + messages.map((message) => `
    <article class="copilot-message ${message.role === 'user' ? 'user' : 'assistant'}">
      <span class="copilot-message-label">${message.role === 'user' ? 'You' : 'Codex'}</span>
      ${renderMessageBody(message)}
    </article>
  `).join('')
  thread.scrollTop = thread.scrollHeight
}

function appendTemporaryMessage(role, content) {
  const thread = root.querySelector('[data-copilot-thread]')
  thread.insertAdjacentHTML('beforeend', `
    <article class="copilot-message ${role === 'user' ? 'user' : 'assistant'}">
      <span class="copilot-message-label">${role === 'user' ? 'You' : 'Codex'}</span>
      ${renderMessageBody({ role, content })}
    </article>
  `)
  thread.scrollTop = thread.scrollHeight
}

async function checkCodexStatus() {
  const status = root.querySelector('[data-copilot-status]')
  try {
    const response = await fetch('/api/workbench/codex/status', { cache: 'no-store' })
    const payload = await response.json()
    const ready = response.ok && payload.available && payload.logged_in
    status.textContent = ready ? 'Codex ready' : 'Codex unavailable'
    status.dataset.state = ready ? 'ready' : 'blocked'
  } catch {
    status.textContent = 'Start Workbench to ask'
    status.dataset.state = 'blocked'
  }
}

async function askCodex(question) {
  const button = root.querySelector('[data-ask-codex]')
  const message = root.querySelector('[data-copilot-message]')
  const priorHistory = chatForActivePaper().slice(-8)
  const paperIds = comparisonSelection()
  const annotationIds = [...selectedAnnotationIds]
  appendTemporaryMessage('user', question)
  button.disabled = true
  button.textContent = 'Thinking…'
  message.textContent = `Auditing ${paperIds.length} source${paperIds.length === 1 ? '' : 's'} and ${annotationIds.length} linked underline${annotationIds.length === 1 ? '' : 's'}…`
  try {
    const response = await fetch('/api/workbench/paper-investigation/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        paper_ids: paperIds,
        annotation_ids: annotationIds,
        question,
        selected_passage: selectedPassage?.quote || '',
        history: priorHistory,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`)
    questions.unshift({
      id: payload.question_id,
      question,
      answer: payload.answer,
      paper_ids: paperIds,
      annotation_ids: annotationIds,
      selected_passage: selectedPassage?.quote || '',
      created_at: new Date().toISOString(),
    })
    selectedAnnotationIds.clear()
    paperRecords[activePaperId].question_count = questions.length
    renderChat()
    renderAnnotations()
    renderLibrary()
    message.textContent = 'Answer and evidence links saved in each selected paper folder.'
  } catch (error) {
    appendTemporaryMessage('assistant', `I could not reach the local research copilot: ${error.message}`)
    message.textContent = 'Start the full Workbench, then try again.'
  } finally {
    button.disabled = false
    button.textContent = 'Ask Codex'
  }
}

async function migrateLegacyAnnotations() {
  if (!libraryAvailable) return
  const legacy = readStorage(storageKeys.legacyAnnotations, [])
  if (!legacy.length) return
  let migrated = true
  for (const annotation of legacy) {
    const paperId = annotation.paper_id || annotation.paperId
    if (!paperRecords[paperId]) continue
    try {
      await apiRequest(
        `/api/workbench/paper-investigation/papers/${encodeURIComponent(paperId)}/annotations`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...annotation,
            comment: annotation.comment || annotation.note || '',
            created_at: annotation.created_at || annotation.createdAt,
          }),
        },
      )
    } catch {
      migrated = false
    }
  }
  if (migrated) localStorage.removeItem(storageKeys.legacyAnnotations)
}

async function migrateLegacyChats() {
  if (!libraryAvailable) return
  const legacyChats = readStorage(storageKeys.legacyChats, {})
  let migrated = true
  for (const [paperId, turns] of Object.entries(legacyChats)) {
    if (!paperRecords[paperId] || !Array.isArray(turns)) continue
    for (let index = 0; index < turns.length; index += 1) {
      const user = turns[index]
      const assistant = turns[index + 1]
      if (user?.role !== 'user' || assistant?.role !== 'assistant') continue
      try {
        await apiRequest(
          `/api/workbench/paper-investigation/papers/${encodeURIComponent(paperId)}/questions`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              id: `legacy-${paperId}-${index}`,
              question: user.content,
              answer: assistant.content,
              annotation_ids: [],
            }),
          },
        )
        index += 1
      } catch {
        migrated = false
      }
    }
  }
  if (migrated) localStorage.removeItem(storageKeys.legacyChats)
}

async function importPaper(event) {
  event.preventDefault()
  const dialog = root.ownerDocument.querySelector('[data-paper-import-dialog]')
  const button = dialog.querySelector('[data-import-paper]')
  const message = dialog.querySelector('[data-paper-import-message]')
  const url = dialog.querySelector('[data-paper-url]').value.trim()
  const file = dialog.querySelector('[data-paper-file]').files[0]
  const title = dialog.querySelector('[data-import-title]').value.trim()
  const authors = dialog.querySelector('[data-import-authors]').value.trim()
  if (!file && !url) {
    message.textContent = 'Paste an arXiv/PDF link or choose a PDF file.'
    return
  }
  button.disabled = true
  button.textContent = 'Saving…'
  message.textContent = 'Downloading, extracting selectable text, and creating the paper folder…'
  try {
    let payload
    if (file) {
      const query = new URLSearchParams({ filename: file.name, title, authors })
      payload = await apiRequest(`/api/workbench/paper-investigation/papers/upload?${query}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/pdf' },
        body: file,
      })
    } else {
      payload = await apiRequest('/api/workbench/paper-investigation/papers/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, title, authors }),
      })
    }
    paperRecords[payload.paper.id] = payload.paper
    libraryFilter = 'all'
    dialog.querySelector('form').reset()
    dialog.close()
    await activatePaper(payload.paper.id)
  } catch (error) {
    message.textContent = error.message
  } finally {
    button.disabled = false
    button.textContent = 'Save paper'
  }
}

async function saveAnnotationComment(annotation, comment) {
  annotation.comment = comment
  if (!libraryAvailable) return
  try {
    await apiRequest(
      `/api/workbench/paper-investigation/papers/${encodeURIComponent(activePaperId)}/annotations/${encodeURIComponent(annotation.id)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment }),
      },
    )
  } catch (error) {
    root.querySelector('[data-copilot-message]').textContent = `Comment could not be saved: ${error.message}`
  }
}

function scheduleReadingProgress() {
  if (!libraryAvailable || !paperRecords[activePaperId]?.has_pdf) return
  const reader = root.querySelector('[data-pdf-reader]')
  const readerTop = reader.getBoundingClientRect().top
  const visiblePage = [...reader.querySelectorAll('.pdf-page')]
    .map((page) => ({ page, distance: Math.abs(page.getBoundingClientRect().top - readerTop - 12) }))
    .sort((left, right) => left.distance - right.distance)[0]?.page
  const pageNumber = Number(visiblePage?.dataset.pageNumber || 0)
  if (!pageNumber || pageNumber === paperRecords[activePaperId].last_page) return
  const paperId = activePaperId
  if (progressSaveTimer) window.clearTimeout(progressSaveTimer)
  progressSaveTimer = window.setTimeout(async () => {
    try {
      const payload = await apiRequest(
        `/api/workbench/paper-investigation/papers/${encodeURIComponent(paperId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ last_page: pageNumber }),
        },
      )
      paperRecords[paperId] = payload.paper
      renderLibrary()
    } catch {
      // Reading progress is helpful metadata; it should never interrupt reading.
    }
  }, 700)
}

function installInteractions() {
  installTabs()
  root.addEventListener('mouseup', () => window.setTimeout(captureSelection, 0))
  root.addEventListener('keyup', (event) => {
    if (event.key === 'Shift' || event.key.startsWith('Arrow')) window.setTimeout(captureSelection, 0)
  })
  root.querySelectorAll('[data-save-annotation]').forEach((button) => button.addEventListener('click', saveCurrentAnnotation))
  root.querySelector('[data-clear-selection]').addEventListener('click', clearSelectedPassage)
  const pdfReader = root.querySelector('[data-pdf-reader]')
  pdfReader.addEventListener('scroll', () => {
    hideSelectionToolbar()
    scheduleReadingProgress()
  }, { passive: true })
  pdfReader.addEventListener('click', (event) => {
    const underline = event.target.closest('[data-pdf-underline]')
    if (underline) toggleAnnotationLink(underline.dataset.pdfUnderline)
  })
  pdfReader.addEventListener('keydown', (event) => {
    if ((event.key !== 'Enter' && event.key !== ' ') || !event.target.matches('[data-pdf-underline]')) return
    event.preventDefault()
    toggleAnnotationLink(event.target.dataset.pdfUnderline)
  })
  if ('ResizeObserver' in window) {
    const resizeObserver = new ResizeObserver(([entry]) => {
      if (!entry.contentRect.width) return
      if (pdfResizeTimer) window.clearTimeout(pdfResizeTimer)
      pdfResizeTimer = window.setTimeout(fitRenderedPdfPages, 180)
    })
    resizeObserver.observe(root.querySelector('.paper-reader'))
  }
  window.addEventListener('scroll', hideSelectionToolbar, { passive: true, capture: true })
  window.addEventListener('resize', hideSelectionToolbar, { passive: true })

  const library = root.querySelector('[data-paper-library]')
  root.querySelector('[data-toggle-library]').addEventListener('click', () => {
    library.hidden = !library.hidden
  })
  root.querySelector('[data-open-paper-import]').addEventListener('click', () => {
    root.ownerDocument.querySelector('[data-paper-import-dialog]').showModal()
  })
  const importDialog = root.ownerDocument.querySelector('[data-paper-import-dialog]')
  importDialog.querySelector('[data-close-paper-import]').addEventListener('click', () => importDialog.close())
  importDialog.querySelector('[data-paper-import-form]').addEventListener('submit', importPaper)

  root.querySelector('[data-paper-library-list]').addEventListener('click', (event) => {
    const button = event.target.closest('[data-paper-select]')
    if (button) activatePaper(button.dataset.paperSelect)
  })
  root.querySelector('[data-paper-library-list]').addEventListener('change', (event) => {
    if (!event.target.matches('[data-compare-paper]')) return
    const paperId = event.target.dataset.comparePaper
    if (event.target.checked) selectedPaperIds.add(paperId)
    else if (paperId !== activePaperId) selectedPaperIds.delete(paperId)
    else event.target.checked = true
    writeStorage(storageKeys.selectedPapers, [...selectedPaperIds])
  })

  root.querySelectorAll('[data-paper-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      libraryFilter = button.dataset.paperFilter
      root.querySelectorAll('[data-paper-filter]').forEach((filter) => filter.classList.toggle('active', filter === button))
      renderLibrary()
    })
  })

  root.querySelector('[data-reading-status]').addEventListener('change', async (event) => {
    if (!libraryAvailable) return
    try {
      const payload = await apiRequest(
        `/api/workbench/paper-investigation/papers/${encodeURIComponent(activePaperId)}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: event.target.value }),
        },
      )
      paperRecords[activePaperId] = payload.paper
      renderLibrary()
    } catch (error) {
      root.querySelector('[data-copilot-message]').textContent = `Reading status could not be saved: ${error.message}`
    }
  })

  root.querySelectorAll('[data-question-preset]').forEach((button) => {
    button.addEventListener('click', () => {
      const textarea = root.querySelector('[data-paper-question]')
      textarea.value = button.dataset.questionPreset
      textarea.focus()
    })
  })

  root.querySelector('[data-annotation-list]').addEventListener('input', (event) => {
    if (!event.target.matches('[data-annotation-comment]')) return
    const card = event.target.closest('[data-annotation-id]')
    const annotation = annotations.find((item) => item.id === card.dataset.annotationId)
    if (!annotation) return
    const existing = commentSaveTimers.get(annotation.id)
    if (existing) window.clearTimeout(existing)
    commentSaveTimers.set(annotation.id, window.setTimeout(() => {
      commentSaveTimers.delete(annotation.id)
      saveAnnotationComment(annotation, event.target.value)
    }, 450))
  })
  root.querySelector('[data-annotation-list]').addEventListener('change', (event) => {
    if (!event.target.matches('[data-link-annotation]')) return
    const card = event.target.closest('[data-annotation-id]')
    toggleAnnotationLink(card.dataset.annotationId)
  })
  root.querySelector('[data-annotation-list]').addEventListener('click', async (event) => {
    const card = event.target.closest('[data-annotation-id]')
    if (!card) return
    const annotation = annotations.find((item) => item.id === card.dataset.annotationId)
    if (event.target.matches('[data-delete-annotation]')) {
      if (libraryAvailable) {
        try {
          await apiRequest(
            `/api/workbench/paper-investigation/papers/${encodeURIComponent(activePaperId)}/annotations/${encodeURIComponent(card.dataset.annotationId)}`,
            { method: 'DELETE' },
          )
        } catch (error) {
          root.querySelector('[data-copilot-message]').textContent = `Underline could not be deleted: ${error.message}`
          return
        }
      }
      annotations = annotations.filter((item) => item.id !== card.dataset.annotationId)
      selectedAnnotationIds.delete(card.dataset.annotationId)
      if (paperRecords[activePaperId]) paperRecords[activePaperId].annotation_count = annotations.length
      renderAnnotations()
      renderLibrary()
      restoreVisibleUnderlines()
      return
    }
    if (event.target.matches('[data-ask-annotation]') && annotation) {
      selectedAnnotationIds.add(annotation.id)
      selectedPassage = {
        quote: annotation.quote,
        page: annotation.page,
        section: annotation.section,
        view: annotation.view,
      }
      selectedRange = null
      renderSelectedPassage()
      renderAnnotations()
      const textarea = root.querySelector('[data-paper-question]')
      textarea.value = annotation.comment
        ? `Explain this passage and evaluate my comment: ${annotation.comment}`
        : 'Explain this passage and tell me exactly why it matters for my thesis.'
      textarea.focus()
    }
  })

  root.querySelector('[data-linked-underlines]').addEventListener('click', (event) => {
    const button = event.target.closest('[data-unlink-annotation]')
    if (!button) return
    selectedAnnotationIds.delete(button.dataset.unlinkAnnotation)
    renderAnnotations()
  })

  root.querySelector('[data-copilot-form]').addEventListener('submit', (event) => {
    event.preventDefault()
    const textarea = root.querySelector('[data-paper-question]')
    const question = textarea.value.trim()
    if (!question) return
    textarea.value = ''
    askCodex(question)
  })
}

if (root) {
  installInteractions()
  ;(async () => {
    await loadLibrary()
    await migrateLegacyAnnotations()
    await migrateLegacyChats()
    await activatePaper(activePaperId)
    checkCodexStatus()
  })()
}
