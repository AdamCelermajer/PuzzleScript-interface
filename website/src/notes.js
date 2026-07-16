const notesPath = '/docs/notes/workbench-notes.md'
const notesSavePath = '/__notes/save'
const editingEnabled = import.meta.env.DEV

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
      closeList()
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

if (root) {
  const draft = root.querySelector('[data-notes-draft]')
  const preview = root.querySelector('[data-notes-preview]')
  const editor = root.querySelector('[data-notes-editor]')
  const status = root.querySelector('[data-notes-status]')
  const saveButton = root.querySelector('[data-notes-save]')
  const reloadButton = root.querySelector('[data-notes-reload]')
  const editButton = root.querySelector('[data-notes-view="edit"]')
  let savedMarkdown = ''
  let busy = false

  const isDirty = () => draft.value !== savedMarkdown
  const setStatus = (message, state = '') => {
    status.textContent = message
    status.dataset.state = state
  }
  const updateSaveState = () => {
    saveButton.disabled = busy || !editingEnabled || !isDirty()
  }
  const selectView = (view) => {
    root.querySelectorAll('[data-notes-view]').forEach((button) => {
      button.classList.toggle('active', button.dataset.notesView === view)
    })
    preview.hidden = view !== 'preview'
    editor.hidden = view !== 'edit'
    if (view === 'edit') draft.focus()
  }

  async function loadNotes() {
    busy = true
    updateSaveState()
    setStatus('Loading notes...')
    try {
      const response = await fetch(notesPath + '?t=' + Date.now(), { cache: 'no-store' })
      if (!response.ok) throw new Error(response.status + ' ' + response.statusText)
      savedMarkdown = await response.text()
      draft.value = savedMarkdown
      preview.innerHTML = renderMarkdown(savedMarkdown)
      setStatus(editingEnabled ? 'Saved' : 'Read only', 'saved')
    } catch (error) {
      setStatus('Load failed: ' + error.message, 'error')
    } finally {
      busy = false
      updateSaveState()
    }
  }

  async function saveNotes() {
    if (!editingEnabled || busy || !isDirty()) return
    busy = true
    updateSaveState()
    setStatus('Saving...')
    try {
      const response = await fetch(notesSavePath, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown: draft.value }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || response.status + ' ' + response.statusText)
      savedMarkdown = draft.value
      preview.innerHTML = renderMarkdown(savedMarkdown)
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
  })
  draft.addEventListener('input', () => {
    preview.innerHTML = renderMarkdown(draft.value)
    setStatus(isDirty() ? 'Unsaved changes' : 'Saved', isDirty() ? 'dirty' : 'saved')
    updateSaveState()
  })
  saveButton.addEventListener('click', saveNotes)
  reloadButton.addEventListener('click', () => {
    if (!isDirty() || window.confirm('Discard unsaved changes and reload?')) loadNotes()
  })
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      saveNotes()
    }
  })
  window.addEventListener('beforeunload', (event) => {
    if (!isDirty()) return
    event.preventDefault()
    event.returnValue = ''
  })

  if (!editingEnabled) {
    editButton.hidden = true
    saveButton.hidden = true
    reloadButton.hidden = true
  }
  loadNotes()
}
