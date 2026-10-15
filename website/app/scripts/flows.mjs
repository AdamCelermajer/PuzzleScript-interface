// Drives the main interactive flows (no launches, no saves) and screenshots the results.
//   node scripts/flows.mjs [baseUrl]
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const base = process.argv[2] ?? 'http://127.0.0.1:5174'
mkdirSync('screenshots', { recursive: true })
let browser
for (const channel of ['msedge', 'chrome']) {
  try { browser = await chromium.launch({ channel }); break } catch { /* next */ }
}
const context = await browser.newContext({ viewport: { width: 1480, height: 920 }, colorScheme: process.env.SCHEME ?? 'light' })
const page = await context.newPage()
page.on('pageerror', (e) => console.error('page error:', e.message))
const shot = async (name) => { await page.waitForTimeout(800); await page.screenshot({ path: `screenshots/${name}.png` }); console.log('saved', name) }
const step = async (name, fn) => { try { await fn() } catch (e) { console.error(`FLOW ${name} failed:`, e.message); await shot(`fail-${name}`) } }

await step('launch', async () => {
  await page.goto(base + '/launch', { waitUntil: 'networkidle' })
  await page.evaluate(() => localStorage.removeItem('workbench.launch.form.v1'))
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('button', { name: /Campaign/ }).first().click()
  await page.getByRole('button', { name: /Codex CLI/ }).click()
  await page.getByRole('button', { name: 'gpt-5.6-sol' }).click()
  await page.getByRole('button', { name: /OpenCode/ }).click()
  await page.getByPlaceholder(/Search \d+ models/).first().fill('qwen3.8-27b')
  await page.locator('tr', { hasText: 'openrouter/qwen/qwen3.8-27b' }).first().click()
  await page.getByPlaceholder(/playable games/).fill('modality')
  await page.locator('tr', { hasText: 'ps_modality-v1' }).first().click()
  await page.getByRole('button', { name: 'Preview', exact: true }).click()
  await page.getByText(/runs · \d+ at once/).waitFor({ timeout: 30_000 })
  await shot('flow-launch-preview')
})

await step('compare', async () => {
  const runs = ['output/workbench/20261013T152559-avo-max-92c30e52/run-0001/campaign', 'output/workbench/20261013T165330-avo-27b-modality/run-0001/campaign',
    'output/codex_agent/modality-55-high-baseline-plus-1000-20260907T181409-r3', 'output/workbench/20261015T012502-nano-modality-baseline-plus-fixed-714e64/run-0002']
  await page.goto(base + '/compare?' + runs.map((r) => 'run=' + encodeURIComponent(r)).join('&'), { waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)
  await page.mouse.move(700, 560)
  await shot('flow-compare')
})

await step('campaign-trace', async () => {
  await page.goto(base + '/runs/output/workbench/20261013T152559-avo-max-92c30e52/run-0001/campaign', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Agent timeline' }).click()
  await page.waitForTimeout(2500)
  await page.locator('main').evaluate((m) => m.scrollTo(0, 900))
  await shot('flow-campaign-trace')
  await page.getByRole('button', { name: 'Solver & world model' }).click()
  await page.waitForTimeout(2500)
  await page.locator('main').evaluate((m) => m.scrollTo(0, 900))
  await shot('flow-campaign-solver')
})

await step('play', async () => {
  await page.goto(base + '/benchmarks/ps_modality-v1', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Play', exact: true }).click()
  await page.getByRole('button', { name: 'Start playing' }).click()
  await page.getByAltText(/frame/).waitFor({ timeout: 30_000 })
  await page.getByAltText(/frame/).click()
  for (const key of ['ArrowRight', 'ArrowRight', 'ArrowDown']) { await page.keyboard.press(key); await page.waitForTimeout(400) }
  await shot('flow-play')
})

await step('diary-new', async () => {
  await page.goto(base + '/diary/new', { waitUntil: 'networkidle' })
  await page.getByPlaceholder('What happened').fill('Workbench SPA first look')
  await page.getByRole('button', { name: 'workbench', exact: true }).click()
  await page.getByRole('button', { name: 'Use template' }).click()
  await page.locator('textarea').click()
  await page.keyboard.press('Control+End')
  await page.keyboard.type('\nTried the new **SPA**.')
  await shot('flow-diary-new')
})

await browser.close()
