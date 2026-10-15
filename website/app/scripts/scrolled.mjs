// Screenshot a page after scrolling the main pane: node scripts/scrolled.mjs <path> <name> <scrollY>
import { chromium } from 'playwright'
const [path, name, y] = process.argv.slice(2)
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1480, height: 920 } })
await page.goto('http://127.0.0.1:5174' + path, { waitUntil: 'networkidle' })
await page.waitForTimeout(3500)
await page.locator('main').evaluate((m, top) => m.scrollTo(0, top), Number(y))
await page.waitForTimeout(500)
await page.screenshot({ path: `screenshots/${name}.png` })
await browser.close()
