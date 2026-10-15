import DOMPurify from 'dompurify'
import katex from 'katex'
import { marked } from 'marked'

/** Copilot answers: GitHub markdown plus \( \) and \[ \] math, sanitized (ported from the old page). */
export function renderResearchMarkdown(content: string): string {
  const math: { placeholder: string; source: string; displayMode: boolean }[] = []
  const preserve = (source: string, displayMode: boolean) => {
    const placeholder = `CODEXMATHPLACEHOLDER${math.length}END`
    math.push({ placeholder, source: source.trim(), displayMode })
    return placeholder
  }
  const markdown = String(content || '')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, source: string) => preserve(source, true))
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, source: string) => preserve(source, false))
  let html = DOMPurify.sanitize(marked.parse(markdown, { gfm: true, breaks: true, async: false }) as string)
  for (const { placeholder, source, displayMode } of math) {
    const rendered = katex.renderToString(source, { displayMode, throwOnError: false, trust: false, strict: 'ignore' })
    html = html.replaceAll(placeholder, `<span class="${displayMode ? 'block overflow-x-auto py-1' : ''}">${rendered}</span>`)
  }
  return DOMPurify.sanitize(html)
}
