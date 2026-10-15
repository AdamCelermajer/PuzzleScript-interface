// Screenshots at given widths and themes (theme forced via localStorage).
//   node scripts/shots.mjs <widths e.g. 1440,2000> <themes e.g. light,dark> name=path[@scrollY] ...
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'
const base = process.env.BASE ?? 'http://127.0.0.1:5174'
const [widths, themes, ...pages] = process.argv.slice(2)
mkdirSync('screenshots', { recursive: true })
const browser = await chromium.launch({ channel: 'msedge' })
for (const theme of themes.split(',')) {
  for (const width of widths.split(',').map(Number)) {
    const context = await browser.newContext({ viewport: { width, height: Math.round(width * 0.62) }, colorScheme: theme })
    await context.addInitScript((t) => localStorage.setItem('workbench.theme', t), theme)
    const page = await context.newPage()
    page.on('pageerror', (e) => console.error('page error:', e.message))
    for (const spec of pages) {
      const eq = spec.indexOf('=')
      const name = spec.slice(0, eq)
      const [path, scroll] = spec.slice(eq + 1).split('@')
      await page.goto(base + path, { waitUntil: 'networkidle', timeout: 120_000 }).catch((e) => console.error(name, e.message))
      await page.waitForTimeout(Number(process.env.WAIT ?? 2500))
      if (scroll) { await page.locator('main').evaluate((m, y) => m.scrollTo(0, y), Number(scroll)); await page.waitForTimeout(400) }
      const file = `screenshots/${name}-${theme}-${width}.png`
      await page.screenshot({ path: file })
      console.log('saved', file)
    }
    await context.close()
  }
}
await browser.close()
