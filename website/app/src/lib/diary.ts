import type { DiaryEntry } from '../api/types'

export const SECTIONS = ['Did', 'Found', 'Decided', 'Next'] as const

export function slugify(title: string): string {
  return title.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'entry'
}

export const entrySlug = (date: string, title: string) => `${date}-${slugify(title)}`

const list = (values: string[]) => `[${values.join(', ')}]`
const scalar = (value: string) => (/[:#[\]{}"',&*!|>%@`]/.test(value) || value.trim() !== value ? `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"` : value)

/** Full markdown file (front matter + body) for the raw editor; PUT /diary/{slug} accepts it as {text}. */
export function entryText(entry: Pick<DiaryEntry, 'date' | 'title' | 'threads' | 'explicit_runs' | 'commits' | 'docs' | 'reconstructed'> & { body?: string }): string {
  return [
    '---',
    `date: ${entry.date}`,
    `title: ${scalar(entry.title)}`,
    `threads: ${list(entry.threads)}`,
    `runs: ${list(entry.explicit_runs)}`,
    `commits: ${list(entry.commits)}`,
    `docs: ${list(entry.docs)}`,
    `reconstructed: ${entry.reconstructed ? 'true' : 'false'}`,
    '---',
    (entry.body ?? '').trim(),
    '',
  ].join('\n')
}

export function newEntryText(date: string, title: string, threads: string[]): string {
  return entryText({
    date,
    title,
    threads,
    explicit_runs: [],
    commits: [],
    docs: [],
    reconstructed: false,
    body: SECTIONS.map((s) => `## ${s}\n- `).join('\n\n'),
  })
}

/** Split the raw editor text for the live preview (mirrors workbench/diary.py split_text loosely). */
export function previewParts(text: string): { title: string; body: string } {
  const normalized = text.replace(/\r\n/g, '\n')
  const match = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(normalized)
  if (!match) return { title: '', body: normalized }
  const title = /^title:\s*(.*)$/m.exec(match[1])?.[1]?.replace(/^"(.*)"$/, '$1') ?? ''
  return { title, body: match[2] }
}

export function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
