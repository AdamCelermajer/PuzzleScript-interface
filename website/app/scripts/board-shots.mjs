// Board screenshots: board, card detail, present mode (slides 1, 4, 7) and the print/PDF export.
//   node scripts/board-shots.mjs [widths] [themes]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const base = process.env.BASE ?? 'http://127.0.0.1:5174'
const widths = (process.argv[2] ?? '1440,2000').split(',').map(Number)
const themes = (process.argv[3] ?? 'light,dark').split(',')
mkdirSync('screenshots', { recursive: true })
const browser = await chromium.launch({ channel: 'msedge' })
for (const theme of themes) {
  for (const width of widths) {
    const context = await browser.newContext({ viewport: { width, height: Math.round(width * 0.5625) }, colorScheme: theme })
    await context.addInitScript((t) => localStorage.setItem('workbench.theme', t), theme)
    const page = await context.newPage()
    page.on('pageerror', (e) => console.error('page error:', e.message))
    const shot = async (name) => { await page.waitForTimeout(1200); await page.screenshot({ path: `screenshots/${name}-${theme}-${width}.png` }); console.log('saved', name, theme, width) }
    await page.goto(`${base}/board`, { waitUntil: 'networkidle' })
    await shot('board')
    await page.goto(`${base}/board/capability-scorecard`, { waitUntil: 'networkidle' })
    await shot('board-card')
    await page.goto(`${base}/board/present`, { waitUntil: 'networkidle' })
    await shot('present-1')
    for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight')
    await shot('present-4')
    await page.keyboard.press('End')
    await shot('present-7')
    if (theme === 'dark' && width === widths[0]) {
      await page.emulateMedia({ media: 'print' })
      await page.pdf({ path: 'screenshots/board-present.pdf', landscape: true, format: 'A4', printBackground: true })
      console.log('saved board-present.pdf')
      await page.emulateMedia({ media: 'screen' })
    }
    await page.keyboard.press('Escape')
    await page.waitForTimeout(500)
    if (!page.url().endsWith('/board')) console.error('Esc did not exit present mode:', page.url())
    await context.close()
  }
}
await browser.close()
