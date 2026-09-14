import { api, escapeHtml as e, agentName } from './runs-shared.js'
const root=document.querySelector('[data-comparison]'), get=s=>root.querySelector(s)
let job=new URLSearchParams(location.search).get('job') || '', busy=false, comparisons=[]
const emptyContent=get('[data-comparison-content]').innerHTML
const modes=['final-only','between-hypotheses']
const value=v=>v == null ? '—' : e(v)
const duration=v=>v == null ? '—' : v<60 ? `${Math.round(v)}s` : `${Math.floor(v/60)}m ${Math.round(v%60)}s`
function historyChart(pair,budget){
  const all=modes.flatMap(m=>pair.runs[m]?.history || [])
  if(!all.length)return '<p class="field-note">Fitness curves appear after the first completed evaluation.</p>'
  const max=Math.max(1,...all.map(v=>v.fitness)), width=700,height=130,left=32,right=680,top=12,bottom=126
  const x=i=>left+(i-1)/Math.max(1,budget-1)*(right-left), y=f=>bottom-f/max*(bottom-top)
  const curves=modes.map((m,n)=>{
    let best=-Infinity;const color=n?'#7664aa':'#196d5f'
    const points=(pair.runs[m]?.history || []).map((v,i)=>{best=Math.max(best,v.fitness);return {x:x(i+1),y:y(best),fitness:best,candidate:v.candidate}})
    return `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${points.map(p=>`${p.x},${p.y}`).join(' ')}"/>${points.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="3.5" fill="${color}"><title>${e(m)} · ${e(p.candidate)} · best fitness ${e(p.fitness)}</title></circle>`).join('')}`
  }).join('')
  return `<svg viewBox="0 0 ${width} ${height+25}" role="img" aria-label="Best fresh fitness by evaluated candidate for both conditions"><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="#dce3e7"/><line x1="${left}" y1="${top}" x2="${right}" y2="${top}" stroke="#edf0f2"/><text x="5" y="${bottom+4}" fill="#82909b" font-size="10">0</text><text x="5" y="${top+4}" fill="#82909b" font-size="10">${max}</text><text x="${left}" y="150" fill="#82909b" font-size="10">1</text><text x="${right-10}" y="150" fill="#82909b" font-size="10">${budget}</text>${curves}</svg>`
}
function render(data){
  const c=data.config
  get('[data-comparison-content]').innerHTML=`<div class="comparison-settings"><span><strong>${e(agentName(c.agent_backend))}</strong> coding harness</span><span><strong>${e(c.max_evaluations)}</strong> candidates / campaign</span><span><strong>${e(c.research_moves)}</strong> research actions / candidate</span><span><strong>${e(c.solver_moves)}</strong> fresh solver actions</span><span><strong>${e(c.max_hours)}h</strong> total launch limit</span></div><p class="comparison-caveat">Fresh solver scores are compared below. Live results are provisional; missing scores stay blank. A failed or cancelled run is not a completed comparison.</p>${data.pairs.map(pair=>{
    const runs=modes.map(m=>pair.runs[m]), complete=runs.every(r=>r?.finalized && !['running','queued','starting','failed','cancelled','unconfirmed'].includes(r.status))
    const row=(label,fn,cls='')=>`<tr class="${cls}"><td>${label}</td>${runs.map(r=>`<td>${r?fn(r):'—'}</td>`).join('')}</tr>`
    const links=r=>`<div class="run-links"><a href="/experiments/avo-lab.html?run=${encodeURIComponent(r.id)}">Trace & replay ↗</a>${r.best_candidate?`<a href="/runs/submission.html?run=${encodeURIComponent(r.id)}">Solver & report ↗</a>`:''}</div>`
    return `<article class="comparison-pair"><header><div><h2>${e(pair.game_id.replace(/^ps_/,'').replace(/-v1$/,'').replaceAll('_',' '))} <small>· attempt ${e(pair.repeat)}</small></h2><p>Player: ${e(pair.model)} · ${e(pair.effort)}</p><p>Optimizer: ${e(c.optimizer_model)} · ${e(c.optimizer_effort)}</p></div><span class="pair-badge ${complete?'done':''}">${complete?'Both finished':'Provisional'}</span></header><table class="comparison-table"><thead><tr><th>${e(pair.id)}</th><th><span class="condition-dot final"></span>Final only</th><th><span class="condition-dot between"></span>Between hypotheses</th></tr></thead><tbody>
    ${row('Best fresh fitness',r=>value(r.best_fitness),'score-row')}
    ${row('Process',r=>`<span class="run-status ${e(r.status)}">${e(r.status)}</span>`)}
    ${row('Game solved',r=>r.solved?'Yes':r.finalized?'No':'Not yet')}
    ${row('Evaluated candidates',r=>`${r.evaluated} / ${e(c.max_evaluations)}`)}
    ${row('First success',r=>r.first_success_evaluation==null?'—':`Evaluation ${r.first_success_evaluation}<small>${duration(r.seconds_to_success)} of search</small>`)}
    ${row('Search time recorded',r=>`${duration(r.search_seconds)}<small>Through latest completed evaluation</small>`)}
    ${row('Research actions used',r=>`${value(r.research_actions)}<small>Completed candidates only</small>`)}
    ${row('Best solver actions',r=>value(r.solver_actions))}
    ${row('Final world model',r=>r.report_available?'Available':r.finalized?'Missing':'Pending')}
    ${row('Finish reason',r=>e(r.finish_reason || '—'))}
    ${row('Inspect',links)}
    </tbody></table><div class="comparison-chart"><h3>Best fitness as the search progresses</h3><p>Candidate evaluation index →</p>${historyChart(pair,c.max_evaluations)}<div class="chart-key"><span><i class="condition-dot final"></i>Final only</span><span><i class="condition-dot between"></i>Between hypotheses</span></div></div></article>`
  }).join('') || '<p>No matched pairs found in this manifest.</p>'}`
}
async function refresh(){
  if(busy)return;busy=true
  const requestedJob=job
  try{
    const listing=await api('/catalog');comparisons=listing.jobs.filter(j=>j.comparison)
    if(job!==requestedJob)return
    get('[data-comparison-select]').innerHTML='<option value="">Choose a comparison</option>'+comparisons.map(j=>`<option value="${e(j.id)}" ${job===j.id?'selected':''}>${e(j.created_at ? new Date(j.created_at).toLocaleString() : j.id)} · ${e(j.status)} · ${j.runs.length/2} pairs</option>`).join('')
    if(job){const data=await api(`/comparison?job=${encodeURIComponent(job)}`);if(job!==requestedJob)return;render(data)}
    else if(comparisons.length)get('[data-comparison-content]').innerHTML=`<div class="comparison-empty"><h2>Choose an experiment above.</h2><p>${comparisons.length} paired launch${comparisons.length===1?' is':'es are'} available to compare.</p></div>`
    else get('[data-comparison-content]').innerHTML=emptyContent
    get('[data-checked]').textContent=`Updated ${new Date().toLocaleTimeString()}`;get('[data-notice]').hidden=true
  }catch(error){if(job===requestedJob){get('[data-notice]').hidden=false;get('[data-notice]').textContent=`${error.message} Displayed results may be stale.`}}
  finally{busy=false;if(job!==requestedJob)refresh()}
}
get('[data-comparison-select]').addEventListener('change',event=>{job=event.target.value;history.replaceState(null,'',job?`?job=${encodeURIComponent(job)}`:location.pathname);refresh()})
get('[data-refresh]').addEventListener('click',refresh)
refresh();setInterval(refresh,10000)
