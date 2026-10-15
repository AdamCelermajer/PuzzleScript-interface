// Screenshots of Tools: notes (view + edit), paper investigation, BFS optimal path (short local search).
import { chromium } from 'playwright'
const base = process.argv[2] ?? 'http://127.0.0.1:5174'
const browser = await chromium.launch({ channel: 'msedge' })
const page = await browser.newPage({ viewport: { width: 1480, height: 920 } })
page.on('pageerror', (e) => console.error('page error:', e.message))
const shot = async (name) => { await page.waitForTimeout(800); await page.screenshot({ path: `screenshots/${name}.png` }); console.log('saved', name) }
const step = async (name, fn) => { try { await fn() } catch (e) { console.error(`FLOW ${name} failed:`, e.message); await shot(`fail-${name}`) } }

await step('tools', async () => { await page.goto(base + '/tools', { waitUntil: 'networkidle' }); await shot('tools') })
await step('notes', async () => {
  await page.goto(base + '/tools/notes', { waitUntil: 'networkidle' })
  await shot('notes')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.locator('textarea').click()
  await page.keyboard.press('Control+End')
  await page.keyboard.type('\n\n(draft line, not saved)')
  await shot('notes-edit')
})
await step('papers', async () => {
  await page.goto(base + '/tools/papers', { waitUntil: 'networkidle' })
  await page.locator('.pdf-page canvas').first().waitFor({ timeout: 60_000 }).catch(() => {})
  await page.waitForTimeout(4000)
  await shot('papers')
  await page.getByRole('button', { name: /Dossier/ }).click()
  await shot('papers-dossier')
})
await step('optimal', async () => {
  await page.goto(base + '/tools/optimal-path', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Start search' }).click()
  await page.getByText(/whole-game path|No winning path/).first().waitFor({ timeout: 120_000 })
  await page.getByRole('button', { name: 'Next →' }).click().catch(() => {})
  await shot('optimal-path')
})
await step('campaign', async () => {
  await page.goto(base + '/runs/avo/output/runs/harness-smoke-opencode-campaign/campaign', { waitUntil: 'networkidle' })
  await page.waitForTimeout(3000)
  await shot('spec-campaign')
  await page.locator('main').evaluate((m) => m.scrollTo(0, 700))
  await shot('spec-campaign-trace')
})
await browser.close()
