export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]))
}
export async function api(path, options = {}) {
  const response = await fetch(`/api/workbench${path}`, {cache:'no-store', ...options})
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('; ') : `Workbench request failed (${response.status})`)
  return data
}

export const agentName = value => ({opencode:'OpenCode', tools:'H1 · OpenRouter tools', raw:'H0 · raw model'}[value] || 'H2 · Codex')
export const providerName = value => ({opencode:'OpenCode Zen',openrouter:'OpenRouter',openai:'OpenAI'}[value] || value || '—')

export function enableRunRowNavigation(root) {
  const navigate = event => {
    if (event.defaultPrevented || ![0, 1].includes(event.button)) return
    // Embedded controls retain their own actions, and dragging to select text
    // must not unexpectedly open a run.
    if (event.target.closest('a,button,input,select,textarea,label,summary,[role="button"],[contenteditable="true"]') || window.getSelection()?.toString()) return
    const link = event.target.closest('tr[data-run-row]')?.querySelector('a[data-run-link]')
    if (!link) return
    event.preventDefault()
    if (event.button === 1 || event.ctrlKey || event.metaKey || event.shiftKey) window.open(link.href, '_blank', 'noopener')
    else window.location.assign(link.href)
  }
  root.addEventListener('click', navigate)
  root.addEventListener('auxclick', navigate)
}
