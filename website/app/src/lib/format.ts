export function relativeTime(ms: number | null | undefined, now = Date.now()): string {
  if (!ms) return '—'
  const seconds = Math.round((now - ms) / 1000)
  if (seconds < 0) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

export function dateTime(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '' || value === 0) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** Compact launch time: no year for the current year. */
export function shortTime(value: number | string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const sameYear = date.getFullYear() === new Date().getFullYear()
  return date.toLocaleString(undefined, { ...(sameYear ? {} : { year: '2-digit' }), month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function shortDate(value: number | string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  if (seconds < 90) return `${Math.round(seconds)}s`
  const minutes = seconds / 60
  if (minutes < 90) return `${Math.round(minutes)}m`
  return `${(minutes / 60).toFixed(1)}h`
}

export function bytes(value: number | null | undefined): string {
  if (!value && value !== 0) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

/** Last path segments of a run id, readable in a table cell. */
export function shortId(id: string | null | undefined, segments = 2): string {
  if (!id) return '—'
  const parts = id.split('/').filter(Boolean)
  if (parts.at(-1) === 'campaign') parts.pop()
  return parts.slice(-segments).join('/')
}

export function gameName(id: string | null | undefined): string {
  if (!id) return '—'
  return id.replace(/^ps_/, '').replace(/-v\d+$/, '').replaceAll('_', ' ')
}
