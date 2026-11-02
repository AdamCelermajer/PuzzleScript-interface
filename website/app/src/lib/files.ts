/** How a saved run file is shown: markdown rendered, JSON indented, JSON lines one indented record each. */
export interface ReadableFile {
  kind: 'markdown' | 'text'
  text: string
  note?: string
}

export const JSONL_PREVIEW = 200

export function readableFile(name: string, raw: string): ReadableFile {
  if (name.endsWith('.md')) return { kind: 'markdown', text: raw }
  if (name.endsWith('.json')) {
    try {
      return { kind: 'text', text: JSON.stringify(JSON.parse(raw), null, 2) }
    } catch {
      return { kind: 'text', text: raw, note: 'Not valid JSON; shown as saved.' }
    }
  }
  if (name.endsWith('.jsonl')) {
    const lines = raw.split('\n').filter((l) => l.trim())
    const shown = lines.slice(-JSONL_PREVIEW)
    const text = shown.map((line, i) => {
      const number = lines.length - shown.length + i + 1
      try {
        return `#${number}\n${JSON.stringify(JSON.parse(line), null, 2)}`
      } catch {
        return `#${number}\n${line}`
      }
    }).join('\n\n')
    return { kind: 'text', text, note: lines.length > shown.length ? `Showing the last ${shown.length} of ${lines.length} records; the raw link has them all.` : `${lines.length} records.` }
  }
  return { kind: 'text', text: raw }
}
