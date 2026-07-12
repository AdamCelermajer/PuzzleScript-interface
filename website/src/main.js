const primaryNavItems = [
  { href: '/', label: 'Overview', match: /^\/$/ },
  { href: '/docs/architecture.html', label: 'Architecture', match: /^\/docs\/architecture\.html$/ },
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
const pseudocodeVarNames = new Set([
  'A',
  'H',
  'P',
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
  'llm',
  'loop',
  'memory',
  'outcome',
  'plan',
  'planner',
  'probe',
  'records',
  'response',
  'rulebook',
  's',
  'state',
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
  return `
    <article class="algorithm-card${item.wide ? ' wide' : ''}">
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
    const cards = await Promise.all(manifest.map(async (item) => {
      try {
        const markdown = await (await fetchFresh(`${pseudocodeBasePath}${item.file}`)).text()
        return renderPseudocodeCard(item, markdown)
      } catch (error) {
        return renderPseudocodeLoadError(item.file, `Could not load Markdown: ${error.message}`)
      }
    }))
    grid.innerHTML = cards.join('')
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
      Static v1: finished artifacts, architecture notes, and experiment evidence. Live Python runner deferred.
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
