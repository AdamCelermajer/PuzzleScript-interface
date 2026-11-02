import { api, escapeHtml as e } from './runs-shared.js'

const games = [
  {
    id:'ps_modality-v1', name:'Modality', score:'4 / 4', candidate:'x_0003',
    run:'output/avo-six-live-20260908-r7/repairs/modality-04/campaign',
    truth:[
      'White and black are incompatible for direct player movement; grey bridges both.',
      'A crate pushes when the player can enter its current terrain. The crate may land on the other colour.',
      'Every crate must be on a target to win.'
    ],
    sourceCode:'[ > Player White | Black ] -> CANCEL\n[ > Player Black | White ] -> CANCEL\n[ > Player Nonblack | Crate Nonblack ] -> [ > Player Nonblack | > Crate Nonblack ]\n[ > Player Black | Crate Black ] -> [ > Player Black | > Crate Black ]\nAll Crate on Target',
    learned:[
      'Same-checkpoint probes separated a successful white-to-dark crate push from the blocked next push.',
      'The final solver used terrain-aware BFS over player and crate positions and completed all four levels.',
      'Its notes corrected an earlier false direction-specific explanation and a mistaken level-four cell ID.'
    ],
    verdict:'Core terrain and goal rules recovered. Unseen object and terrain combinations remain untested.',
    source:'puzzlescript_interface/games/ps_modality-v1/script.txt:86',
    evidence:'x_0003/STRATEGY.md + x_0003/solver/research_record.md'
  },
  {
    id:'ps_knightoban-v1', name:'Knightoban', score:'6 / 6', candidate:'x_0008',
    run:'output/avo-three-continue-x10-20260908-r3/knightoban-04/campaign',
    truth:[
      'Normal crates have a direct push rule; knight crates use a separate contact rule.',
      'Contact offers knight landing cells. Perpendicular input selects a landing; ACTION5 commits it.',
      'Every target must have a crate to win.'
    ],
    sourceCode:'[> player no indicator | normalcrate] -> [> player no indicator | > normalcrate]\n[> player no indicator | Crate | | ] -> [ | player indicator_placing | | > knight_marker]\n[action player][selected_crate][player indicator_selecting] -> [action player][Crate][player]\nAll Target on crates',
    learned:[
      'Controlled contacts revealed knight offsets, preview states, spatial selection and commitment.',
      'The solver tracked multiple pieces and covered targets, then reached all six levels.',
      'A six-piece plateau was solved by faster joint planning rather than a new movement rule.'
    ],
    verdict:'Main observed knight mechanic recovered. The later prose model omits the separate normal-crate source rule and leaves single-option preview behavior open.',
    source:'puzzlescript_interface/games/ps_knightoban-v1/script.txt:122',
    evidence:'x_0008/STRATEGY.md + x_0008/solver/NOTES.md + RESEARCH.md'
  },
  {
    id:'ps_icecrates-v1', name:'IceCrates', score:'6 / 6', candidate:'x_0002',
    run:'output/workbench/20260922T104342-96361f28/run-0001/campaign',
    truth:[
      'A direction input repeatedly moves the player until the next move is blocked.',
      'Crates can push a contiguous train; a crate entering water is consumed and fills the cell.',
      'The stopped player must occupy the goal. Passing across it is insufficient.'
    ],
    sourceCode:'LEFT [ PlayerL | Crate ] -> [ PlayerL | LEFT Crate ] again\nLEFT [ > Crate | Crate ] -> [ > Crate | > Crate ] again\nLEFT [ > Crate | Water ] -> [ | FilledWater]\n[ PlayerL ] -> [ LEFT PlayerL ] again\nSome PlayerStill on Goal',
    learned:[
      'The agent falsified win-on-crossing and represented slides, boxes, water and goal-at-rest.',
      'A controlled sixth-level test found the missing two-box train interaction.',
      'Its revised solver completed six levels in 138 actions in the independent final evaluation.'
    ],
    verdict:'Core sliding, train, water and goal rules recovered. Animated water phase equivalence was tested on selected continuations.',
    source:'puzzlescript_interface/games/ps_icecrates-v1/script.txt:354',
    evidence:'x_0002/STRATEGY.md + x_0002/solver/TRAIN_FINDINGS.md + world_model.md'
  },
]

const tabs = document.querySelector('[data-game-tabs]')
const detail = document.querySelector('[data-game-detail]')
let selected = new URLSearchParams(location.search).get('game') || games[0].id
if (!games.some(game => game.id === selected)) selected = games[0].id
const lab = run => `/experiments/avo-lab.html?run=${encodeURIComponent(run)}`
const submission = run => `/runs/submission.html?run=${encodeURIComponent(run)}`

function renderGame() {
  const game = games.find(item => item.id === selected)
  tabs.innerHTML = games.map(item => `<button type="button" data-game="${e(item.id)}" aria-selected="${item.id === selected}">${e(item.name)}</button>`).join('')
  detail.innerHTML = `<div class="mechanics-grid">
    <article class="mechanics-card"><p class="eyebrow">Actual game source</p><h2>${e(game.name)} rules</h2><ul>${game.truth.map(rule => `<li>${e(rule)}</li>`).join('')}</ul><details><summary>Show source rule excerpt</summary><pre>${e(game.sourceCode)}</pre></details><small>Source: ${e(game.source)}</small></article>
    <article class="mechanics-card"><p class="eyebrow">Saved AVO work</p><h2>Agent inference · ${e(game.score)}</h2><ul>${game.learned.map(rule => `<li>${e(rule)}</li>`).join('')}</ul><small>Evidence: ${e(game.evidence)}</small></article>
  </div><p class="mechanics-verdict"><strong>Assessment:</strong> ${e(game.verdict)}</p>
  <div class="mechanics-links"><a href="${lab(game.run)}">Replay original run and reasoning ↗</a><a href="${submission(game.run)}">Solver and report ↗</a><a href="/games/?game=${encodeURIComponent(game.id)}">Game page ↗</a></div>`
}
tabs.addEventListener('click', event => {
  const button = event.target.closest('[data-game]')
  if (!button) return
  selected = button.dataset.game
  const url = new URL(location.href); url.searchParams.set('game', selected); history.replaceState(null, '', url)
  renderGame()
})
renderGame()

async function renderReruns() {
  const container = document.querySelector('[data-rerun-list]')
  try {
    const catalog = await api('/catalog')
    const requested = new URLSearchParams(location.search).get('job')
    const matches = catalog.runs.filter(run => run.kind === 'avo' && games.some(game => game.id === run.game_id) && run.model === 'openrouter/deepseek/deepseek-v4.1-flash')
    const batches = [...new Set(matches.map(run => run.batch))].sort().reverse()
    const batch = requested || batches[0]
    const runs = matches.filter(run => run.batch === batch)
      .sort((left, right) => games.findIndex(game => game.id === left.game_id) - games.findIndex(game => game.id === right.game_id))
    if (!runs.length) { container.textContent = requested ? 'No campaigns found for this batch yet.' : 'The DeepSeek batch has not been launched yet.'; return }
    container.innerHTML = runs.map(run => `<div class="mechanics-run"><div><strong>${e(games.find(game => game.id === run.game_id)?.name || run.game_id)}</strong><span>${e(run.status)} · ${e(run.evaluated ?? 0)} evaluated · best fitness ${e(run.best_fitness ?? '—')}${run.solved ? ' · solved' : ''}</span></div><a href="${lab(run.id)}">Inspect run and action reasoning ↗</a></div>`).join('')
  } catch (error) { container.textContent = `Run status unavailable: ${error.message}` }
}
document.querySelector('[data-refresh-runs]').addEventListener('click', renderReruns)
renderReruns()
setInterval(renderReruns, 30000)
