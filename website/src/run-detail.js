import { api, escapeHtml as e } from './runs-shared.js'
const root = document.querySelector('[data-record]'), run = new URLSearchParams(location.search).get('run') || ''
const colors = ['#111820','#2962a8','#d13e35','#2f9d62','#e2b53f','#7e8790','#c85aa1','#ef8d32','#56b9c9','#754b33','#d7dde1','#8fb1db','#ef938b','#8bd0a7','#f4d978','#fff']
let index = null, total = 0, loading = false
function grid(frame) {
  const canvas = root.querySelector('canvas'), ctx = canvas.getContext('2d')
  const size = 40
  canvas.width = (frame?.[0]?.length || 1) * size; canvas.height = (frame?.length || 1) * size
  ctx.font = '12px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  for (let y=0; y<(frame?.length || 0); y++) for (let x=0; x<frame[y].length; x++) {
    const id = frame[y][x]
    ctx.fillStyle = colors[id] || `hsl(${(id * 137.508) % 360} 55% 35%)`
    ctx.fillRect(x*size,y*size,size,size)
    ctx.fillStyle = '#000b'; ctx.fillRect(x*size+1,y*size+11,size-2,18)
    ctx.fillStyle = '#fff'; ctx.fillText(String(id),x*size+size/2,y*size+size/2)
  }
}
async function refresh() {
  if (loading) return
  loading = true
  try {
    const record = await api(`/record?run=${encodeURIComponent(run)}`)
    root.querySelector('[data-title]').textContent = run
    const result = record.result, config = record.config
    const facts = {Game:config.game_id, Model:config.model, Effort:config.reasoning_effort,
      Condition:config.condition || 'baseline', Outcome:result.solved ? 'Solved' : result.status === 'completed' ? 'Completed · unsolved' : result.status || 'No final result yet',
      Reason:result.reason?.replaceAll('_',' '), Levels:result.levels_completed == null ? '—' : `${result.levels_completed} / ${result.win_levels ?? '—'}`,
      Actions:result.action_count ?? record.latest_transition.action_index ?? 0}
    root.querySelector('[data-result-summary]').innerHTML = Object.entries(facts).map(([label,value]) => `<div><dt>${e(label)}</dt><dd>${e(value ?? '—')}</dd></div>`).join('')
    root.querySelector('[data-result]').textContent = JSON.stringify({result:record.result, error:record.error, settings:record.config}, null, 2)
    root.querySelector('[data-files]').innerHTML = record.files.map(file => `<li><a href="/api/workbench/record/file?run=${encodeURIComponent(run)}&file=${encodeURIComponent(file)}">${e(file)}</a></li>`).join('')
    total = record.latest_transition.action_index || 0
    if (index !== null) index = Math.min(Math.max(index,1),total)
    const transition = index === null ? record.latest_transition : (await api(`/record/timeline?run=${encodeURIComponent(run)}&index=${index}`)).transition
    grid(transition?.after?.grid)
    root.querySelector('[data-position]').textContent = total ? `Action ${index ?? total} / ${total} · ${transition.action} · ${transition.after?.state}` : 'No transitions recorded yet'
    root.querySelector('[data-transition]').textContent = JSON.stringify({action:transition.action, note:transition.note, before:transition.before?.state, after:transition.after?.state, levels:transition.after?.levels_completed},null,2)
    root.querySelector('[data-previous]').disabled = (index ?? total) <= 1
    root.querySelector('[data-next]').disabled = index === null || index >= total
    root.querySelector('[data-notice]').hidden = true
  } catch(error) { root.querySelector('[data-notice]').hidden = false; root.querySelector('[data-notice]').textContent = error.message }
  finally { loading = false }
}
root.querySelector('[data-previous]').addEventListener('click', () => { if (!loading) { index = Math.max(1,(index ?? total)-1); refresh() } })
root.querySelector('[data-next]').addEventListener('click', () => { if (!loading) { index = Math.min(total,(index ?? total)+1); refresh() } })
root.querySelector('[data-latest]').addEventListener('click', () => { index=null; refresh() })
root.querySelector('[data-refresh]').addEventListener('click', refresh)
refresh()
setInterval(() => { if (index === null) refresh() }, 5000)
