// Screenshots of each section into ./screenshots (gitignored). Uses the installed Edge or
// Chrome through Playwright, so no browser download is needed.
//   node scripts/screenshots.mjs [baseUrl] [name=path ...]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const base = process.argv[2] && !process.argv[2].includes('=') ? process.argv[2] : 'http://127.0.0.1:5174'
const custom = process.argv.slice(2).filter((a) => a.includes('='))
const pages = custom.length
  ? custom.map((a) => a.split(/=(.*)/s).slice(0, 2))
  : [
      ['runs', '/runs'],
      ['launch', '/launch'],
      ['compare', '/compare'],
      ['benchmarks', '/benchmarks'],
      ['diary', '/diary'],
      ['tools', '/tools'],
    ]
mkdirSync('screenshots', { recursive: true })
let browser
for (const channel of ['msedge', 'chrome']) {
  try { browser = await chromium.launch({ channel }); break } catch { /* try next */ }
}
if (!browser) throw new Error('No Edge or Chrome found for Playwright')
const schemes = (process.env.SCHEMES ?? 'light').split(',')
for (const colorScheme of schemes) {
  const context = await browser.newContext({ viewport: { width: 1480, height: 920 }, colorScheme, deviceScaleFactor: 1 })
  const page = await context.newPage()
  page.on('pageerror', (error) => console.error(`[${colorScheme}] page error:`, error.message))
  page.on('console', (msg) => { if (msg.type() === 'error') console.error(`[${colorScheme}] console:`, msg.text()) })
  for (const [name, path] of pages) {
    await page.goto(base + path, { waitUntil: 'networkidle', timeout: 90_000 }).catch((e) => console.error(name, e.message))
    await page.waitForTimeout(Number(process.env.WAIT ?? 1500))
    const file = `screenshots/${name}${colorScheme === 'light' ? '' : '-' + colorScheme}.png`
    await page.screenshot({ path: file, fullPage: process.env.FULL === '1' })
    console.log('saved', file)
  }
  await context.close()
}
await browser.close()
