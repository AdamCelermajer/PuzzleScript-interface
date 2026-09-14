export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]))
}
export async function api(path, options = {}) {
  const response = await fetch(`/api/workbench${path}`, {cache:'no-store', ...options})
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('; ') : `Workbench request failed (${response.status})`)
  return data
}

export const agentName = value => value === 'opencode' ? 'OpenCode' : 'Codex'
export const providerName = value => ({opencode:'OpenCode Zen',openrouter:'OpenRouter',openai:'OpenAI'}[value] || value || '—')
