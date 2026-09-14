import { api, escapeHtml as e, agentName, providerName } from './runs-shared.js'
const root = document.querySelector('[data-launch]'), form = root.querySelector('form')
const get = s => root.querySelector(s), field = name => form.elements[name]
const notice = get('[data-notice]'), review = get('[data-review]'), dialog = get('[data-model-dialog]')
let kind = new URLSearchParams(location.search).get('approach') === 'codex' ? 'codex' : 'avo'
let games = [], selectedGames = new Set(['ps_modality-v1']), parentRuns = [], reviewed = null, launching = false
let modelRole = 'player', provider = 'codex', modelRequest = 0, catalog = [], modelError = ''
const catalogs = new Map(), details = new Map()
const codexModels = ['gpt-6-astra','gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna','gpt-5.5'].map(id => ({id,name:id,provider:'codex'}))
const savedModels = {player:'gpt-5.6-luna',optimizer:'gpt-6-astra'}
const comparing = () => kind === 'avo' && field('experiment_mode').value === 'compare'
const list = value => value.split(',').map(s => s.trim()).filter(Boolean)
const currentModel = role => field(role === 'player' ? 'models' : 'optimizer_model').value
function modelMarkup(id) {
  const model = details.get(id), p = id.includes('/') ? id.split('/')[0] : 'openai'
  return `<strong>${e(model?.name || id.split('/').slice(p === 'openrouter' ? 1 : -1).join('/'))}</strong><small>${e(providerName(p))}${model?.free ? ' · Free' : ''} · ${e(id)}</small>`
}
function renderModels() {
  if (kind === 'avo' && field('same_model').checked) field('optimizer_model').value = field('models').value
  get('[data-player-model]').innerHTML = modelMarkup(currentModel('player'))
  get('[data-optimizer-model]').innerHTML = modelMarkup(currentModel('optimizer'))
  get('[data-outer-model]').hidden = kind !== 'avo' || field('same_model').checked
  const routerPlayer = kind === 'avo' && currentModel('player').startsWith('openrouter/')
  field('service_tier').disabled = routerPlayer
  if (field('service_tier').disabled) field('service_tier').value = ''
}
function setModels() {
  field('models').value = kind === 'codex' ? 'gpt-5.6-sol' : savedModels.player
  field('optimizer_model').value = savedModels.optimizer
  field('same_model').checked = savedModels.player === savedModels.optimizer
  field('efforts').value = kind === 'avo' ? 'high' : 'low'
  field('optimizer_effort').value = 'low'
  field('service_tier').value = ''
  get('[data-agent-help]').textContent = kind === 'avo' ? 'Codex runs the tools in the AVO sandbox. Choose an OpenAI model using your login, or an OpenRouter model using the project API key.' : 'Uses your existing Codex login.'
  renderModels(); update()
}
function setApproach() {
  root.querySelectorAll('[data-avo]').forEach(el => { el.hidden = kind !== 'avo' })
  root.querySelectorAll('[data-codex]').forEach(el => { el.hidden = kind !== 'codex' })
  field('approach').value = kind
  field('backend_url').value = kind === 'avo' ? 'http://host.docker.internal:8000' : 'http://localhost:8000'
  get('[data-budget-step]').textContent = kind === 'avo' ? '04' : '03'
  setMode(); setModels()
}
function setMode() {
  const compare = comparing()
  get('[data-single-condition]').hidden = compare
  get('[data-comparison-note]').hidden = !compare
  for (const option of field('parallel').options) option.disabled = compare && Number(option.value) % 2 !== 0
  if (compare && Number(field('parallel').value) % 2) field('parallel').value = '2'
  get('[data-parallel-help]').textContent = compare ? 'Pairs start together. Choose 2, 4 or 6 slots.' : 'Separate campaigns, independent workspaces.'
  get('[data-attempt-help]').textContent = compare ? 'Matched pairs per game' : 'Per game & condition'
  update()
}
function configuration() {
  const custom = kind === 'codex' ? list(field('custom_game_ids').value) : []
  const config = {kind, agent_backend:'codex', comparison:comparing(),
    game_ids:custom.length ? custom : [...selectedGames], models:[currentModel('player')], efforts:[field('efforts').value],
    backend_url:field('backend_url').value, repeats:Number(field('repeats').value), parallel:Number(field('parallel').value), max_hours:Number(field('max_hours').value)}
  if (kind === 'avo') Object.assign(config, {optimizer_model:currentModel('optimizer'), optimizer_effort:field('optimizer_effort').value,
    service_tier:field('service_tier').value, world_model_modes:comparing() ? ['final-only','between-hypotheses'] : [field('world_model_mode').value],
    max_evaluations:Number(field('max_evaluations').value), research_moves:Number(field('research_moves').value), solver_moves:Number(field('solver_moves').value)})
  else Object.assign(config,{conditions:[field('conditions').value],max_steps:Number(field('max_steps').value),continue_from:field('continue_from').value})
  return config
}
function update() {
  review.hidden = true; reviewed = null
  const c = configuration(), count = c.game_ids.length * (c.repeats || 0) * (c.comparison ? 2 : 1)
  get('[data-summary-title]').textContent = c.comparison ? 'World-model comparison' : 'Single condition'
  get('[data-summary-count]').textContent = count
  get('[data-summary-unit]').textContent = count === 1 ? 'campaign' : 'campaigns'
  get('[data-summary-description]').textContent = `${c.game_ids.length} game${c.game_ids.length === 1 ? '' : 's'} × ${c.repeats || 0} attempt${c.repeats === 1 ? '' : 's'}${c.comparison ? ' × 2 conditions' : ''}`
  const facts = {Harness:agentName(c.agent_backend),Player:details.get(c.models[0])?.name || c.models[0],
    ...(kind === 'avo' ? {Candidates:c.max_evaluations,'Actions / candidate':c.research_moves} : {'Action budget':c.max_steps}),
    'Launch limit':`${c.max_hours || 0} hours`}
  get('[data-summary-facts]').innerHTML = Object.entries(facts).map(([k,v])=>`<div><dt>${e(k)}</dt><dd>${e(v)}</dd></div>`).join('')
  get('[data-summary-modes]').innerHTML = kind === 'avo' ? c.world_model_modes.map(m=>`<div><span class="condition-dot ${m === 'final-only' ? 'final' : 'between'}"></span>${m === 'final-only' ? 'Final only' : 'Between hypotheses'}</div>`).join('') : ''
  get('[data-summary-capacity]').textContent = c.comparison ? `${Math.min(c.parallel,count)/2} matched pair${Math.min(c.parallel,count) === 2 ? '' : 's'} can run at once.` : `Up to ${Math.min(c.parallel,count)} running at once.`
}
function renderSelectedGames() {
  const title = id => games.find(g=>g.game_id === id)?.title || id
  get('[data-games-summary]').textContent = selectedGames.size ? `${selectedGames.size} selected · ${[...selectedGames].slice(0,2).map(title).join(', ')}${selectedGames.size > 2 ? '…' : ''}` : 'Choose games'
  get('[data-selected-games]').innerHTML = [...selectedGames].map(id=>`<button type="button" data-remove-game="${e(id)}" aria-label="Remove ${e(title(id))}">${e(title(id))} ×</button>`).join('')
}
function renderGames() {
  const needle = get('[data-game-search]').value.trim().toLowerCase()
  const filtered = games.filter(g=>`${g.title} ${g.game_id}`.toLowerCase().includes(needle))
  get('[data-game-options]').innerHTML = filtered.map(g=>`<label><input type="checkbox" data-game="${e(g.game_id)}" ${selectedGames.has(g.game_id)?'checked':''}>${e(g.title || g.game_id)}</label>`).join('') || '<p class="field-note">No matching games.</p>'
  renderSelectedGames()
}
form.addEventListener('change', event => {
  const el = event.target
  if (el.name === 'approach') { kind = el.value; setApproach() }
  else if (el.name === 'experiment_mode') setMode()
  else if (el.name === 'same_model') { if(!el.checked) field('optimizer_model').value=savedModels.optimizer; renderModels(); update() }
  else if (el.dataset.game) { el.checked ? selectedGames.add(el.dataset.game) : selectedGames.delete(el.dataset.game); renderSelectedGames(); update() }
  else update()
})
form.addEventListener('input', update)
get('[data-game-search]').addEventListener('input', renderGames)
get('[data-selected-games]').addEventListener('click', event => {const b=event.target.closest('[data-remove-game]');if(b){selectedGames.delete(b.dataset.removeGame);renderGames();update()}})
function renderModelList() {
  const needle=get('[data-model-search]').value.trim().toLowerCase(), free=get('[data-free-only]').checked
  const models=catalog.filter(m=>(!free || provider!=='openrouter' || m.free) && `${m.name} ${m.id}`.toLowerCase().includes(needle))
  get('[data-model-status]').textContent = modelError || `${models.length} models${provider === 'openrouter' ? ' with tool support' : ''}`
  get('[data-model-results]').innerHTML = models.map(m=>`<button type="button" class="model-option" data-select-model="${e(m.id)}" aria-pressed="${m.id === currentModel(modelRole)}"><span><strong>${e(m.name)}</strong><small>${e(m.id)}${m.context ? ` · ${Math.round(m.context/1000)}k context` : ''}</small></span><span class="model-price">${m.free ? '<span class="free-badge">Free</span>' : m.input_price != null ? `$${e(m.input_price.toFixed(2))} / $${e(m.output_price?.toFixed(2) ?? '—')}<small>in / out · per 1M tokens</small>` : 'Select →'}</span></button>`).join('') || `<p class="run-empty">${e(modelError || 'No models match this search.')}</p>`
}
async function loadModels(refresh=false) {
  const request=++modelRequest, selectedProvider=provider
  modelError=''; catalog=[]; get('[data-model-status]').textContent='Loading model catalog…';get('[data-model-results]').innerHTML='<p class="run-empty">Loading models…</p>'
  root.querySelectorAll('[data-provider]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.provider===provider));b.hidden = kind!=='avo' && b.dataset.provider==='openrouter'})
  get('[data-free-filter]').hidden=provider!=='openrouter'
  get('[data-model-note]').textContent=provider==='openrouter' ? 'OpenRouter through Codex. DeepSeek V4.1 Flash passed our sandbox and tool test; other listed models need compatibility testing. Prices are USD per million tokens.' : 'OpenAI models available through your Codex login. You can also enter a model ID.'
  get('[data-manual-model]').placeholder=provider==='openrouter' ? 'deepseek/deepseek-v4.1-flash' : 'gpt-5.6-sol'
  try {
    const data = provider==='codex' ? {models:codexModels} : !refresh && catalogs.has(provider) ? catalogs.get(provider) : await api(`/model-catalog?provider=${provider}`)
    if(request!==modelRequest || selectedProvider!==provider) return
    catalogs.set(provider,data);catalog=data.models;modelError=data.warning || ''
    for(const model of catalog) details.set(model.id,model)
    renderModelList()
  } catch(error) {if(request===modelRequest){modelError=error.message;renderModelList()}}
}
function chooseModel(id) {
  field(modelRole==='player'?'models':'optimizer_model').value=id
  savedModels[modelRole]=id
  if(modelRole==='player' && field('same_model').checked) savedModels.optimizer=id
  renderModels();update();dialog.close()
}
root.querySelectorAll('[data-pick-model]').forEach(b=>b.addEventListener('click',()=>{
  modelRole=b.dataset.pickModel;provider=kind==='avo' && currentModel(modelRole).startsWith('openrouter/') ? 'openrouter' : 'codex'
  get('#model-dialog-title').textContent=`Choose ${modelRole==='player'?'a player':'an optimizer'} model`
  get('[data-model-search]').value='';get('[data-free-only]').checked=false;get('[data-manual-model]').value=''
  dialog.showModal();get('[data-model-search]').focus();loadModels()
}))
get('[data-close-model]').addEventListener('click',()=>dialog.close())
root.querySelectorAll('[data-provider]').forEach(b=>b.addEventListener('click',()=>{provider=b.dataset.provider;get('[data-model-search]').value='';get('[data-free-only]').checked=false;loadModels()}))
get('[data-model-search]').addEventListener('input',renderModelList)
get('[data-free-only]').addEventListener('change',renderModelList)
get('[data-retry-models]').addEventListener('click',()=>loadModels(true))
get('[data-model-results]').addEventListener('click',event=>{const b=event.target.closest('[data-select-model]');if(b)chooseModel(b.dataset.selectModel)})
get('[data-use-manual]').addEventListener('click',()=>{
  let id=get('[data-manual-model]').value.trim()
  if(!/^[a-zA-Z0-9][a-zA-Z0-9._/:-]{0,159}$/.test(id)){get('[data-model-status]').textContent='Enter a valid model ID.';return}
  if(provider==='openrouter' && !id.startsWith('openrouter/')) id='openrouter/'+id
  if(id.length>160){get('[data-model-status]').textContent='Model ID is too long.';return}
  chooseModel(id)
})
form.addEventListener('submit',async event=>{
  event.preventDefault();notice.hidden=true
  try {
    const config=configuration(), result=await api('/experiments/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)})
    reviewed=JSON.stringify(config)
    get('[data-review-summary]').textContent=`${result.count} campaigns · ${result.parallel} concurrent slots · ${result.max_hours} hours total${result.comparison ? ' · matched pairs start together' : ''}`
    const groups=new Map()
    result.campaigns.forEach((c,i)=>{const key=c.pair_id || i;groups.set(key,[...(groups.get(key)||[]),c])})
    get('[data-campaign-plan]').innerHTML=[...groups.values()].map(rows=>{const c=rows[0];return `<div class="review-pair"><strong>${e(games.find(g=>g.game_id===c.game_id)?.title || c.game_id)} · attempt ${e(c.repeat)}</strong><p>${e(agentName(c.agent_backend))} · ${e(c.model)}${c.optimizer_model ? ` · outer: ${e(c.optimizer_model)}` : ''}</p><div class="review-conditions">${rows.map(r=>`<span>${e(r.world_model_mode==='final-only'?'Final only':r.world_model_mode==='between-hypotheses'?'Between hypotheses':r.condition)}</span>`).join('')}${rows.length===2?'<span>Start together</span>':''}</div></div>`}).join('')
    get('[data-commands]').textContent=result.commands.map(args=>args.map(a=>JSON.stringify(a)).join(' ')).join('\n\n')
    get('[data-launch-button]').textContent=result.comparison ? 'Launch comparison →' : 'Launch experiment →'
    review.hidden=false;review.scrollIntoView({behavior:'smooth',block:'center'})
  }catch(error){notice.hidden=false;notice.textContent=error.message;notice.scrollIntoView({behavior:'smooth',block:'center'})}
})
get('[data-launch-button]').addEventListener('click',async event=>{
  if(launching || !reviewed || JSON.stringify(configuration())!==reviewed)return
  launching=true;event.target.disabled=true
  try{const result=await api('/experiments',{method:'POST',headers:{'Content-Type':'application/json'},body:reviewed});window.location.assign(comparing()?`/runs/compare.html?job=${encodeURIComponent(result.id)}`:'/')}
  catch(error){notice.hidden=false;notice.textContent=error.message;event.target.disabled=false;launching=false}
})
field('continue_from').addEventListener('change',()=>{
  const parent=parentRuns.find(r=>r.id===field('continue_from').value);if(!parent)return
  const c=parent.config;field('models').value=c.model;field('efforts').value=c.reasoning_effort || 'low'
  field('repeats').value=1;field('parallel').value='1';field('conditions').value=c.condition;field('custom_game_ids').value=''
  if(!games.some(g=>g.game_id===c.game_id))games.push({game_id:c.game_id,title:c.game_id})
  selectedGames=new Set([c.game_id]);if(c.backend_url)field('backend_url').value=c.backend_url
  renderModels();renderGames();update()
})
if(new URLSearchParams(location.search).get('comparison')==='1')field('experiment_mode').value='compare'
setApproach()
async function initialize(){
  const results=await Promise.allSettled([api('/games'),api('/catalog')])
  if(results[0].status==='fulfilled'){
    games=results[0].value.games.map(g=>({game_id:g.game_id || g.id,title:g.title || g.name || g.game_id}))
    if(games.length && !games.some(g=>selectedGames.has(g.game_id)))selectedGames=new Set([games[0].game_id])
    renderGames();update()
  }else{get('[data-games-summary]').textContent='Game catalog unavailable';notice.hidden=false;notice.textContent=results[0].reason.message}
  if(results[1].status==='fulfilled'){parentRuns=results[1].value.runs.filter(r=>r.can_continue);field('continue_from').innerHTML='<option value="">Start fresh</option>'+parentRuns.map(r=>`<option value="${e(r.id)}">${e(r.game_id)} · ${e(r.model)} · ${e(r.id)}</option>`).join('')}
}
initialize()
