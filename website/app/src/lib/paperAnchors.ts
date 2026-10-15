// PDF text-layer anchors and underline drawing, ported from website/src/paper-investigation.js.
// Saved annotations carry {startSpan, startOffset, endSpan, endOffset} over `.textLayer span`s;
// older annotations without an anchor are located again by their normalized quote.

export interface PdfAnchor {
  startSpan: number
  startOffset: number
  endSpan: number
  endOffset: number
}

const elementOf = (node: Node): Element | null => (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)

export function normalizeText(value: string): string {
  return String(value).replace(/\s+/g, ' ').trim().toLowerCase()
}

function textOffsetWithin(element: Element, container: Node, offset: number): number | null {
  const range = document.createRange()
  range.selectNodeContents(element)
  try {
    range.setEnd(container, offset)
    return range.toString().length
  } catch {
    return null
  }
}

function textPointAt(element: Element | undefined, offset: number): { node: Node; offset: number } | null {
  if (!element) return null
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
  let remaining = offset
  let node = walker.nextNode()
  let lastNode: Node | null = null
  while (node) {
    lastNode = node
    const length = node.textContent?.length ?? 0
    if (remaining <= length) return { node, offset: remaining }
    remaining -= length
    node = walker.nextNode()
  }
  return lastNode ? { node: lastNode, offset: lastNode.textContent?.length ?? 0 } : null
}

export function pdfAnchorForRange(range: Range, page: Element): PdfAnchor | null {
  const spans = [...page.querySelectorAll('.textLayer span')]
  const startSpan = elementOf(range.startContainer)?.closest('.textLayer span')
  const endSpan = elementOf(range.endContainer)?.closest('.textLayer span')
  const startIndex = startSpan ? spans.indexOf(startSpan) : -1
  const endIndex = endSpan ? spans.indexOf(endSpan) : -1
  if (startIndex < 0 || endIndex < 0 || !startSpan || !endSpan) return null
  const startOffset = textOffsetWithin(startSpan, range.startContainer, range.startOffset)
  const endOffset = textOffsetWithin(endSpan, range.endContainer, range.endOffset)
  if (startOffset === null || endOffset === null) return null
  return { startSpan: startIndex, startOffset, endSpan: endIndex, endOffset }
}

export function rangeFromPdfAnchor(page: Element, anchor: PdfAnchor | null | undefined): Range | null {
  if (!anchor) return null
  const spans = [...page.querySelectorAll('.textLayer span')]
  const start = textPointAt(spans[anchor.startSpan], anchor.startOffset)
  const end = textPointAt(spans[anchor.endSpan], anchor.endOffset)
  if (!start || !end) return null
  const range = document.createRange()
  range.setStart(start.node, start.offset)
  range.setEnd(end.node, end.offset)
  return range
}

/** Find a quote across several elements, ignoring case and whitespace differences. */
export function rangeForQuote(elements: Element[], quote: string): Range | null {
  type Point = { node: Node; offset: number }
  const mapped: { character: string; start: Point; end: Point }[] = []
  let previousEnd: Point | null = null
  for (const element of elements) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
    const nodes: Node[] = []
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node)
    if (!nodes.length) continue
    if (previousEnd && mapped.at(-1)?.character !== ' ') mapped.push({ character: ' ', start: previousEnd, end: { node: nodes[0], offset: 0 } })
    for (const textNode of nodes) {
      const text = textNode.textContent ?? ''
      for (let offset = 0; offset < text.length; offset += 1) {
        const character = text[offset]
        const start = { node: textNode, offset }
        const end = { node: textNode, offset: offset + 1 }
        if (/\s/.test(character)) {
          if (mapped.length && mapped.at(-1)!.character !== ' ') mapped.push({ character: ' ', start, end })
        } else {
          mapped.push({ character: character.toLowerCase(), start, end })
        }
        previousEnd = end
      }
    }
  }
  const needle = normalizeText(quote)
  const index = mapped.map((m) => m.character).join('').indexOf(needle)
  if (!needle || index < 0) return null
  const first = mapped[index]
  const last = mapped[index + needle.length - 1]
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.start.node, first.start.offset)
  range.setEnd(last.end.node, last.end.offset)
  return range
}

/** Draw clickable underline segments for `range` inside a `.pdf-page` (positions in unzoomed page units). */
export function drawPdfUnderline(page: HTMLElement, range: Range, annotationId: string, linked: boolean): void {
  const pageRect = page.getBoundingClientRect()
  const scale = Number(page.dataset.displayScale) || 1
  const lines: { left: number; right: number; bottom: number }[] = []
  for (const rect of range.getClientRects()) {
    if (rect.width <= 1 || rect.height <= 1) continue
    const item = { left: (rect.left - pageRect.left) / scale, right: (rect.right - pageRect.left) / scale, bottom: (rect.bottom - pageRect.top) / scale }
    const previous = lines.at(-1)
    if (previous && Math.abs(previous.bottom - item.bottom) < 2 && item.left - previous.right < 5) previous.right = Math.max(previous.right, item.right)
    else lines.push(item)
  }
  for (const line of lines) {
    const underline = document.createElement('span')
    underline.className = 'pdf-underline-segment' + (linked ? ' linked' : '')
    underline.dataset.pdfUnderline = annotationId
    underline.setAttribute('role', 'button')
    underline.setAttribute('tabindex', '0')
    underline.title = 'Click to link or unlink this underline from the next question'
    underline.style.left = `${line.left}px`
    underline.style.top = `${line.bottom - 2}px`
    underline.style.width = `${line.right - line.left}px`
    page.appendChild(underline)
  }
}
