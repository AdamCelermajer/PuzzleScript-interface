"""Draw the rule-learning figures from curves-combined.json: the interactive rule-learning.html and, through
headless Chrome, rule-learning-{knightoban,icecrates,modality}.png. Solid line = combined grade (notebook +
thinking); faint dashed line = the earlier notebook-only grade (curves.json).

Run from the repo root: uv run python docs/research/rule-learning-20261028/figures.py
"""
import json, os, subprocess, tempfile

here = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
data = json.load(open(f"{here}/curves-combined.json", encoding="utf-8"))
KEEP = ("actions", "tool_calls", "gen_tokens")
DATA = {}
for run, r in data.items():
    pts = [{**{k: c[k] for k in KEEP}, "score": c["score"], "levels": c["levels"]} for c in r["checkpoints"]]
    lv = []
    for lu in r["levelups"]:  # the checkpoint taken at the level-up carries the belief at that moment
        c = next(c for c in r["checkpoints"] if f"level {lu['level']} completed" in c["why"])
        lv.append({**{k: lu[k] for k in KEEP}, "level": lu["level"], "score": c["score"]})
    DATA.setdefault(r["game"], {})[r["driver"]] = {
        "points": pts, "old": r["old_notebook_curve"], "levelups": lv,
        "totals": {k: r["totals"][k] for k in KEEP + ("levels",)}, "final": r["checkpoints"][-1]["belief"]}

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Rule learning, 21 Oct runs</title>
<style>
:root{--agent:var(--chart-1,#2a78d6);--turn:var(--chart-2,#eb6834);--gridc:color-mix(in srgb,var(--foreground,#0b0b0b) 10%,transparent);--axisc:color-mix(in srgb,var(--foreground,#0b0b0b) 25%,transparent)}
*{box-sizing:border-box}body{margin:0;font-family:var(--font-sans,system-ui,sans-serif);font-size:13px;line-height:1.45}
.sub{color:var(--muted-foreground,#52514e);margin:0 0 10px}
.bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.seg{display:inline-flex;border:1px solid var(--border,#ddd);border-radius:var(--radius,8px);overflow:hidden}
.seg button{border:0;background:none;padding:5px 10px;font:inherit;color:var(--muted-foreground,#52514e);cursor:pointer}
.seg button.on{background:var(--primary,#111);color:var(--primary-foreground,#fff)}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted-foreground,#52514e);font-size:12px}
.legend i{display:inline-block;width:16px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.legend i.dash{height:0;border-top:2px dashed var(--muted-foreground,#888);border-radius:0;opacity:.7}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--muted-foreground,#888);vertical-align:middle;margin-right:5px}
.game{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:14px;align-items:start;background:var(--card,transparent);border:1px solid var(--border,#e5e5e5);border-radius:var(--radius,10px);padding:16px;margin-bottom:12px}
.game h2{font-size:14px;margin:0}.what{color:var(--muted-foreground,#888);font-size:11.5px;margin:1px 0 4px}
svg{display:block;width:100%;height:auto;overflow:visible}
.tip{position:fixed;pointer-events:none;background:var(--popover,#fff);color:var(--popover-foreground,#111);border:1px solid var(--border,#ccc);border-radius:8px;padding:6px 8px;font-size:12px;display:none;z-index:9}
table{width:100%;border-collapse:collapse;font-size:11.5px}th,td{padding:3px 3px;border-top:1px solid var(--border,#eee);text-align:left;vertical-align:top}
th{color:var(--muted-foreground,#888);font-weight:500}td.g{text-align:center;width:52px;white-space:nowrap}.hid{color:var(--muted-foreground,#888);font-size:10.5px}
/*STATIC*/
</style></head><body>
/*HEAD*/
<div id="charts"></div><div class="tip" id="tip"></div>
<script>
const DATA=/*DATA*/;const ONLY=/*ONLY*/;
const GAMES=[["ps_modality-v1","Modality","Sokoban where floor colour limits where you can walk",4],["ps_icecrates-v1","IceCrates","ice: you slide until you hit something",6],["ps_knightoban-v1","Knightoban","red boxes jump like a chess knight",6]].filter(g=>!ONLY||g[0]===ONLY);
const RULES={M1:"Controls (4 moves)",M2:"Walking into a box pushes it",M3:"Box can't go into a box or off the grid",M4:"Floor colour blocks the player",M5:"Grey tiles connect both colours",M6:"Pushing also depends on floor colour",M7:"The box ignores floor colour",M8:"Win: every box on a target",
I1:"Controls (4 moves)",I2:"Ice: you keep sliding",I3:"Sliding into a box pushes it",I4:"Pushed boxes push other boxes",I5:"Water blocks the player",I6:"A box pushed into water fills it",I7:"Win: stop on the goal",
K1:"Controls (4 moves + action)",K2:"Walls; orange boxes push normally",K3:"Red boxes jump like a knight",K4:"Landing cell must be empty",K5:"Landing cells shown to choose from",K6:"Action button confirms the jump",K7:"Win: every target covered"};
const HIDDEN=new Set(["M4","M5","M6","M7","I4","I6","I7","K3","K4","K5","K6"]);
const MARK=ONLY?{correct:"✓",partial:"½",wrong:"✗",absent:"–"}:{correct:"✓",partial:"½",wrong:"✗ wrong",absent:"–"};
const COL={agent:"var(--agent)",controller:"var(--turn)"};const NAME={agent:"agent-driven",controller:"turn-based"};
const LAB={actions:"game moves",gen_tokens:"tokens the model wrote (output + thinking)",tool_calls:"tool calls"};
let X="actions";const tip=document.getElementById("tip");
const fmt=v=>X==="gen_tokens"?(v>=1000?Math.round(v/1000)+"k":Math.round(v)):Math.round(v);
function step(pts,sx,sy,end){let p=`M${sx(0)},${sy(0)}`,last=0;for(const q of pts){p+=` H${sx(q[X])} V${sy(q.score)}`;last=q.score}return [p+` H${sx(end)}`,last]}
function draw(){const root=document.getElementById("charts");root.innerHTML="";
for(const [g,title,what,nlev] of GAMES){const runs=DATA[g];const W=420,H=230,L=34,R=62,T=8,B=32;
 const xmax=Math.max(...Object.values(runs).map(r=>r.totals[X]))*1.02;
 const sx=v=>L+(W-L-R)*v/xmax, sy=v=>T+(H-T-B)*(1-v/100);
 let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}">`;
 for(const y of [0,25,50,75,100]) s+=`<line x1="${L}" x2="${W-R}" y1="${sy(y)}" y2="${sy(y)}" stroke="var(--gridc)"/><text x="${L-5}" y="${sy(y)+3.5}" font-size="10" fill="currentColor" opacity=".55" text-anchor="end">${y}%</text>`;
 for(let i=0;i<=4;i++){const v=xmax*i/4;s+=`<text x="${sx(v)}" y="${H-B+14}" font-size="10" fill="currentColor" opacity=".55" text-anchor="middle">${fmt(v)}</text>`}
 s+=`<line x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--axisc)"/><text x="${(L+W-R)/2}" y="${H-2}" font-size="10.5" fill="currentColor" opacity=".75" text-anchor="middle">${LAB[X]}</text>`;
 const ends=[];
 for(const d of ["controller","agent"]){const r=runs[d];const [op]=step(r.old,sx,sy,r.totals[X]);
  s+=`<path d="${op}" fill="none" stroke="${COL[d]}" stroke-width="1.6" stroke-dasharray="4 3" opacity=".42" stroke-linejoin="round"/>`}
 for(const d of ["controller","agent"]){const r=runs[d];const [path,prev]=step(r.points,sx,sy,r.totals[X]);
  s+=`<path d="${path}" fill="none" stroke="${COL[d]}" stroke-width="2.2" stroke-linejoin="round"/>`;
  for(const p of r.points) s+=`<circle cx="${sx(p[X])}" cy="${sy(p.score)}" r="8" fill="transparent" data-tip="<b>${NAME[d]}</b>: ${p.score}% of rules believed right (notes + thinking)<br>at move ${p.actions} · ${Math.round(p.gen_tokens/1000)}k tokens · ${p.tool_calls} tool calls"/>`;
  for(const p of r.old) s+=`<circle cx="${sx(p[X])}" cy="${sy(p.score)}" r="6" fill="transparent" data-tip="<b>${NAME[d]}</b>, notes only (earlier grading): ${p.score}%<br>at move ${p.actions}"/>`;
  for(const lu of r.levelups) s+=`<circle cx="${sx(lu[X])}" cy="${sy(lu.score)}" r="4.5" fill="${COL[d]}" stroke="var(--background,#fff)" stroke-width="2" data-tip="<b>${NAME[d]}</b>: level ${lu.level} completed at move ${lu.actions}"/>`;
  ends.push({y:sy(prev),x:sx(r.totals[X]),txt:`${r.totals.levels}/${nlev} levels`,c:COL[d]});}
 ends.sort((a,b)=>a.y-b.y);for(let i=1;i<ends.length;i++) if(ends[i].y-ends[i-1].y<13) ends[i].y=ends[i-1].y+13;
 for(const e of ends) s+=ONLY?`<text x="${e.x+5}" y="${e.y+4}" font-size="12" font-weight="600" fill="${e.c}">${e.txt}</text>`:`<text x="${e.x+5}" y="${e.y+4}" font-size="11" fill="currentColor" opacity=".8">${e.txt}</text>`;
 s+=`</svg>`;
 let t=`<table><tr><th>${ONLY?"Final belief, rule by rule":"rule"}</th><th class="ca" style="text-align:center">agent</th><th class="ct" style="text-align:center">turn</th></tr>`;
 for(const id of Object.keys(runs.agent.final)) t+=`<tr><td>${RULES[id]}${HIDDEN.has(id)?' <span class="hid">hidden</span>':''}</td><td class="g">${MARK[runs.agent.final[id]]}</td><td class="g">${MARK[runs.controller.final[id]]}</td></tr>`;
 t+=`</table>`;
 const c=document.createElement("div");c.className="game";
 c.innerHTML=ONLY?`<div>${s}</div><div>${t}</div>`:`<div><h2>${title}</h2><div class="what">${what}</div>${s}</div><div><div class="what">Final belief (notes + thinking), rule by rule</div>${t}</div>`;root.appendChild(c);}
 document.querySelectorAll("[data-tip]").forEach(el=>{el.addEventListener("mousemove",e=>{tip.innerHTML=el.dataset.tip;tip.style.display="block";tip.style.left=(e.clientX+12)+"px";tip.style.top=(e.clientY+12)+"px"});el.addEventListener("mouseleave",()=>tip.style.display="none")});}
document.querySelectorAll("#xs button").forEach(b=>b.onclick=()=>{X=b.dataset.x;document.querySelectorAll("#xs button").forEach(o=>o.classList.toggle("on",o===b));draw()});
draw();
</script></body></html>"""

HEAD = """<p class="sub">At every rewrite of its <code>world_model.md</code>, every 25 moves and every level, a grader read the notes and the thinking written since the last check and marked each of the game's real rules (right = 1, half = ½, missing or wrong = 0); a belief stays until the model drops it. Solid line = share of rules the model believes right, from notes and thinking; faint dashed line = the earlier grade from the notes alone. Qwen 3.8 27B 8-bit, OpenCode, 21 Oct, one run per line.</p>
<div class="bar"><div class="seg" id="xs"><button data-x="actions" class="on">game moves</button><button data-x="gen_tokens">tokens written</button><button data-x="tool_calls">tool calls</button></div>
<div class="legend"><span><i style="background:var(--agent)"></i>agent-driven</span><span><i style="background:var(--turn)"></i>turn-based</span><span><i class="dash"></i>notes only (earlier)</span><span><span class="dot"></span>level completed</span></div></div>"""

STATIC_CSS = """body{background:#fff;color:#0b0b0b;padding:22px 26px 0;font-size:16px;width:1200px}
h1{font-family:Georgia,'Times New Roman',serif;font-size:30px;margin:0 0 4px;letter-spacing:-.2px}
.sub{font-size:16.5px;line-height:1.4;margin:0 0 8px}
.legend{font-size:15.5px;color:#3d3c39;gap:26px;margin-bottom:6px}.legend i{width:26px;height:4px;margin-right:8px}
.legend i.dash{border-top-width:2.5px}
.game{border:0;padding:0;gap:56px;grid-template-columns:minmax(0,1.32fr) minmax(0,1fr)}
svg{margin-top:10px}table{font-size:16px}th{font-size:15.5px;font-weight:600;padding:8px 6px}td{padding:7px 6px}td.g{width:100px;font-size:17px}
th.ca{color:#2a78d6}th.ct{color:#eb6834}.hid{font-size:13.5px}"""

ABOUT = {"ps_modality-v1": "Sokoban where floor colour limits where you can walk.",
         "ps_icecrates-v1": "Ice: you slide until you hit something.",
         "ps_knightoban-v1": "Red boxes jump like a chess knight."}
TITLE = {"ps_modality-v1": "Modality", "ps_icecrates-v1": "IceCrates", "ps_knightoban-v1": "Knightoban"}


def page(only=None):
    if only is None:
        head, css = HEAD, ""
    else:
        head = (f"<h1>{TITLE[only]}: rules figured out vs moves played</h1>"
                f"<p class=\"sub\">{ABOUT[only]} Line = % of the game's real rules the model believes, read from its notes and "
                "its thinking (checked at every notes rewrite, every 25 moves and every level); faint dashed = the earlier "
                "grade from the notes alone; dots = level completed.</p>"
                "<div class=\"legend\"><span><i style=\"background:var(--agent)\"></i>agent-driven (plays through a command, "
                "writes scripts)</span><span><i style=\"background:var(--turn)\"></i>turn-based (one board in, one move out)"
                "</span><span><i class=\"dash\"></i>notes only (earlier)</span></div>")
        css = STATIC_CSS
    return (PAGE.replace("/*DATA*/", json.dumps(DATA)).replace("/*ONLY*/", json.dumps(only))
            .replace("/*HEAD*/", head).replace("/*STATIC*/", css))


if __name__ == "__main__":
    open(f"{here}/rule-learning.html", "w", encoding="utf-8").write(page())
    tmp = tempfile.mkdtemp()
    for game, name in TITLE.items():
        src = os.path.join(tmp, f"{name.lower()}.html")
        open(src, "w", encoding="utf-8").write(page(game))
        out = f"{here}/rule-learning-{name.lower()}.png"
        subprocess.run([CHROME, "--headless=new", "--force-device-scale-factor=1.5", "--window-size=1200,640",
                        "--hide-scrollbars", f"--screenshot={out}", "file:///" + src.replace("\\", "/")], check=True,
                       capture_output=True)
        print(out)
