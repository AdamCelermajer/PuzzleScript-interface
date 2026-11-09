"""Build runs.html: the six 800-move runs of 5 Nov 2026. One table, then for each run one rule grid against tokens used and
the model call of its key moment. Run from the repo root, after combine.py:
    uv run python docs/research/rule-learning-vast-20261105/build_page.py
"""
import base64
import glob
import html
import json
from datetime import datetime, timezone
from pathlib import Path

here = Path(__file__).resolve().parent
data = json.load(open(here / "results.json", encoding="utf-8"))
key = json.load(open("output/vast/rule-grading-key.json", encoding="utf-8"))
runs = data["runs"]
ORDER = ["I", "K", "G", "L", "J", "H"]
NAMES = {"modality": "Modality", "icecrates": "IceCrates", "knightoban": "Knightoban"}
MERGED = "http://adampalace-pc.tail65f3f9.ts.net:5173/runs/output/workbench/20261105T080749-vast-4x5090-800-xhigh-merged/"
SHORT = {"M1": "Controls", "M2": "Push", "M3": "Blocked push", "M4": "Floor limits walking", "M5": "Grey connects", "M6": "Floor limits pushing", "M7": "Crate on any floor", "M8": "Win",
         "I1": "Controls", "I2": "Sliding", "I3": "Push", "I4": "Chain push", "I5": "Water blocks", "I6": "Crate fills water", "I7": "Stop on goal",
         "K1": "Controls", "K2": "Walls, crates", "K3": "Knight jump", "K4": "Landing must be free", "K5": "Choosing a landing", "K6": "Confirm", "K7": "Win"}
CONTROLS_INTO = {"M1": "M2", "I1": "I2", "K1": "K2"}
HIDDEN = {"I4", "I6", "I7", "K3", "K4", "K5", "K6", "M4", "M5", "M6", "M7"}
VALUE = {"correct": 1, "partial": 0.5, "wrong": 0, "absent": 0}
BATCH_SECONDS = (datetime(2026, 11, 5, 10, 47, 25) - datetime(2026, 11, 5, 6, 7, 50)).total_seconds()
MACHINE_TFLOPS = 79.4 + 78.6 + 78.8 + 76.6  # measured on this machine: FP32 matmul, all four at once at 575 W
FLOPS_PER_TOKEN = 2 * 27e9  # one multiply-accumulate per parameter, two operations each
STORIES = {
    "I": {"title": "One push the other way", "line": "Believed the crate could not move for 48 moves. One new test changed that.",
          "phrase": "never once tried pushing", "quote": "never once tried pushing the orange box toward an open tile!"},
    "K": {"title": "One wrong number in its solver", "line": "Stuck for 455 moves on the last level, because of one wrong floor value in its own solver.",
          "phrase": "158-move solution", "quote": "158-move solution"},
    "G": {"title": "3 levels in 43 moves, then none", "line": "No win in its last 757 moves. It invented rules and ruled out chain pushes without testing them.",
          "phrase": "Can't push a crate onto a crate", "quote": "Can't push a crate onto a crate"},
    "L": {"title": "“This is a breakthrough!”", "line": "Its solver said impossible. It fixed its own simulator, then won with a 32-move plan.",
          "phrase": "This is a breakthrough", "quote": "This is a breakthrough!", "call": "resume-0cd48014/run-0001/calls/0045.json"},
    "J": {"title": "It ruled out the real goal", "line": "At move 220 it rejected the real goal, and never took that back in 580 more moves.",
          "phrase": "The box on the goal is out", "quote": "The box on the goal is out."},
    "H": {"title": "“There's no way to stop”", "line": "Decided level 3 was impossible, then went left and right for its last 274 moves.",
          "phrase": "There's no way to", "quote": "There's no way to \"stop\"", "call": "resume-d73e8f63/run-0001/calls/0261.json"},
}
# Each rule still partial at the end of a run: (what the player knows, what is missing or wrong). Written from the grader's report; the build fails if the set differs from the final labels.
PARTIALS = {
    "I": {"M6": ("Same-colour pushes work.", "Treats grey as neutral, so it allows a push from grey onto a crate on black.")},
    "K": {"M1": ("The four directions.", "Never says the action button is unused, though this game does not offer one."),
          "M6": ("Floor limits pushing, using its walking rule.", "That rule wrongly allows pushes between grey and black."),
          "M8": ("A box on the target wins and the next level loads.", "Never says every crate must be on a target.")},
    "G": {"I2": ("Slides until a wall or water stops it.", "Adds false exceptions from misread positions, like “Down = −1 cell”."),
          "I6": ("A crate into water disappears, and the player can then cross.", "From move 675, also believes a filled tile can take more crates or let one pass."),
          "I7": ("Stopping on the goal won levels 1 and 2.", "Never makes it general: thinks passing over the goal won level 3.")},
    "L": {"I4": ("A row of touching crates moves together.", "Thinks a moving crate stops at a crate it meets, instead of pushing it.")},
    "J": {"K2": ("Walls block.", "Never met an orange crate, so nothing on pushing them."),
          "K3": ("The player enters the crate's cell, and the crate lands in much of the L shape.", "Thinks the jump depends on the target's position."),
          "K4": ("Walls can refuse a move.", "No rule that the landing must be empty, and nothing on crates or the player there."),
          "K5": ("The keys swap the landing cell.", "Thinks the player sometimes moves while choosing.")},
    "H": {"K1": ("The four directions, and what ACTION5 does.", "Calls ACTION5 “clear enemies”, not confirming a choice. It knew better at move 75 and lost it at the restart at 299."),
          "K2": ("Walls block.", "Never met an orange crate, so nothing on pushing them."),
          "K3": ("The player enters the crate's cell. Full L shape stated by move 100.", "Later plans keep predicting the wrong landing cells."),
          "K4": ("Some moves into a red crate are refused.", "Gives the wrong cause, with no rule that the landing must be empty."),
          "K5": ("The markers swap, and the player cannot walk during that.", "Sees the markers as enemies, not as a choice.")},
}
ARROWS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")
# What the player believed about each control. A belief is (quote, where): None for its thinking, "end" for its final file, a move number for its notes at that move.
# Every quote is asserted against the record. Undo and reset are not in the grader's rules. ACTION5 follows the grader's final label. Moves means the four directions only,
# so K counts as understood although the grader gave M1 partial for never saying the action button is unused.
CONTROLS = {
    "I": ("all understood by move 17", [
        ("Moves", ARROWS, "correct", "Move 4", [("ACTION1 = up, ACTION2 = down, ACTION3 = left, ACTION4 = probably right", None)]),
        ("Undo (ACTION7)", ("ACTION7",), "correct", "Move 7", [("Therefore ACTION7 is undo.", None)]),
        ("Reset", ("RESET",), "correct", "Move 17", [("RESET=reset the level", None)])]),
    "K": ("undo never understood", [
        ("Moves", ARROWS, "correct", "Move 12", [("ACTION1 = move 5 up", 12)]),
        ("Undo (ACTION7)", ("ACTION7",), "wrong", "Never", [("So ACTION7 = \"random move of the 5\"", None), ("No undo, no history.", "end")]),
        ("Reset", ("RESET",), "correct", "Move 30", [("RESET restored the initial state", None)])]),
    "G": ("undo understood only at move 535", [
        ("Moves", ARROWS, "correct", "Move 10", [("ACTION1/2/3/4 = slide up/down/left/right", None)]),
        ("Undo (ACTION7)", ("ACTION7",), "partial", "Move 535", [("random past/current position", None), ("A7 = time rewind (2 actions)", None), ("So A7 = pure undo", None)]),
        ("Reset", ("RESET",), "correct", "Move 30", [("RESET is a complete level restart", None)])]),
    "L": ("all understood, one lapse at move 322", [
        ("Moves", ARROWS, "correct", "Start, lapse at 322", [("ACTION1..4 = up/down/left/right", None), ("the quadrant hypothesis is confirmed", None), ("A1=up, A2=down, A3=left, A4=right.", None)]),
        ("Undo (ACTION7)", ("ACTION7",), "correct", "Move 19", [("So ACTION7 = undo last move.", None)]),
        ("Reset", ("RESET",), "correct", "Move 49", [("The level has been reset", None)])]),
    "J": ("undo never understood", [
        ("Moves", ARROWS, "correct", "Move 2", [("ACTION1 = up", None)]),
        ("ACTION5 (confirm)", ("ACTION5",), "correct", "Move 57", [("settle the box first (ACTION5)", None)]),
        ("Undo (ACTION7)", ("ACTION7",), "wrong", "Never", [("ACTION7 = \"box jumps 2 tiles toward the player\" (magnet/attract)", None), ("No other undo/history exists.", "end")]),
        ("Reset", ("RESET",), "correct", "Move 41", [("Reset to initial state", None)])]),
    "H": ("ACTION5 only partly understood", [
        ("Moves", ARROWS, "correct", "Move 4", [("So ACTION4 = move right. Confirmed.", None)]),
        ("ACTION5 (confirm)", ("ACTION5",), "partial", "Partly", [("removes all enemies", "end")]),
        ("Undo (ACTION7)", ("ACTION7",), "correct", "Move 39", [("ACTION7 = UNDO!!", None)]),
        ("Reset", ("RESET",), "correct", "Move 18", [("RESET returned to the initial state.", None)])]),
}


def esc(text):
    return html.escape(str(text), quote=True)


def k(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def hours(h):
    return f"{int(h)}h {round((h - int(h)) * 60):02d}m"


def stamp(text):
    value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).timestamp()


def graded(letter):
    out = []
    for seg in sorted((here / f"grade/run-{letter}").glob("seg-*"), key=lambda p: int(p.name.split("-")[1])):
        out += json.load(open(seg / "labels.json", encoding="utf-8"))
    return out


def scores(labels):
    v = {r: VALUE[x["belief"]] for r, x in labels.items()}
    for control, movement in CONTROLS_INTO.items():
        if control in v:
            v[movement] = (v[movement] + v.pop(control)) / 2
    hidden = [s for r, s in v.items() if r in HIDDEN]
    visible = [s for r, s in v.items() if r not in HIDDEN]
    return 100 * sum(visible) / len(visible), 100 * sum(hidden) / len(hidden)


def load_calls(letter):
    """Every model call of the run, in order: (start, end, path, record)."""
    out = []
    for folder in runs[letter]["folders"]:
        for path in glob.glob(f"{folder}/calls/[0-9][0-9][0-9][0-9].json"):
            d = json.load(open(path, encoding="utf-8"))
            if d.get("method") == "POST" and d.get("started"):
                start = stamp(d["started"])
                out.append((start, start + float(d.get("seconds") or 0), path.replace("\\", "/"), d))
    return sorted(out, key=lambda x: x[0])


def grid(letter, calls):
    """One row per rule, one cell per step. A cell's width is the tokens used in that step, so the x axis is tokens used."""
    run = runs[letter]
    labels = graded(letter)
    meta = {c["cp"]: c for c in key[letter]["checkpoints"]}
    finished = sorted((end, ((d.get("response") or {}).get("usage") or {}).get("completion_tokens") or 0) for _, end, _, d in calls)
    used = lambda t: sum(n for end, n in finished if end <= t)
    total = sum(n for _, n in finished)
    steps = []
    for item in labels:
        c = meta[item["cp"]]
        steps.append({"labels": item["labels"], "tokens": used(c["t"]), "move": c["actions"], "restart": c["restart"]})
    steps[-1]["tokens"] = total
    rules = list(run["rules"])
    LEFT, RIGHT, TOP, ROW, GAP, BOTTOM, W = 150, 8, 16, 21, 2, 36, 760
    width = W - LEFT - RIGHT
    x = lambda t: LEFT + width * t / total
    H = TOP + len(rules) * (ROW + GAP) + BOTTOM
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Belief in each rule at each step, against tokens used">']
    previous = 0
    for step in steps:
        x0, x1 = x(previous), max(x(step["tokens"]), x(previous) + 0.6)
        for row, rule in enumerate(rules):
            belief = step["labels"][rule]["belief"]
            y = TOP + row * (ROW + GAP)
            parts.append(f'<rect x="{x0:.2f}" y="{y}" width="{x1 - x0:.2f}" height="{ROW}" class="c-{belief}"><title>{esc(SHORT[rule])}: {belief} · move {step["move"]} · {k(step["tokens"])} tokens</title></rect>')
        previous = step["tokens"]
    for row, rule in enumerate(rules):
        y = TOP + row * (ROW + GAP)
        parts.append(f'<text x="{LEFT - 8}" y="{y + ROW * 0.72:.1f}" class="rule" text-anchor="end">{esc(SHORT[rule])}</text>')
    bottom = TOP + len(rules) * (ROW + GAP)
    moves = [(s["tokens"], s["move"]) for s in steps]
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        t = total * fraction
        move = next((m for tok, m in moves if tok >= t), run["moves"]) if fraction else 0
        anchor = "start" if fraction == 0 else "end" if fraction == 1 else "middle"
        parts.append(f'<text x="{x(t):.1f}" y="{bottom + 13}" class="tok" text-anchor="{anchor}">{k(t) if fraction else "0 tokens"}</text>'
                     f'<text x="{x(t):.1f}" y="{bottom + 27}" class="mov" text-anchor="{anchor}">move {move}</text>')
    for move, _ in run["levelups"]:
        tokens = next((tok for tok, m in moves if m >= move), total)
        parts.append(f'<path d="M{x(tokens) - 5:.1f} 3 h10 l-5 9 z" class="wintick"><title>Level won at move {move}</title></path>')
    for step in steps:
        if step["restart"]:
            parts.append(f'<line x1="{x(step["tokens"]):.1f}" x2="{x(step["tokens"]):.1f}" y1="{TOP - 3}" y2="{bottom}" class="restart"/>')
    parts.append("</svg>")
    return "".join(parts), labels[-1]["labels"]


def frame(run, move, moves):
    folder = run["folders"][-1]
    index = moves[max(move, 1) - 1].get("decision", move)
    for candidate in (f"{folder}/frames/{index:03d}.png", f"{folder}/frames/{move:03d}.png"):
        if Path(candidate).is_file():
            return "data:image/png;base64," + base64.b64encode(Path(candidate).read_bytes()).decode()
    return None


def partials(letter, final):
    """What each partial rule lacks, and what it takes off the Visible or Hidden score shown in the table."""
    rules = runs[letter]["rules"]
    entries = PARTIALS[letter]
    assert set(entries) == {r for r, x in final.items() if x["belief"] == "partial"}, letter
    cells = []
    for rule, (knows, missing) in entries.items():
        hidden = rule in HIDDEN
        size = sum((r in HIDDEN) == hidden and r not in CONTROLS_INTO for r in rules)  # controls share one row with movement
        shared = rule in CONTROLS_INTO or rule in CONTROLS_INTO.values()
        cost = 100 * (0.25 if shared else 0.5) / size
        cells.append(f'<tr><td>{esc(SHORT[rule])}</td><td>{esc(knows)}</td><td>{esc(missing)}</td><td class="num">−{cost:.1f}% {"hidden" if hidden else "visible"}</td></tr>')
    return (f'<details><summary>Partial rules: {len(entries)} of {len(rules)} at the end</summary><div class="scroll"><table class="controls partials"><thead><tr><th>Rule</th><th>Knows</th><th>Missing or wrong</th><th class="num">Costs</th></tr></thead>'
            f'<tbody>{"".join(cells)}</tbody></table></div><p class="small">Every partial counts as half a rule, however much is missing. Written from the grader\'s report.</p></details>')


def undo_presses(moves):
    """Replay the run: undo goes back one action, a blocked move counts as one, RESET and a level win clear the history. Fails if any press disagrees."""
    history, presses = [], 0
    for m in moves:
        if m["action"] == "ACTION7":
            presses += 1
            assert (history.pop() if history else m["before"]["grid"]) == m["after"]["grid"], m["id"]
        elif m["action"] == "RESET":
            history = []
        else:
            history.append(m["before"]["grid"])
        if m["before"].get("levels_completed") != m["after"].get("levels_completed"):
            history = []
    return presses


def belief(letter, quote, where, after, calls, times):
    """Check one quote against the record. Returns (label, move it was found at)."""
    folders = runs[letter]["folders"]
    if where == "end":
        assert quote in Path(folders[-1], "world_model_snapshots/final.md").read_text(encoding="utf-8"), (letter, quote)
        return "End", after
    if where is not None:
        assert any(quote in Path(p).read_text(encoding="utf-8", errors="replace") for f in folders for p in glob.glob(f"{f}/agent_files/*/*.md")), (letter, quote)
        return f"Move {where}", where
    for start, _, _, d in calls:
        move = sum(x <= start for x in times)
        if move >= after and quote in ((d.get("response") or {}).get("reasoning") or ""):
            return (f"Move {move}" if move else "Start"), move
    raise AssertionError((letter, quote))


def controls(letter, moves, times, calls):
    summary, rows = CONTROLS[letter]
    cells = []
    for name, actions, mark, when, beliefs in rows:
        pressed = [m for m in moves if m["action"] in actions]
        after, trail = 0, []
        for quote, where in beliefs:
            label, after = belief(letter, quote, where, after, calls, times)
            trail.append(f'{label}: “{esc(quote)}”')
        cells.append(f'<tr><td>{esc(name)}</td><td class="num">{len(pressed)}</td><td class="num">{sum(not m["changed"] for m in pressed)}</td><td>{" → ".join(trail)}</td><td><span class="sw {mark}"></span>{esc(when)}</td></tr>')
    return (f'<details><summary>Controls: {esc(summary)}</summary><div class="scroll"><table class="controls"><thead><tr><th>Control</th><th class="num">Presses</th><th class="num">No change</th><th>What the player believed</th><th>Understood</th></tr></thead>'
            f'<tbody>{"".join(cells)}</tbody></table></div><p class="small">Undo goes back one action, and a blocked move counts as one: true for all {{UNDO_TOTAL}} presses in these runs. Undo and reset were not graded; those rows come from the player\'s own words.</p></details>')


total = {name: sum(r["tokens"].get(name, 0) for r in runs.values()) for name in ("input", "cached", "output", "thinking", "calls")}
work_tokens = lambda t: t.get("input", 0) - t.get("cached", 0) + t.get("output", 0)
total_work = sum(work_tokens(r["tokens"]) for r in runs.values())
capacity = MACHINE_TFLOPS * 1e12 * BATCH_SECONDS
rows, sections = [], []
undo_total = 0
for letter in ORDER:
    run, story = runs[letter], STORIES[letter]
    t = run["tokens"]
    calls = load_calls(letter)
    svg, final = grid(letter, calls)
    vis, hid = scores(final)
    moves = [json.loads(line) for line in open(f"{run['folders'][-1]}/transitions.jsonl", encoding="utf-8")]
    times = [stamp(m["timestamp"]) for m in moves]
    undo_total += undo_presses(moves)
    found = [c for c in calls if story["phrase"].lower() in ((c[3].get("response") or {}).get("reasoning") or "").lower()]
    if story.get("call"):
        found = [c for c in found if c[2].endswith(story["call"])]
    start, _, path, call = found[0]
    thinking = (call.get("response") or {}).get("reasoning") or ""
    assert story["quote"] in thinking, (letter, story["quote"])
    move = sum(x <= start for x in times)
    tokens_then = sum(((d.get("response") or {}).get("usage") or {}).get("completion_tokens") or 0 for s, _, _, d in calls if s < start)
    picture = frame(run, move, moves)
    at = thinking.find(story["quote"])
    begin, stop = max(0, at - 1000), min(len(thinking), at + 700)
    excerpt = ("… " if begin else "") + esc(thinking[begin:at]) + "<mark>" + esc(story["quote"]) + "</mark>" + esc(thinking[at + len(story["quote"]):stop]) + (" …" if stop < len(thinking) else "")
    pips = "".join(f'<span class="pip{" on" if i < run["levels"] else ""}"></span>' for i in range(run["win_levels"]))
    name = Path(run["folders"][0]).name
    cache = 100 * t["cached"] / t["input"]
    rows.append(f'<tr><td><a href="#run-{letter}">{NAMES[run["game"]]}</a></td><td>{esc(run["driver"])}</td><td class="num">{run["levels"]}/{run["win_levels"]}</td><td class="num">{run["moves"]}</td>'
                f'<td class="num">{hours(run["hours"])}</td><td class="num">{k(t["input"])}</td><td class="num">{cache:.0f}%</td><td class="num">{k(t["output"])}</td><td class="num">{k(t["thinking"])}</td>'
                f'<td class="num">{vis:.0f}%</td><td class="num">{hid:.0f}%</td><td class="num">{work_tokens(t) * FLOPS_PER_TOKEN / 1e15:.0f}</td></tr>')
    sections.append(f'''<section class="run" id="run-{letter}">
<p class="eyebrow">{NAMES[run["game"]]} · {esc(run["driver"])}</p>
<h2>{esc(story["title"])}</h2>
<div class="sub"><span class="pips">{pips}</span><span>{run["levels"]}/{run["win_levels"]} levels · {run["moves"]} moves · {k(t["output"])} tokens</span></div>
<p>{esc(story["line"])}</p>
<figure>{svg}</figure>
{partials(letter, final)}
{controls(letter, moves, times, calls)}
<details><summary>Model call at move {move}, after {k(tokens_then)} tokens</summary><div class="callgrid">{f'<img src="{picture}" alt="Board near move {move}">' if picture else ""}<pre>{excerpt}</pre></div>
<p class="file mono">{esc(path.split("output/workbench/")[-1])} · {float(call.get("seconds") or 0):.0f} s · {len(thinking):,} characters of thinking</p></details>
<p class="open"><a href="{MERGED}{name}">Open in workbench</a></p>
</section>''')

PAGE = f'''<title>Qwen Puzzle Runs, 5 Nov</title>
<meta charset="utf-8"><meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@100,400;100,600;125,800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one table, then one rule grid per run. The grid carries the story; words stay short. */
:root{{--bg:#eef2f4;--panel:#fbfcfd;--fg:#16232b;--muted:#566872;--line:#ccd7dd;--accent:#0b6e99;--win:#16232b;--restart:#16232b;--mark:#ffe08a;
--correct:#2f9e5b;--partial:#efb73e;--wrong:#d6453d;--absent:#dbe3e7;--display:"Archivo",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#10191f;--panel:#17222a;--fg:#e4edf1;--muted:#93a5af;--line:#2d3c46;--accent:#5cc2ec;--win:#e4edf1;--restart:#e4edf1;--mark:#6b5410;--correct:#3fae6c;--partial:#d9a52f;--wrong:#d9534a;--absent:#26333c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#10191f;--panel:#17222a;--fg:#e4edf1;--muted:#93a5af;--line:#2d3c46;--accent:#5cc2ec;--win:#e4edf1;--restart:#e4edf1;--mark:#6b5410;--correct:#3fae6c;--partial:#d9a52f;--wrong:#d9534a;--absent:#26333c;color-scheme:dark}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);font-family:var(--display);font-size:16px;line-height:1.5;padding-block:32px 72px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
main{{max-width:900px;margin:0 auto;display:grid;gap:44px;min-width:0}}
h1,h2{{font-stretch:125%;font-weight:800;line-height:1.1;text-wrap:balance;margin:0}}h1{{font-size:clamp(28px,5vw,42px)}}h2{{font-size:clamp(22px,3.4vw,28px)}}
p{{margin:0}}a{{color:var(--accent)}}a:focus-visible,summary:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.head{{display:grid;gap:8px}}.eyebrow{{font-family:var(--mono);font-size:12.5px;color:var(--muted)}}.mono{{font-family:var(--mono)}}
.scroll{{overflow-x:auto;min-width:0}}table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th{{text-align:left;font-weight:600;color:var(--muted);font-size:12.5px;border-bottom:1px solid var(--line);padding:6px 10px 6px 0;vertical-align:bottom;white-space:nowrap}}td{{border-bottom:1px solid var(--line);padding:7px 10px 7px 0;white-space:nowrap}}.num{{text-align:right}}
.machine{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:0}}.machine dt{{font-size:12.5px;color:var(--muted)}}.machine dd{{margin:0;font-stretch:125%;font-weight:800;font-size:23px}}
.small{{font-size:13px;color:var(--muted)}}.engine td{{white-space:normal}}.controls{{margin-top:8px}}.controls td{{white-space:normal;vertical-align:top}}.controls td:first-child,.controls td:last-child{{white-space:nowrap}}.partials td:nth-child(2),.partials td:nth-child(3){{min-width:190px}}details .small{{margin-top:8px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);align-items:center}}.sw{{display:inline-block;width:13px;height:13px;margin-right:5px;vertical-align:-2px}}.sw.correct{{background:var(--correct)}}.sw.partial{{background:var(--partial)}}.sw.wrong{{background:var(--wrong)}}.sw.absent{{background:var(--absent)}}
.run{{display:grid;gap:12px;border-top:3px solid var(--fg);padding-top:16px;min-width:0;scroll-margin-top:12px}}.run .eyebrow{{margin-bottom:-8px}}
.sub{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:14px;color:var(--muted)}}.pips{{display:inline-flex;gap:4px}}.pip{{width:13px;height:13px;border:1.5px solid var(--muted);display:inline-block}}.pip.on{{background:var(--correct);border-color:var(--correct)}}
figure{{margin:0;min-width:0}}figure svg{{width:100%;height:auto;display:block}}.c-correct{{fill:var(--correct)}}.c-partial{{fill:var(--partial)}}.c-wrong{{fill:var(--wrong)}}.c-absent{{fill:var(--absent)}}figure rect{{shape-rendering:crispEdges}}
.rule{{fill:var(--fg);font:500 12.5px var(--display)}}.tok{{fill:var(--fg);font:600 11.5px var(--mono)}}.mov{{fill:var(--muted);font:11px var(--mono)}}.wintick{{fill:var(--win)}}.restart{{stroke:var(--restart);stroke-width:1.5;stroke-dasharray:3 3}}
summary{{cursor:pointer;font-size:14px;color:var(--accent)}}.callgrid{{display:grid;grid-template-columns:minmax(0,150px) minmax(0,1fr);gap:14px;margin-top:10px}}.callgrid img{{width:100%;image-rendering:pixelated;display:block;border:1px solid var(--line)}}
pre{{font-family:var(--mono);font-size:12.5px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;margin:0;max-height:360px;overflow:auto;background:var(--panel);border:1px solid var(--line);padding:10px}}mark{{background:var(--mark);color:inherit;padding:0 2px}}.file{{font-size:11.5px;color:var(--muted);overflow-wrap:anywhere;margin-top:8px}}.open{{font-size:14px}}
@media (max-width:620px){{.callgrid{{grid-template-columns:minmax(0,1fr)}}.callgrid img{{max-width:180px}}}}
</style>
<main>
<div class="head"><h1>Six runs, three puzzle games</h1><p class="eyebrow">Qwen3.8 27B · xhigh · OpenCode · 4×RTX 5090 · up to 800 moves</p></div>
<section><div class="scroll"><table><thead><tr><th>Game</th><th>Driver</th><th class="num">Levels</th><th class="num">Moves</th><th class="num">Time</th><th class="num">Input</th><th class="num">Cached</th><th class="num">Output</th><th class="num">Thinking</th><th class="num">Visible rules</th><th class="num">Hidden rules</th><th class="num">PFLOP</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
<dl class="machine"><div><dt>Measured speed</dt><dd>{MACHINE_TFLOPS:.0f} TFLOPS</dd></div><div><dt>Maximum, {BATCH_SECONDS / 3600:.1f} h</dt><dd>{capacity / 1e18:.1f} EFLOP</dd></div><div><dt>Model work, estimate</dt><dd>{total_work * FLOPS_PER_TOKEN / 1e18:.1f} EFLOP</dd></div><div><dt>Input cached</dt><dd>{100 * total["cached"] / total["input"]:.0f}%</dd></div></dl>
<p class="small">Model work assumes 54 GFLOP per token, on {k(total["output"])} output and {k(total["input"] - total["cached"])} uncached input tokens: an order of magnitude only.</p>
<section class="engine"><div class="scroll"><table><thead><tr><th>Inference</th><th>Setting</th><th>Result</th></tr></thead><tbody>
<tr><td>Engine</td><td>vLLM 0.31.0, CUDA 13.0</td><td>4 GPUs, tensor parallel</td></tr>
<tr><td>Weights</td><td>Qwen3.8-27B FP8</td><td>29 GB</td></tr>
<tr><td>KV cache</td><td>FP8</td><td>2.04M tokens, 7.8× a full context</td></tr>
<tr><td>Speculative decoding</td><td>MTP, 2 draft tokens</td><td>104 → 213 tok/s alone, 572 → 816 with 10 at once (21 Oct)</td></tr>
<tr><td>Prefix caching</td><td>on, Mamba align</td><td>{100 * total["cached"] / total["input"]:.0f}% of input cached</td></tr>
<tr><td>Chunked prefill</td><td>8,192 tokens per batch</td><td>not measured alone</td></tr>
<tr><td>Limits</td><td>262,144 context, 16 sequences</td><td>6 runs, no queue seen most of the time</td></tr>
</tbody></table></div></section>
<div class="legend"><span><span class="sw correct"></span>correct</span><span><span class="sw partial"></span>partial</span><span><span class="sw wrong"></span>wrong</span><span><span class="sw absent"></span>no belief</span><span>▼ level won</span><span>┆ restart</span><span>Hover a cell for its step.</span></div>
{"".join(sections)}
<p class="small">Graded blind by gpt-6-astra, one grader per run. Graders differed on two Modality rules, so small score differences mean little.</p>
</main>'''
PAGE = PAGE.replace("{UNDO_TOTAL}", str(undo_total))
(here / "runs.html").write_text(PAGE, encoding="utf-8")
print("written", len(PAGE) // 1024, "KB")
