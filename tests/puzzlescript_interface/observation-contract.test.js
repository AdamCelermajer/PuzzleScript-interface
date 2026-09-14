const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const {createSessionFromSource, loadGameSourceByName, executeAction, renderSessionFrame} = require('../../puzzlescript_interface/runtime/server');
const quiet = {silent: true};
const make = (name, level=0) => createSessionFromSource(loadGameSourceByName(name), level).session;
test('visual encoding is global, including arbitrary submitted titles', () => {
    const source = loadGameSourceByName('ps_sokoban_basic-v1').replace(/^title .*$/mi, 'title Arbitrary unlisted research game');
    const s = createSessionFromSource(source, 0).session;
    assert.equal(s.projectionCompression.mode, 'visible-cell-v1');
    assert.deepEqual(s.projectionCompression.cell_encoding.shape, [1, 1]);
    assert.equal(s.projectionCompression.max_combinations, 65536);
    assert.equal(s.renderIntGrid().length, s.engine.getCurrentLevelCells().length);
});
test('legacy encoding is explicit and unknown configuration fails', () => {
    const {spawnSync} = require('node:child_process');
    const entry = require.resolve('../../puzzlescript_interface/runtime/server');
    const script = `const r=require(${JSON.stringify(entry)}); const s=r.createSessionFromSource(r.loadGameSourceByName('ps_sokoban_basic-v1'),0).session; console.log(JSON.stringify(s.projectionCompression.cell_encoding.shape));`;
    const legacy = spawnSync(process.execPath, ['-e', script], {encoding:'utf8', env:{...process.env, PUZZLESCRIPT_GRID_ENCODING:'visible-cell-hex-v2'}});
    assert.equal(legacy.status, 0, legacy.stderr);
    assert.match(legacy.stdout, /\[2,2\]/);
    const invalid = spawnSync(process.execPath, ['-e', script], {encoding:'utf8', env:{...process.env, PUZZLESCRIPT_GRID_ENCODING:'typo'}});
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stderr, /Unsupported PUZZLESCRIPT_GRID_ENCODING/);
});
function decode(grid) {
    return Array.from({length:grid.length/2}, (_, y) =>
        Array.from({length:grid[0].length/2}, (_, x) =>
            grid[2*y][2*x]*4096+grid[2*y][2*x+1]*256+grid[2*y+1][2*x]*16+grid[2*y+1][2*x+1]));
}
function pngPixels(frame) {
    const b = Buffer.from(frame.data_url.split(',')[1], 'base64');
    const chunks=[];
    for(let p=8;p<b.length;) {
        const n=b.readUInt32BE(p);
        if(b.toString('ascii',p+4,p+8)==='IDAT')chunks.push(b.subarray(p+8,p+8+n));
        p+=12+n;
    }
    const raw=zlib.inflateSync(Buffer.concat(chunks));
    const stride=frame.width*4+1;
    return (x,y)=>Array.from(raw.subarray(y*stride+1+x*4,y*stride+1+x*4+4));
}
test('lossless ARC blocks retain more than 16 patterns and reconstruct the PNG', async()=>{
    const s=make('ps_purple-v1');
    s.projectionCompression.mode='visible-cell-hex-v2';
    const keys={W:1,S:2,A:3,D:4};
    for(const key of 'WWWDWADDWWASWWAASDSWAASDASSSSDSDDW')
        await executeAction(s,'ACTION'+keys[key],quiet);
    const grid=s.renderIntGrid(), ids=decode(grid), png=renderSessionFrame(s);
    assert.ok(s.visualSignatureToInt.size>16);
    assert.ok(grid.flat().every(v=>Number.isInteger(v)&&v>=0&&v<16));
    assert.equal(s.projectionCompression.compressed,false);
    const pixel=pngPixels(png), tw=png.width/ids[0].length, th=png.height/ids.length;
    for(let y=0;y<ids.length;y++)for(let x=0;x<ids[y].length;x++) {
        const pattern=s.visualPatterns[ids[y][x]];
        for(let py=0;py<pattern.length;py++)for(let px=0;px<pattern[py].length;px++)
            assert.deepEqual(pixel(x*tw+px*tw/pattern[py].length,y*th+py*th/pattern.length),pattern[py][px]);
    }
});
for (const name of ['midas', 'purple', 'enqueue']) {
    test(`${name}: tile IDs depend only on rendered pixels`, () => {
        const s=make(`ps_${name}-v1`);
        const grid=s.renderIntGrid(),png=renderSessionFrame(s),pixel=pngPixels(png);
        assert.equal(s.projectionCompression.mode,'visible-cell-v1');
        const textures=new Map(), tw=png.width/grid[0].length, th=png.height/grid.length;
        for(let y=0;y<grid.length;y++)for(let x=0;x<grid[y].length;x++) {
            const pattern=s.visualPatterns[grid[y][x]];
            const actual=[];
            for(let py=0;py<pattern.length;py++)for(let px=0;px<pattern[py].length;px++) {
                const rgba=pixel(x*tw+px*tw/pattern[py].length,y*th+py*th/pattern.length);
                assert.deepEqual(rgba,pattern[py][px]);actual.push(rgba);
            }
            const signature=JSON.stringify(actual);
            if(textures.has(signature))assert.equal(grid[y][x],textures.get(signature));
            else textures.set(signature,grid[y][x]);
        }
        assert.equal(new Set(textures.values()).size,textures.size);
        assert.deepEqual(s.renderIntGrid(),grid);
        assert.ok(Object.values(s.intToName).every(name=>name.startsWith('Visible texture')));
    });
}
test('Enqueue merges invisible wall markers and invisible floor markers',()=>{
    const s=make('ps_enqueue-v1');const grid=s.renderIntGrid();
    const groups=new Map();
    s.engine.getCurrentLevelCells().forEach((row,y)=>row.forEach((cell,x)=>{
        const id=grid[y][x];if(!groups.has(id))groups.set(id,new Set());
        groups.get(id).add(cell.getSprites().map(sprite=>sprite.getName()).sort().join('+'));
    }));
    assert.ok([...groups.values()].filter(g=>g.size>1).length>=2);
});
test('texture IDs survive RESET and overflow never merges textures',async()=>{
    const s=make('ps_midas-v1'),initial=s.renderIntGrid();
    await executeAction(s,'ACTION1',quiet);await executeAction(s,'RESET',quiet);
    assert.deepEqual(s.renderIntGrid(),initial);
    const capped=make('ps_midas-v1');capped.visualSignatureToInt.clear();
    capped.projectionCompression.max_combinations=1;
    assert.throws(()=>capped.renderIntGrid(),/refusing to merge/);
});

test('ragged source maps fail explicitly for both observation surfaces', () => {
    const s = make('ps_mc_escher_s_equestrian_armageddon-v1', 3);
    assert.throws(() => s.renderIntGrid(), /Unsupported ragged level/);
    assert.throws(() => renderSessionFrame(s), /Unsupported ragged level/);
});

test('leading messages do not create blank resets or consume a gameplay action', async()=>{
    const s=make('ps_purple-v1'), direct=make('ps_purple-v1',2);
    assert.equal(s.engine.currentLevelNum,2);
    assert.deepEqual(s.renderIntGrid(),direct.renderIntGrid());
    const a=await executeAction(s,'ACTION1',quiet), b=await executeAction(direct,'ACTION1',quiet);
    assert.deepEqual(a.frame,b.frame);
    assert.ok(a.rendered_frame);
});
test('Atlas Shrank uses its 18x11 viewport for both PNG and grid',()=>{
    const s=make('ps_atlas_shrank-v1',16);
    const grid=s.renderIntGrid(),png=renderSessionFrame(s);
    assert.equal(s.engine.getCurrentLevelCells()[0].length,72);
    assert.equal(grid.length,11);assert.equal(grid[0].length,18);
    assert.equal(png.width,810);assert.equal(png.height,495);
});
for(const [name,index] of [['mowing',6],['magnetic',7],['icecrates',11]]) {
    test(`${name}: solving last map immediately reports WIN and all levels`,async()=>{
        const s=make(`ps_${name}-v1`,index);
        const recording=JSON.parse(fs.readFileSync(path.resolve(__dirname,`../../node_modules/puzzlescript/game-solutions/${name}.json`))).solutions[index].solution;
        const keys={W:1,S:2,A:3,D:4,X:5};let result;
        for(const c of recording)if(keys[c]) {
            result=await executeAction(s,'ACTION'+keys[c],quiet);
            if(result.state==='WIN')break;
        }
        assert.equal(result.state,'WIN');
        assert.equal(result.levels_completed,s.winLevels);
        assert.ok(result.frame.at(-1).length);
        assert.equal(s.completedLevels(),s.winLevels);
        const reset=await executeAction(s,'RESET',quiet);
        assert.equal(reset.state,'PLAYING');
        assert.equal(reset.levels_completed,s.winLevels-1);
        assert.equal(s.engine.currentLevelNum,index);
        assert.ok(reset.frame.at(-1).length);
    });
}
