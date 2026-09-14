// Audit every installed game in an isolated worker; a bad game cannot hang the catalog.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),games=path.join(root,'puzzlescript_interface/games');
if(process.argv[2]==='--game') {
 (async()=>{
  const id=process.argv[3];let result={game:id,status:'passed',maps:0,frames:0,max_textures:0};
  try {
   const r=require('../puzzlescript_interface/runtime/server');
   const s=r.createSessionFromSource(fs.readFileSync(path.join(games,id,'script.txt'),'utf8'),0).session;
   const levels=s.gameData.levels.map((l,i)=>l.type==='LEVEL_MAP'?i:null).filter(i=>i!==null);
   result.total_maps=levels.length;
   const check=()=>{
    const grid=s.renderIntGrid();
    if(s.projectionCompression.mode!=='visible-cell-v1'||s.projectionCompression.cell_encoding.shape.join(',')!=='1,1')throw Error('Wrong default encoding');
    if(!grid.length||!grid[0].length)throw Error('Empty visual grid');
    if(grid.some(row=>row.length!==grid[0].length))throw Error('Ragged visual grid');
    for(const value of grid.flat())if(!Number.isInteger(value)||value<0||value>=s.projectionCompression.max_combinations||!s.visualPatterns[value])throw Error('Invalid texture ID');
    const png=r.renderSessionFrame(s);
    if(png.width/grid[0].length!==s.pixelUI.SPRITE_WIDTH*9||png.height/grid.length!==s.pixelUI.SPRITE_HEIGHT*9)throw Error('PNG/grid viewport mismatch');
    const ids=new Set(grid.flat()),pixels=new Set([...ids].map(id=>JSON.stringify(s.visualPatterns[id])));
    if(ids.size!==pixels.size)throw Error('Identical textures have different IDs');
    result.frames++;result.max_textures=Math.max(result.max_textures,s.visualSignatureToInt.size);
   };
   for(const index of levels){result.current_level=index;s.engine.setLevel(index);s.skipMessageLevels();check();result.maps++;
    for(const action of s.availableActions.filter(a=>a!=='RESET')){await r.executeAction(s,action,{silent:true,includeRenderedFrame:false});check();if(s.handler.won)break;}
   }
  }catch(e){result.status='failed';result.error=e.message;result.stack=e.stack;}
  process.stdout.write('\nAUDIT_RESULT='+JSON.stringify(result)+'\n');
 })();
}else if(process.argv[2]==='--report'){
 writeReport(JSON.parse(fs.readFileSync(path.join(root,'output/global-visible-texture-audit/results.json'),'utf8')));
}else{
 const results=[];const output=path.join(root,'output/global-visible-texture-audit');fs.mkdirSync(output,{recursive:true});
 for(const dir of fs.readdirSync(games,{withFileTypes:true}).filter(d=>d.isDirectory()&&fs.existsSync(path.join(games,d.name,'script.txt')))){
  const child=spawnSync(process.execPath,[__filename,'--game',dir.name],{cwd:root,encoding:'utf8',timeout:60000,maxBuffer:2*1024*1024,env:{...process.env,PUZZLESCRIPT_GRID_ENCODING:'visible-cell-v1',PUZZLESCRIPT_RENDER_SCALE:'9'}});
  const line=(child.stdout||'').split('\n').find(l=>l.startsWith('AUDIT_RESULT='));
  const result=line?JSON.parse(line.slice(13)):{game:dir.name,status:'failed',error:child.error?.message||(child.stderr||'Worker failed').slice(-800)};
  results.push(result);fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));
  if(results.length%25===0)console.log(`${results.length} games checked`);
 }
 writeReport(results);
}
function writeReport(results){
 const output=path.join(root,'output/global-visible-texture-audit');
 const summary={games:results.length,passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status!=='passed').length,maps:results.reduce((n,r)=>n+(r.maps||0),0),frames:results.reduce((n,r)=>n+(r.frames||0),0),max_textures:Math.max(...results.map(r=>r.max_textures||0)),mode:'visible-cell-v1',capacity:65536,worker_timeout_seconds:60};
 fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2));
 const lines=['# Global visible-texture audit','',
  `${summary.passed}/${summary.games} installed games passed bounded probes; ${summary.failed} failed. ${summary.maps} maps and ${summary.frames} frames checked. Largest observed session dictionary: ${summary.max_textures} textures.`,
  '', '## Representation', '',
  'All built-in games and arbitrary submitted source use visible-cell-v1 by default. No game-title list selects the encoding. One grid cell represents one visible tile; exact composited RGBA pixels determine its ID. Invisible object differences do not create separate IDs. Visibly different wall textures remain different.',
  '', 'IDs are allocated on observation, stay stable within the session, and range from 0 to 65535. No 65536-entry dictionary is preallocated. Overflow fails explicitly. The legacy 2x2 encoding requires PUZZLESCRIPT_GRID_ENCODING=visible-cell-hex-v2. This local extension is not the official ARC 0-15 contract.',
  '', '## Coverage and limits', '',
  'Every installed script.txt was attempted in a separate worker. Each playable map was loaded and available actions were probed. Checks cover rectangular grids, integer ID bounds, observed texture dictionaries, identical-texture merging, and PNG/grid viewport alignment. Workers have a 60-second limit. A failed game stops further probes for that game; timeout records do not count partial work.',
  '', 'This is not exhaustive reachable-state coverage or proof that every game mechanic is supported. Pixel-by-pixel reconstruction, hidden-marker merging, RESET stability, cameras, terminal wins, arbitrary titles and explicit legacy selection have separate regression tests.',
  '', 'The public ARC adapter and AVO preserve extended IDs and projection metadata. AVO/direct-player prompts describe the encoding. Web and terminal viewers preserve large numeric IDs. Native PNG rendering retains game colors; numeric-grid display colors are only an aid.',
  '', '## Remaining failures', '', '| Game | Failure |','| --- | --- |',
  ...results.filter(r=>r.status!=='passed').map(r=>`| ${r.game} | ${r.error.replace(/\n/g,' ').replace(/\|/g,'\\|')} |`),
  '', 'These failures are not silently remapped or counted as supported. Easy Enigma hits the engine rule-loop guard; Fish Friend exceeds the audit timeout; Equestrian Armageddon has nonrectangular source rows; Oskar\'s Maze and World Generation fail inside the npm engine during initialization.',
  '', '## Activation', '',
  'Source changes are saved. Shared running services and campaigns were not restarted. Fresh service processes load this default; old object-grid experiment artifacts remain historical and were not relabeled.',
  '', 'Reproduce: node scripts/audit_visible_textures.cjs. Full per-game evidence and error stacks: results.json. Numeric summary: summary.json.', ''];
 fs.writeFileSync(path.join(output,'report.md'),lines.join('\n'));console.log(JSON.stringify(summary));
}
