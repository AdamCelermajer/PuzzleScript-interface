// Thin fetch wrapper for the FastAPI workbench (prefix /api/workbench).
export const API = '/api/workbench'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** FastAPI errors are `{detail: string | [{loc, msg}]}`; AVO console routes use `{error}`. */
export function errorMessage(status: number, body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    const detail = record.detail ?? record.error
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string }
          const where = Array.isArray(entry.loc) ? entry.loc.filter((p) => p !== 'body').join('.') : ''
          return where ? `${where}: ${entry.msg}` : String(entry.msg ?? item)
        })
        .join('; ')
    }
  }
  if (typeof body === 'string' && body.trim()) return body.trim().slice(0, 400)
  return `${fallback} (HTTP ${status})`
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path.startsWith('/api/') ? path : API + path, {
    method,
    cache: 'no-store',
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let parsed: unknown = text
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    /* plain text body */
  }
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, parsed, `${method} ${path} failed`))
  return parsed as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
  /** Raw text (artifact files, markdown notes, jsonl). */
  text: async (path: string, signal?: AbortSignal): Promise<string> => {
    const response = await fetch(path.startsWith('/api/') ? path : API + path, { cache: 'no-store', signal })
    const text = await response.text()
    if (!response.ok) {
      let parsed: unknown = text
      try { parsed = JSON.parse(text) } catch { /* text */ }
      throw new ApiError(response.status, errorMessage(response.status, parsed, 'Could not read file'))
    }
    return text
  },
}

export const q = (params: Record<string, string | number | boolean | null | undefined>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}
