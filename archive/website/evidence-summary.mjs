import fs from 'node:fs'
import { stat } from 'node:fs/promises'
import { createInterface } from 'node:readline'

const cache = new Map()
const pending = new Map()
const maxCachedFiles = 128

function emptySummary() {
  return { actions: 0, levels: 0, events: 0, last_event: '', last_transition: null, recent: [] }
}

export async function readEvidenceSummary(path, recentLimit = 0) {
  let file
  try { file = await stat(path) } catch { return emptySummary() }
  const saved = cache.get(path)
  if (saved && saved.size === file.size && saved.mtimeMs === file.mtimeMs && saved.recentLimit >= recentLimit) {
    cache.delete(path)
    cache.set(path, saved)
    return saved.summary
  }

  const key = `${path}:${file.size}:${file.mtimeMs}:${recentLimit}`
  if (pending.has(key)) return pending.get(key)
  const work = (async () => {
    const summary = emptySummary()
    const input = fs.createReadStream(path, { encoding: 'utf8' })
    const lines = createInterface({ input, crlfDelay: Infinity })
    try {
      for await (const line of lines) {
        if (!line.trim()) continue
        let event
        try { event = JSON.parse(line) } catch { continue }
        if (!event || typeof event !== 'object' || Array.isArray(event)) continue
        summary.events += 1
        summary.last_event = event.type || ''
        if (event.type === 'transition') {
          summary.actions += 1
          summary.last_transition = event
          const level = Number(event?.payload?.after?.progress?.levels_completed)
          if (Number.isFinite(level)) summary.levels = Math.max(summary.levels, level)
        }
        if (recentLimit) {
          summary.recent.push(event)
          if (summary.recent.length > recentLimit) {
            summary.recent.sort((a, b) => String(a.recorded_at || '').localeCompare(String(b.recorded_at || '')))
            summary.recent.shift()
          }
        }
      }
    } catch {
      return emptySummary()
    } finally {
      lines.close()
      input.destroy()
    }
    cache.delete(path)
    cache.set(path, { size: file.size, mtimeMs: file.mtimeMs, recentLimit, summary })
    if (cache.size > maxCachedFiles) cache.delete(cache.keys().next().value)
    return summary
  })()
  pending.set(key, work)
  try { return await work } finally { pending.delete(key) }
}
