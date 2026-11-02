const conditions = {
  'kimi-thinking': {
    label: 'Kimi thinking',
    model: 'moonshotai/kimi-k2.6',
    status: '1 / 5 steps, crashed on second move-selection call',
    thinkingPath: '/experiments/thinking-comparison/kimi-thinking/thinking_20260622T124354.json',
    logPath: '/experiments/thinking-comparison/kimi-thinking/log.txt',
    timelinePath: '/experiments/thinking-comparison/kimi-thinking/timeline.jsonl',
    rulesPath: '/experiments/thinking-comparison/kimi-thinking/rules.json',
  },
  'kimi-no-thinking': {
    label: 'Kimi no-thinking',
    model: 'moonshotai/kimi-k2.6',
    status: '5 / 5 steps, max steps reached',
    thinkingPath: null,
    logPath: '/experiments/thinking-comparison/kimi-no-thinking/log.txt',
    timelinePath: '/experiments/thinking-comparison/kimi-no-thinking/timeline.jsonl',
    rulesPath: '/experiments/thinking-comparison/kimi-no-thinking/rules.json',
  },
  'deepseek-thinking': {
    label: 'DeepSeek thinking',
    model: 'deepseek/deepseek-v4-pro',
    status: '5 / 5 steps, max steps reached',
    thinkingPath: '/experiments/thinking-comparison/deepseek-thinking/thinking_20260622T121610.json',
    logPath: '/experiments/thinking-comparison/deepseek-thinking/log.txt',
    timelinePath: '/experiments/thinking-comparison/deepseek-thinking/timeline.jsonl',
    rulesPath: '/experiments/thinking-comparison/deepseek-thinking/rules.json',
  },
}

const cache = new Map()
const conditionButtons = [...document.querySelectorAll('.trace-condition')]
const tabButtons = [...document.querySelectorAll('.trace-tabs button')]
const panels = [...document.querySelectorAll('.trace-panel')]

function setText(id, value) {
  const target = document.querySelector(id)
  if (target) target.textContent = value
}

async function fetchText(path) {
  if (!path) return null
  if (!cache.has(path)) {
    const response = await fetch(path)
    if (!response.ok) throw new Error(`${response.status} ${path}`)
    cache.set(path, await response.text())
  }
  return cache.get(path)
}

function prettyJson(text) {
  if (!text) return ''
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

function formatTimeline(text) {
  if (!text) return ''
  const lines = text.trim().split('\n')
  return lines.map((line, index) => {
    try {
      const event = JSON.parse(line)
      if (event.kind === 'state') {
        const grid = event.state?.grid?.map((row) => row.join(' ')).join('\n') || ''
        return `#${index + 1} STATE ${event.id}\nstate=${event.state?.state} levels=${event.state?.levels_completed}/${event.state?.win_levels}\n${grid}`
      }
      if (event.kind === 'action') {
        return `#${index + 1} ACTION ${event.id}\n${event.action}: ${event.before_id} -> ${event.after_id}`
      }
      return `#${index + 1}\n${JSON.stringify(event, null, 2)}`
    } catch {
      return `#${index + 1}\n${line}`
    }
  }).join('\n\n')
}

async function loadCondition(key) {
  const condition = conditions[key]
  if (!condition) return

  conditionButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.condition === key)
  })

  document.querySelector('#trace-label').textContent = condition.label
  document.querySelector('#trace-title').textContent = condition.model
  document.querySelector('#trace-meta').innerHTML = `
    <span class="chip gray">${condition.status}</span>
  `

  setText('#trace-reasoning', 'Loading reasoning trace...')
  setText('#trace-final', 'Loading final output...')
  setText('#trace-log', 'Loading log...')
  setText('#trace-timeline', 'Loading timeline...')
  setText('#trace-rules', 'Loading rules...')

  const [thinking, log, timeline, rules] = await Promise.all([
    condition.thinkingPath ? fetchText(condition.thinkingPath) : Promise.resolve(null),
    fetchText(condition.logPath),
    fetchText(condition.timelinePath),
    fetchText(condition.rulesPath),
  ])

  if (thinking) {
    const parsed = JSON.parse(thinking)
    setText('#trace-reasoning', parsed.reasoning || 'No reasoning field found.')
    setText('#trace-final', parsed.final_output || 'No final output field found.')
  } else {
    setText('#trace-reasoning', 'Reasoning was disabled for this condition. Use the log and timeline tabs to inspect behavior.')
    setText('#trace-final', 'No captured thinking final_output exists because reasoning capture was disabled.')
  }

  setText('#trace-log', log.trim())
  setText('#trace-timeline', formatTimeline(timeline))
  setText('#trace-rules', prettyJson(rules))
}

function activatePanel(name) {
  tabButtons.forEach((button) => button.classList.toggle('active', button.dataset.panel === name))
  panels.forEach((panel) => panel.classList.toggle('active', panel.dataset.panel === name))
}

conditionButtons.forEach((button) => {
  button.addEventListener('click', () => loadCondition(button.dataset.condition))
})

tabButtons.forEach((button) => {
  button.addEventListener('click', () => activatePanel(button.dataset.panel))
})

loadCondition('kimi-thinking').catch((error) => {
  setText('#trace-reasoning', `Failed to load trace: ${error.message}`)
})
