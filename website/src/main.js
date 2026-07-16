const primaryNavItems = [
  { href: '/', label: 'Client Agent', match: /^\/$/ },
  { href: '/docs/architecture.html', label: 'Architecture', match: /^\/docs\/architecture\.html$/ },
  { href: '/notes.html', label: 'Notes', match: /^\/notes\.html$/ },
]

const traceNavItems = [
  { href: '/experiments/goal-recognition/', label: 'Goal recognition', match: /^\/experiments\/goal-recognition\/?/ },
  { href: '/experiments/thinking-comparison.html', label: 'Thinking comparison', match: /^\/experiments\/thinking-comparison\.html$/ },
  { href: '/experiments/live-framework.html', label: 'LIVE framework', match: /^\/experiments\/live-framework\.html$/ },
]

const referenceNavItems = [
  { href: '/docs/api.html', label: 'API', match: /^\/docs\/api\.html$/ },
  { href: '/games/', label: 'Games', match: /^\/games\/?/ },
]

function normalizedPath() {
  return window.location.pathname.replace(/\/index\.html$/, '/') || '/'
}

function navLink(item, pathname) {
  const active = item.match.test(pathname) ? ' aria-current="page"' : ''
  return `<a href="${item.href}"${active}>${item.label}</a>`
}

function navGroup(title, items, pathname) {
  const open = items.some((item) => item.match.test(pathname)) ? ' open' : ''
  return `
    <details class="nav-group"${open}>
      <summary>${title}</summary>
      <div class="nav-group-links">
        ${items.map((item) => navLink(item, pathname)).join('')}
      </div>
    </details>
  `
}

const pseudocodeBasePath = '/docs/pseudocode/'
const pseudocodeSavePath = '/__pseudocode/save'
const pseudocodeEditingEnabled = import.meta.env.DEV
const pseudocodeVarNames = new Set([
  'A',
  'H',
  'P',
  'action_selector',
  'active_plan',
  'base_path',
  'c',
  'candidates',
  'cfg',
  'contradicted',
  'dashboard',
  'decision',
  'engine',
  'env',
  'events',
  'frame',
  'game_id',
  'goal',
  'images',
  'inducer',
  'legend',
  'legend_inferer',
  'legend_store',
  'llm',
  'loop',
  'memory',
  'natural_rule_library',
  'outcome',
  'plan',
  'planner',
  'probe_planner',
  'probe',
  'records',
  'response',
  'raw_response',
  'rule_attempt_log',
  'rulebook',
  'rule_learner',
  'rule_planner',
  's',
  'state',
  'task_goal',
  'unexplained',
  'verifier',
])

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => (
    {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]
  ))
}

function renderInline(value) {
  return escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function renderPseudocodeStatement(value) {
  let rendered = escapeHtml(value).replace(/&lt;-/g, '&larr;')
  rendered = rendered.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (word) => (
    pseudocodeVarNames.has(word) ? `<var>${word}</var>` : word
  ))
  return rendered
    .replace(/\b(while|do|if|then|return|for all|else)\b/g, '<strong>$1</strong>')
    .replace(/\b(is empty)\b/g, '$1')
}

function markdownHeading(markdown) {
  return markdown.match(/^#\s+(.+)$/m)?.[1].trim() || 'Pseudocode'
}

function markdownSection(markdown, heading) {
  const lines = markdown.split(/\r?\n/)
  const start = lines.findIndex((line) => line.trim() === `## ${heading}`)
  if (start === -1) return ''

  const section = []
  for (let index = start + 1; index < lines.length; index += 1) {
    if (/^##\s+/.test(lines[index])) break
    section.push(lines[index])
  }
  return section.join('\n').trim()
}

function firstCodeBlock(markdown) {
  return markdown.match(/```[^\n]*\n([\s\S]*?)\n```/)?.[1] || ''
}

function trimCodeLines(code) {
  const lines = code.split(/\r?\n/)
  while (lines.length > 0 && lines[0].trim() === '') lines.shift()
  while (lines.length > 0 && lines[lines.length - 1].trim() === '') lines.pop()
  return lines
}

function splitStatementAndComment(line) {
  const index = line.indexOf(' # ')
  if (index === -1) return { statement: line, comment: '' }
  return {
    statement: line.slice(0, index),
    comment: line.slice(index + 3),
  }
}

function renderPseudocodeLines(code) {
  return trimCodeLines(code).map((line) => {
    const { statement, comment } = splitStatementAndComment(line)
    return `
      <div class="pseudocode-line">
        <span class="pseudocode-stmt">${renderPseudocodeStatement(statement)}</span>
        ${comment ? `<span class="pseudocode-comment">${renderInline(comment)}</span>` : ''}
      </div>
    `
  }).join('')
}

function renderPseudocodeCard(item, markdown) {
  const title = markdownHeading(markdown)
  const cardTitle = markdownSection(markdown, 'Card Title').split(/\n\s*\n/)[0] || '**File role** Pseudocode'
  const code = firstCodeBlock(markdownSection(markdown, 'Pseudocode'))
  const editableClass = pseudocodeEditingEnabled ? ' is-editable' : ''
  const editHint = pseudocodeEditingEnabled ? ' title="Double-click to edit Markdown"' : ''
  return `
    <article class="algorithm-card${item.wide ? ' wide' : ''}${editableClass}" data-pseudocode-file="${escapeHtml(item.file)}"${editHint}>
      <header>
        <h3>${escapeHtml(title)}</h3>
        <span class="path">${escapeHtml(item.path || item.file)}</span>
      </header>
      <div class="pseudocode">
        <div class="pseudocode-title">${renderInline(cardTitle)}</div>
        ${renderPseudocodeLines(code)}
      </div>
    </article>
  `
}

function renderPseudocodeEditor(item, markdown) {
  return `
    <article class="algorithm-card pseudocode-editor-card${item.wide ? ' wide' : ''}" data-pseudocode-file="${escapeHtml(item.file)}" data-pseudocode-editor>
      <header>
        <h3>Edit ${escapeHtml(markdownHeading(markdown))}</h3>
        <span class="path">docs/pseudocode/${escapeHtml(item.file)}</span>
      </header>
      <div class="pseudocode-editor">
        <label for="pseudocode-editor-${escapeHtml(item.file)}">Markdown source</label>
        <textarea id="pseudocode-editor-${escapeHtml(item.file)}" data-pseudocode-draft spellcheck="false">${escapeHtml(markdown)}</textarea>
        <div class="pseudocode-editor-actions">
          <span class="pseudocode-editor-status" data-pseudocode-status aria-live="polite">No changes yet</span>
          <button type="button" class="secondary" data-pseudocode-cancel>Cancel</button>
          <button type="button" data-pseudocode-save disabled>Save</button>
        </div>
      </div>
    </article>
  `
}

function replacePseudocodeCard(card, html) {
  const template = document.createElement('template')
  template.innerHTML = html.trim()
  const replacement = template.content.firstElementChild
  card.replaceWith(replacement)
  return replacement
}

function setPseudocodeEditorBusy(editor, busy) {
  const textarea = editor.querySelector('[data-pseudocode-draft]')
  const cancelButton = editor.querySelector('[data-pseudocode-cancel]')
  const saveButton = editor.querySelector('[data-pseudocode-save]')
  textarea.disabled = busy
  cancelButton.disabled = busy
  saveButton.disabled = busy
}

async function savePseudocodeDraft(editor, item, markdownByFile) {
  const textarea = editor.querySelector('[data-pseudocode-draft]')
  const status = editor.querySelector('[data-pseudocode-status]')
  const draftMarkdown = textarea.value

  setPseudocodeEditorBusy(editor, true)
  status.textContent = 'Saving...'
  status.classList.remove('error')

  try {
    const response = await fetch(pseudocodeSavePath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: item.file, markdown: draftMarkdown }),
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.error || `${response.status} ${response.statusText}`)

    const savedMarkdown = await (await fetchFresh(`${pseudocodeBasePath}${item.file}`)).text()
    markdownByFile.set(item.file, savedMarkdown)
    replacePseudocodeCard(editor, renderPseudocodeCard(item, savedMarkdown))
  } catch (error) {
    setPseudocodeEditorBusy(editor, false)
    status.textContent = `Save failed: ${error.message}`
    status.classList.add('error')
  }
}

function installPseudocodeEditor(grid, manifest, markdownByFile) {
  if (!pseudocodeEditingEnabled) return

  const itemsByFile = new Map(manifest.map((item) => [item.file, item]))

  grid.addEventListener('dblclick', (event) => {
    const card = event.target.closest('[data-pseudocode-file]')
    if (!card || card.matches('[data-pseudocode-editor]')) return

    const item = itemsByFile.get(card.dataset.pseudocodeFile)
    const markdown = item && markdownByFile.get(item.file)
    if (!item || markdown === undefined) return

    const editor = replacePseudocodeCard(card, renderPseudocodeEditor(item, markdown))
    editor.querySelector('[data-pseudocode-draft]').focus()
  })

  grid.addEventListener('input', (event) => {
    if (!event.target.matches('[data-pseudocode-draft]')) return
    const editor = event.target.closest('[data-pseudocode-editor]')
    const savedMarkdown = markdownByFile.get(editor.dataset.pseudocodeFile)
    const changed = event.target.value !== savedMarkdown
    editor.querySelector('[data-pseudocode-save]').disabled = !changed
    const status = editor.querySelector('[data-pseudocode-status]')
    status.textContent = changed ? 'Unsaved changes' : 'No changes yet'
    status.classList.remove('error')
  })

  grid.addEventListener('click', (event) => {
    const button = event.target.closest('button')
    if (!button) return
    const editor = button.closest('[data-pseudocode-editor]')
    if (!editor) return

    const item = itemsByFile.get(editor.dataset.pseudocodeFile)
    if (button.matches('[data-pseudocode-cancel]')) {
      replacePseudocodeCard(editor, renderPseudocodeCard(item, markdownByFile.get(item.file)))
      return
    }
    if (button.matches('[data-pseudocode-save]') && !button.disabled) {
      savePseudocodeDraft(editor, item, markdownByFile)
    }
  })

  grid.addEventListener('keydown', (event) => {
    if (!event.target.matches('[data-pseudocode-draft]')) return
    const editor = event.target.closest('[data-pseudocode-editor]')
    if (event.key === 'Escape') {
      event.preventDefault()
      editor.querySelector('[data-pseudocode-cancel]').click()
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      editor.querySelector('[data-pseudocode-save]').click()
    }
  })
}

function renderPseudocodeLoadError(title, message) {
  return `
    <article class="algorithm-card wide">
      <header>
        <h3>${escapeHtml(title)}</h3>
        <span class="path">docs/pseudocode/</span>
      </header>
      <div class="pseudocode">
        <div class="pseudocode-line">
          <span class="pseudocode-stmt">${escapeHtml(message)}</span>
        </div>
      </div>
    </article>
  `
}

async function fetchFresh(path) {
  const response = await fetch(`${path}?t=${Date.now()}`, { cache: 'no-store' })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return response
}

async function installPseudocodeRenderer() {
  const grid = document.querySelector('[data-pseudocode-grid]')
  if (!grid) return

  try {
    const manifest = await (await fetchFresh(`${pseudocodeBasePath}manifest.json`)).json()
    const markdownByFile = new Map()
    const cards = await Promise.all(manifest.map(async (item) => {
      try {
        const markdown = await (await fetchFresh(`${pseudocodeBasePath}${item.file}`)).text()
        markdownByFile.set(item.file, markdown)
        return renderPseudocodeCard(item, markdown)
      } catch (error) {
        return renderPseudocodeLoadError(item.file, `Could not load Markdown: ${error.message}`)
      }
    }))
    grid.innerHTML = cards.join('')
    installPseudocodeEditor(grid, manifest, markdownByFile)
  } catch (error) {
    grid.innerHTML = renderPseudocodeLoadError('Pseudocode Manifest', `Could not load manifest: ${error.message}`)
  }
}

function buildSidebar(pathname) {
  const sidebar = document.createElement('aside')
  sidebar.className = 'site-sidebar'
  sidebar.innerHTML = `
    <a class="site-brand" href="/">
      <span class="brand-mark">PS</span>
      <span>
        <strong>PuzzleScript</strong>
        <small>Research Workbench</small>
      </span>
    </a>
    <nav class="site-nav" aria-label="Main navigation">
      ${primaryNavItems.map((item) => navLink(item, pathname)).join('')}
      ${navGroup('Research traces', traceNavItems, pathname)}
      ${navGroup('Reference', referenceNavItems, pathname)}
    </nav>
    <div class="site-note">
      Local workbench, architecture notes, and experiment evidence.
    </div>
  `
  return sidebar
}

function installShell() {
  if (document.querySelector('.site-layout')) return

  const main = document.querySelector('main')
  if (!main) return

  const pathname = normalizedPath()
  const layout = document.createElement('div')
  layout.className = 'site-layout'
  const content = document.createElement('div')
  content.className = 'site-content'

  document.body.insertBefore(layout, main)
  layout.appendChild(buildSidebar(pathname))
  layout.appendChild(content)
  content.appendChild(main)
}

installShell()
installPseudocodeRenderer()
