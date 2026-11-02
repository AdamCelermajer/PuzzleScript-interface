"""Belief checkpoints for the combined (notebook + thinking) grading of the six 21 Oct runs.

Checkpoints: every 25 game moves, every level completion, every distinct world_model.md version, and the run end;
plus extra ones inside any window holding more than SPLIT characters of thinking.
For each checkpoint, writes the latest notebook (when it changed) and the thinking written since the previous
checkpoint. Checkpoints are grouped into segments of at most MAX_CHARS for sequential grading by blind graders
(runs are named A..F; the key stays in grade/key.json).

Run from the repo root: uv run python docs/research/rule-learning-20261028/checkpoints.py
"""
import json, glob, os, re, bisect, datetime, sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from rebuild import rebuild, ts

B = "output/workbench/"
RUNS = {  # blind letter -> run
    "A": B + "20261021T162323-vast-fp8-baseline-v4-6767db38/run-0003",
    "B": B + "20261021T144508-vast-fp8-harness2-153a4dc2/run-0002/rollouts/base1",
    "C": B + "20261021T162323-vast-fp8-baseline-v4-6767db38/run-0001",
    "D": B + "20261021T144508-vast-fp8-harness2-153a4dc2/run-0003/rollouts/base1",
    "E": B + "20261021T144508-vast-fp8-harness2-153a4dc2/run-0001/rollouts/base1",
    "F": B + "20261021T162323-vast-fp8-baseline-v4-6767db38/run-0002",
}
MAX_CHARS = 280_000
SPLIT = 100_000  # a window with more thinking than this gets extra checkpoints inside it
EVERY = 25


def thinking(run):
    out = []
    for f in glob.glob(f"{run}/raw/turn-*.jsonl"):
        for line in open(f, encoding="utf-8"):
            if '"type":"reasoning"' not in line:
                continue
            e = json.loads(line)
            txt = (e.get("part") or {}).get("text") or ""
            if txt.strip():
                out.append((e["timestamp"] / 1000, txt))
    out.sort()
    return out


def counters(run):
    """Generated tokens per step and tool-call end times, as rebuild.py counts them."""
    steps, tools = [], []
    for f in glob.glob(f"{run}/raw/turn-*.jsonl"):
        for line in open(f, encoding="utf-8"):
            e = json.loads(line); p = e.get("part") or {}
            if e["type"] == "step_finish":
                tok = p.get("tokens") or {}
                steps.append((e["timestamp"] / 1000, (tok.get("output") or 0) + (tok.get("reasoning") or 0)))
            if e["type"] == "tool_use" and p.get("type") == "tool":
                tools.append((((p.get("state") or {}).get("time") or {}).get("end") or e["timestamp"]) / 1000)
    return steps, tools


def build(letter, run):
    r = rebuild(run)
    spec = open(f"{run}/run_config.json" if os.path.exists(f"{run}/run_config.json") else f"{run}/run_spec.json").read()
    game = re.search(r"ps_[a-z0-9_]+-v1", spec).group(0)
    moves = [ts(json.loads(l)["timestamp"]) for l in open(f"{run}/transitions.jsonl", encoding="utf-8")]
    th = thinking(run)
    start = min([moves[0]] + [t for t, _ in th])
    end = max([moves[-1]] + [t for t, _ in th])
    # Times of each checkpoint. Moves have 1 s resolution: a move checkpoint covers everything up to that second.
    cps = []
    for n in range(EVERY, len(moves) + 1, EVERY):
        cps.append((moves[n - 1] + 0.999, "moves"))
    for lu in r["levelups"]:
        cps.append((moves[lu["actions"] - 1] + 0.999, f"level {lu['level']} completed"))
    for v in r["versions"]:
        cps.append((start + v["minutes"] * 60 if v["source"] == "edit" else moves[max(v["actions"], 1) - 1] + 0.999,
                    "notebook"))
    cps.append((end + 1, "run end"))
    cps.sort()
    # Notebook version in force at each time: an edit version at its own time, a snapshot at its move.
    vt = []
    for i, v in enumerate(r["versions"]):
        t = start + v["minutes"] * 60 if v["source"] == "edit" else moves[max(v["actions"], 1) - 1] + 0.999
        vt.append((t, i))
    vt.sort()
    merged = []
    for t, why in cps:  # merge checkpoints within the same second
        if merged and t - merged[-1]["t"] < 1.0:
            merged[-1]["why"].add(why); merged[-1]["t"] = max(merged[-1]["t"], t)
        else:
            merged.append({"t": t, "why": {why}})
    extra, prev_t = [], -1e18
    for c in merged:  # split long thinking windows
        size = 0
        for tt, x in th:
            if prev_t < tt <= c["t"]:
                size += len(x)
                if size > SPLIT:
                    extra.append({"t": tt, "why": {"thinking"}}); size = 0
        prev_t = c["t"]
    merged = sorted(merged + extra, key=lambda c: c["t"])
    steps, tools = counters(run)
    out, prev_t, prev_text = [], -1e18, None
    for k, c in enumerate(merged):
        t = c["t"]
        vi = [i for tv, i in vt if tv <= t + 0.001]
        text = r["versions"][vi[-1]]["text"] if vi else None
        chunk = [(tt, x) for tt, x in th if prev_t < tt <= t]
        done = bisect.bisect_right(moves, t)
        levels = max([lu["level"] for lu in r["levelups"] if lu["actions"] <= done] or [0])
        out.append({"cp": k, "t": t, "why": sorted(c["why"]), "actions": done, "levels": levels,
                    "minutes": round((t - start) / 60, 2), "gen_tokens": sum(n for tt, n in steps if tt <= t),
                    "tool_calls": sum(1 for tt in tools if tt <= t), "notebook_version": vi[-1] if vi else None,
                    "notebook_changed": text != prev_text, "notebook": text,
                    "thinking": [(bisect.bisect_right(moves, tt), x) for tt, x in chunk]})
        prev_t, prev_text = t, text
    return {"game": game, "driver": "agent" if "rollouts/base1" in run else "controller", "run": run.split(B)[-1],
            "levelups": r["levelups"], "totals": r["totals"], "checkpoints": out}


def render(c):
    lines = [f"# Checkpoint {c['cp']:03d} — after {c['actions']} game moves", ""]
    if c["notebook"] is None:
        lines += ["## Notebook (world_model.md)", "", "(no notebook written yet)", ""]
    elif c["notebook_changed"]:
        lines += ["## Notebook (world_model.md) — NEW VERSION, written at the end of this window", "", c["notebook"], ""]
    else:
        lines += ["## Notebook (world_model.md)", "", "(unchanged since the previous checkpoint; older than the thinking below)", ""]
    lines += ["## Thinking written since the previous checkpoint", ""]
    if not c["thinking"]:
        lines.append("(none)")
    for n, x in c["thinking"]:
        lines += [f"--- [after {n} moves]", x.strip(), ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    rules = json.load(open(f"{here}/rules.json", encoding="utf-8"))
    g = f"{here}/grade"
    os.makedirs(g, exist_ok=True)
    key, plan = {}, {}
    for letter, run in RUNS.items():
        d = build(letter, run)
        key[letter] = {"run": d["run"], "game": d["game"], "driver": d["driver"]}
        segs, cur, size = [], [], 0
        for c in d["checkpoints"]:
            s = len(render(c))
            if cur and size + s > MAX_CHARS:
                segs.append(cur); cur, size = [], 0
            cur.append(c); size += s
        segs.append(cur)
        for k, seg in enumerate(segs):
            p = f"{g}/run-{letter}/seg-{k}"
            os.makedirs(p, exist_ok=True)
            json.dump([{"id": x["id"], "rule": x["rule"]} for x in rules[d["game"]]],
                      open(f"{p}/rules.json", "w", encoding="utf-8"), indent=1)
            for c in seg:
                open(f"{p}/cp-{c['cp']:03d}.md", "w", encoding="utf-8").write(render(c))
        meta = {k: v for k, v in d.items() if k != "checkpoints"}
        meta["checkpoints"] = [{k: v for k, v in c.items() if k not in ("notebook", "thinking")}
                               | {"thinking_chars": sum(len(x) for _, x in c["thinking"])} for c in d["checkpoints"]]
        meta["segments"] = [[c["cp"] for c in seg] for seg in segs]
        json.dump(meta, open(f"{g}/run-{letter}/meta.json", "w", encoding="utf-8"), indent=1)
        plan[letter] = [(len(seg), sum(len(render(c)) for c in seg)) for seg in segs]
        print(letter, d["game"], d["driver"], len(d["checkpoints"]), "checkpoints", len(segs), "segments", plan[letter])
    json.dump(key, open(f"{g}/key.json", "w", encoding="utf-8"), indent=1)
