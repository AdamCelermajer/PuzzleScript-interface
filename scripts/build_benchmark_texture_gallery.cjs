const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const selected = require('../output/game-selection-20/engine-metadata.json');
const output = path.join(root, 'output/game-selection-20/live-texture-gallery');
const publicDir = path.join(root, 'website/public/benchmark-textures');
const api = 'http://127.0.0.1:8000';
async function post(route, body) {
    const res = await fetch(api + route, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!res.ok) throw Error(`${route}: ${res.status} ${await res.text()}`);
    return res.json();
}
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function gridSvg(grid) {
    const size = 44;
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${grid[0].length*size} ${grid.length*size}" role="img" aria-label="Actual numeric ARC frame">` + grid.flatMap((row,y) => row.map((id,x) => `<g><rect x="${x*size}" y="${y*size}" width="44" height="44" fill="hsl(${id*137.508%360} 35% 24%)" stroke="#ffffff55"/><text x="${x*size+22}" y="${y*size+23}" fill="white" font-family="monospace" font-size="16" text-anchor="middle" dominant-baseline="middle">${id}</text></g>`)).join('') + '</svg>';
}
function textureSvg(pixels) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${pixels[0].length} ${pixels.length}" shape-rendering="crispEdges">` + pixels.flatMap((row,y) => row.map(([r,g,b,a],x) => `<rect x="${x}" y="${y}" width="1" height="1" fill="rgba(${r},${g},${b},${a/255})"/>`)).join('') + '</svg>';
}
(async () => {
    fs.mkdirSync(output,{recursive:true}); fs.mkdirSync(publicDir,{recursive:true});
    const card = await post('/api/scorecard/open',{tags:['benchmark-texture-gallery']});
    const captures = [];
    try {
        for (const game of selected) {
            const ordinal = game.id === 'ps_enqueue-v1' ? 11 : 0;
            const rawLevel = game.maps[ordinal].index;
            const observation = await post('/api/cmd/RESET',{card_id:card.card_id,game_id:game.id,level_index:rawLevel});
            const p = observation.projection;
            if(p.mode !== 'visible-cell-v1' || p.max_combinations !== 65536) throw Error('Runtime did not reload: '+game.id);
            const grid = observation.frame.at(-1);
            if(!observation.rendered_frame?.data_url || grid.some(row=>row.length!==grid[0].length)) throw Error('Invalid comparison '+game.id);
            const ids = [...new Set(grid.flat())].sort((a,b)=>a-b);
            if(ids.some(id=>!p.patterns[id])) throw Error('Missing texture '+game.id);
            const capture = {id:game.id,name:game.name,difficulty:game.difficulty,level:ordinal+1,raw_level:rawLevel,ids,observation};
            captures.push(capture);
            fs.writeFileSync(path.join(output,game.id+'.json'),JSON.stringify(capture,null,2));
            fs.writeFileSync(path.join(output,game.id+'.png'),Buffer.from(observation.rendered_frame.data_url.split(',')[1],'base64'));
        }
    } finally { await post('/api/scorecard/close',{card_id:card.card_id}); }
    const cards = captures.map(c=>{
        const grid=c.observation.frame.at(-1);
        return `<article id="${c.id}"><header><div><span class="difficulty">${esc(c.difficulty)}</span><h2>${esc(c.name)}</h2></div><p>Level ${c.level} · ${grid[0].length} × ${grid.length} tiles · ${c.ids.length} visible textures</p></header><div class="pair"><section><h3>Rendered image</h3><img src="${c.observation.rendered_frame.data_url}" alt="${esc(c.name)} rendered level ${c.level}"/></section><section><h3>Actual numeric frame</h3>${gridSvg(grid)}</section></div><details><summary>Texture key — match each number to its visible pixels</summary><div class="key">${c.ids.map(id=>`<div><span>${id}</span>${textureSvg(c.observation.projection.patterns[id])}</div>`).join('')}</div></details></article>`;
    }).join('');
    const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>20 games · visible texture comparison</title><style>
    *{box-sizing:border-box}body{margin:0;background:#edf2f5;color:#173044;font:16px/1.5 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:40px 26px}h1{font-size:38px;letter-spacing:-1px;margin:0 0 12px}h2{margin:3px 0;font-size:26px}h3{font-size:14px;text-transform:uppercase;letter-spacing:1px;color:#546976}.intro{max-width:850px;color:#526778}.badge{display:inline-block;background:#d9ebe4;color:#176449;padding:5px 12px;border-radius:20px;font-weight:650}nav{display:flex;flex-wrap:wrap;gap:7px;margin:25px 0 35px}nav a{color:#315c74;background:white;border:1px solid #d5e0e7;padding:5px 10px;border-radius:7px;text-decoration:none;font-size:13px}article{background:white;border:1px solid #d5e0e7;border-radius:16px;padding:26px;margin-bottom:30px;scroll-margin-top:15px}article header{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #e6edf0;padding-bottom:15px}header p{color:#617587;font-size:14px}.difficulty{font-size:12px;color:#4c7186;text-transform:uppercase;letter-spacing:1px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:30px}.pair section{min-width:0}.pair img,.pair svg{display:block;width:100%;height:auto;image-rendering:pixelated;background:#101820}details{margin-top:22px;border-top:1px solid #e6edf0;padding-top:14px}summary{cursor:pointer;color:#526b7e;font-size:14px}.key{display:flex;flex-wrap:wrap;gap:12px;margin-top:15px}.key div{display:flex;align-items:center;gap:6px;background:#eef3f5;padding:6px;border-radius:5px}.key span{min-width:24px;text-align:center;font-family:monospace}.key svg{width:38px;height:38px;background:#101820}@media(max-width:650px){main{padding:24px 12px}.pair{gap:12px}article{padding:14px}article header{display:block}h1{font-size:29px}}
    </style><main><span class="badge">Live API verified · 20 / 20</span><h1>The same state, two views</h1><p class="intro">Captured from the restarted ARC service. Each number identifies one exact rendered tile texture. Identical pixels share an ID; hidden objects do not produce extra IDs. Grid colors are only a reading aid. IDs are local to each game session.</p><p class="intro">First playable level of each game, except Enqueue: level 12, to show the previously discussed hidden-wall example. All captures use <code>visible-cell-v1</code>, capacity 65,536. No gameplay moves were taken.</p><nav>${captures.map(c=>`<a href="#${c.id}">${esc(c.name)}</a>`).join('')}</nav>${cards}<p class="intro">Captured ${new Date().toISOString()} · PNG and grid taken from the same RESET response.</p></main></html>`;
    fs.writeFileSync(path.join(output,'index.html'),html);
    fs.writeFileSync(path.join(publicDir,'index.html'),html);
    fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(captures.map(({observation,...c})=>({...c,mode:observation.projection.mode,capacity:observation.projection.max_combinations})),null,2));
    console.log(JSON.stringify({games:captures.length,url:'http://127.0.0.1:5173/benchmark-textures/index.html',output}));
})().catch(e=>{console.error(e);process.exitCode=1;});
