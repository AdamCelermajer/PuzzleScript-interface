const notesSavePath = '/__notes/save'
const editingEnabled = import.meta.env.DEV
const noteDocuments = {
  notes: {
    label: 'Notes',
    file: 'workbench-notes.md',
    path: '/docs/notes/workbench-notes.md',
  },
  todo: {
    label: 'Todo',
    file: 'todo.md',
    path: '/docs/notes/todo.md',
  },
  benchmark: {
    label: 'Benchmark Positioning',
    file: 'benchmark-positioning.md',
    path: '/docs/notes/benchmark-positioning.md',
  },
}

const root = document.querySelector('[data-notes]')

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]))
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/\x60([^\x60]+)\x60/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r/g, '').split('\n')
  const rendered = []
  let paragraph = []
  let listType = ''
  let code = []
  let inCode = false

  const flushParagraph = () => {
    if (paragraph.length) rendered.push('<p>' + inlineMarkdown(paragraph.join(' ')) + '</p>')
    paragraph = []
  }
  const closeList = () => {
    if (listType) rendered.push('</' + listType + '>')
    listType = ''
  }

  for (const line of lines) {
    if (line.startsWith('\x60\x60\x60')) {
      if (inCode) {
        rendered.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>')
        code = []
      } else {
        flushParagraph()
        closeList()
      }
      inCode = !inCode
      continue
    }
    if (inCode) {
      code.push(line)
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    const unordered = line.match(/^[-*]\s+(.+)$/)
    const ordered = line.match(/^\d+\.\s+(.+)$/)
    if (heading) {
      flushParagraph()
      closeList()
      const level = heading[1].length
      rendered.push('<h' + level + '>' + inlineMarkdown(heading[2]) + '</h' + level + '>')
    } else if (unordered || ordered) {
      flushParagraph()
      const nextType = unordered ? 'ul' : 'ol'
      if (listType !== nextType) {
        closeList()
        rendered.push('<' + nextType + '>')
        listType = nextType
      }
      rendered.push('<li>' + inlineMarkdown((unordered || ordered)[1]) + '</li>')
    } else if (line.startsWith('> ')) {
      flushParagraph()
      closeList()
      rendered.push('<blockquote>' + inlineMarkdown(line.slice(2)) + '</blockquote>')
    } else if (!line.trim()) {
      flushParagraph()
    } else {
      closeList()
      paragraph.push(line.trim())
    }
  }

  if (inCode) rendered.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>')
  flushParagraph()
  closeList()
  return rendered.join('')
}

function makeSectionsCollapsible(container) {
  const children = [...container.children]
  let sectionBody = null

  for (const child of children) {
    if (child.tagName === 'H2') {
      const details = document.createElement('details')
      const summary = document.createElement('summary')
      const body = document.createElement('div')
      details.className = 'notes-section'
      details.open = true
      summary.innerHTML = child.innerHTML
      body.className = 'notes-section-body'
      container.insertBefore(details, child)
      details.append(summary, body)
      child.remove()
      sectionBody = body
    } else if (sectionBody) {
      sectionBody.append(child)
    }
  }
}

if (root) {
  const draft = root.querySelector('[data-notes-draft]')
  const preview = root.querySelector('[data-notes-preview]')
  const editor = root.querySelector('[data-notes-editor]')
  const editorLabel = root.querySelector('[data-notes-editor-label]')
  const status = root.querySelector('[data-notes-status]')
  const sourcePath = root.querySelector('[data-notes-path]')
  const saveButton = root.querySelector('[data-notes-save]')
  const reloadButton = root.querySelector('[data-notes-reload]')
  const editButton = root.querySelector('[data-notes-view="edit"]')
  const documentStates = Object.fromEntries(
    Object.keys(noteDocuments).map((key) => [key, { saved: '', draft: '', loaded: false }]),
  )
  let activeDocument = 'notes'
  let busy = false

  const activeDefinition = () => noteDocuments[activeDocument]
  const activeState = () => documentStates[activeDocument]
  const isDirty = (key = activeDocument) => {
    const state = documentStates[key]
    return state.loaded && state.draft !== state.saved
  }
  const hasDirtyDocuments = () => Object.keys(documentStates).some((key) => isDirty(key))
  const setStatus = (message, state = '') => {
    status.textContent = message
    status.dataset.state = state
  }
  const updateSaveState = () => {
    saveButton.disabled = busy || !editingEnabled || !isDirty()
  }
  const renderPreview = (markdown) => {
    preview.innerHTML = renderMarkdown(markdown)
    makeSectionsCollapsible(preview)
  }
  const updateDocumentChrome = () => {
    const definition = activeDefinition()
    root.querySelectorAll('[data-notes-document]').forEach((button) => {
      button.classList.toggle('active', button.dataset.notesDocument === activeDocument)
    })
    sourcePath.textContent = 'docs/notes/' + definition.file
    editorLabel.textContent = definition.label + ' Markdown'
  }
  const showActiveDocument = () => {
    const state = activeState()
    draft.value = state.draft
    renderPreview(state.draft)
    setStatus(
      isDirty() ? 'Unsaved changes' : editingEnabled ? 'Saved' : 'Read only',
      isDirty() ? 'dirty' : 'saved',
    )
    updateSaveState()
  }
  const selectView = (view) => {
    root.querySelectorAll('[data-notes-view]').forEach((button) => {
      button.classList.toggle('active', button.dataset.notesView === view)
    })
    preview.hidden = view !== 'preview'
    editor.hidden = view !== 'edit'
    if (view === 'edit') draft.focus()
  }

  async function loadDocument(key = activeDocument, force = false) {
    const definition = noteDocuments[key]
    const state = documentStates[key]
    if (!definition || busy) return
    if (state.loaded && !force) {
      if (activeDocument === key) showActiveDocument()
      return
    }

    busy = true
    updateSaveState()
    setStatus('Loading ' + definition.label.toLowerCase() + '...')
    try {
      const response = await fetch(definition.path + '?t=' + Date.now(), { cache: 'no-store' })
      if (!response.ok) throw new Error(response.status + ' ' + response.statusText)
      state.saved = await response.text()
      state.draft = state.saved
      state.loaded = true
      if (activeDocument === key) showActiveDocument()
    } catch (error) {
      setStatus('Load failed: ' + error.message, 'error')
    } finally {
      busy = false
      updateSaveState()
    }
  }

  async function saveNotes() {
    if (!editingEnabled || busy || !isDirty()) return
    const definition = activeDefinition()
    const state = activeState()
    busy = true
    updateSaveState()
    setStatus('Saving...')
    try {
      const response = await fetch(notesSavePath, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: definition.file, markdown: state.draft }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || response.status + ' ' + response.statusText)
      state.saved = state.draft
      renderPreview(state.saved)
      setStatus('Saved', 'saved')
    } catch (error) {
      setStatus('Save failed: ' + error.message, 'error')
    } finally {
      busy = false
      updateSaveState()
    }
  }

  root.addEventListener('click', (event) => {
    const viewButton = event.target.closest('[data-notes-view]')
    if (viewButton) selectView(viewButton.dataset.notesView)

    const documentButton = event.target.closest('[data-notes-document]')
    if (documentButton && documentButton.dataset.notesDocument !== activeDocument && !busy) {
      activeDocument = documentButton.dataset.notesDocument
      updateDocumentChrome()
      loadDocument(activeDocument)
    }
  })
  draft.addEventListener('input', () => {
    activeState().draft = draft.value
    renderPreview(draft.value)
    setStatus(isDirty() ? 'Unsaved changes' : 'Saved', isDirty() ? 'dirty' : 'saved')
    updateSaveState()
  })
  saveButton.addEventListener('click', saveNotes)
  reloadButton.addEventListener('click', () => {
    if (!isDirty() || window.confirm('Discard unsaved changes in this tab and reload?')) {
      loadDocument(activeDocument, true)
    }
  })
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      saveNotes()
    }
  })
  window.addEventListener('beforeunload', (event) => {
    if (!hasDirtyDocuments()) return
    event.preventDefault()
    event.returnValue = ''
  })

  if (!editingEnabled) {
    editButton.hidden = true
    saveButton.hidden = true
    reloadButton.hidden = true
  }
  updateDocumentChrome()
  loadDocument()
}
