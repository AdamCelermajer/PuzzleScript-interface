"""Rebuild every version of a run's world_model.md from raw OpenCode events and put each on one
time axis with the run's counters: generated tokens, processed tokens, tool calls, game actions, levels."""
import json, glob, os, sys, datetime, re

def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "")).replace(tzinfo=datetime.timezone.utc).timestamp()

def rebuild(run):
    files = sorted(glob.glob(f"{run}/raw/turn-*.jsonl"), key=lambda f: int(re.findall(r"\d+", os.path.basename(f))[0]))
    steps, tools, edits, fails = [], [], [], 0
    text = None
    for f in files:
        for line in open(f, encoding="utf-8"):
            e = json.loads(line); p = e.get("part") or {}
            if e["type"] == "step_finish":
                tok = p.get("tokens") or {}
                steps.append((e["timestamp"] / 1000, (tok.get("output") or 0) + (tok.get("reasoning") or 0),
                              (tok.get("input") or 0) + ((tok.get("cache") or {}).get("read") or 0)))
            if e["type"] != "tool_use" or p.get("type") != "tool":
                continue
            st = p.get("state") or {}; inp = st.get("input") or {}
            t = ((st.get("time") or {}).get("end") or e["timestamp"]) / 1000
            tools.append(t)
            if st.get("status") != "completed" or not str(inp.get("filePath") or "").endswith("world_model.md"):
                continue
            new = None
            if p["tool"] == "write":
                new = inp.get("content") or ""
            elif p["tool"] == "edit":
                old, rep = inp.get("oldString") or "", inp.get("newString") or ""
                if text is not None and old and old in text:
                    new = text.replace(old, rep) if inp.get("replaceAll") else text.replace(old, rep, 1)
                else:
                    fails += 1
            if new is not None and new != text:
                text = new
                edits.append((t, text))
    trans = [(ts(json.loads(l)["timestamp"]), json.loads(l)["after"]["levels_completed"])
             for l in open(f"{run}/transitions.jsonl", encoding="utf-8")]
    start = min([s[0] for s in steps] + [t for t, _ in trans])

    def counters(t):
        done = [x for x in trans if x[0] <= t + 0.999]  # transitions have 1 s resolution
        return {"minutes": round((t - start) / 60, 2),
                "gen_tokens": sum(s[1] for s in steps if s[0] <= t),
                "proc_tokens": sum(s[2] for s in steps if s[0] <= t),
                "tool_calls": sum(1 for x in tools if x <= t),
                "actions": len(done), "levels": max([lv for _, lv in done] or [0])}

    wm = [p for p in (f"{run}/workspace/notes/world_model.md", f"{run}/world_model.md", f"{run}/workspace/world_model.md")
          if os.path.exists(p)]
    final_ok = bool(wm) and text == open(wm[0], encoding="utf-8").read()
    versions = [dict(counters(t), source="edit", text=x) for t, x in edits]
    if fails or not final_ok:  # replay incomplete: add the snapshot copies, placed by action count
        for f in sorted(glob.glob(f"{run}/world_model_snapshots/*.md")):
            m = re.search(r"a(\d+)", os.path.basename(f))
            n = int(m.group(1)) if m else len(trans)
            t = trans[min(n, len(trans)) - 1][0] if trans else start
            versions.append(dict(counters(t), source="snapshot:" + os.path.basename(f), text=open(f, encoding="utf-8").read()))
        versions.sort(key=lambda v: (v["actions"], v["tool_calls"]))
        versions = [v for i, v in enumerate(versions) if i == 0 or v["text"] != versions[i - 1]["text"]]
    levelups = []
    prev = 0
    for t, lv in trans:
        if lv > prev:
            levelups.append(dict(counters(t), level=lv)); prev = lv
    end = max([s[0] for s in steps] + [t for t, _ in trans])
    return {"versions": versions, "levelups": levelups, "totals": counters(end), "edit_fails": fails, "final_matches": final_ok}

if __name__ == "__main__":
    out = {}
    for run in sys.argv[1:]:
        r = rebuild(run)
        spec = open(f"{run}/run_config.json" if os.path.exists(f"{run}/run_config.json") else f"{run}/run_spec.json").read()
        game = re.search(r"ps_[a-z0-9_]+-v1", spec).group(0)
        r["game"] = game; r["driver"] = "agent" if "rollouts/base1" in run else "controller"
        name = run.split("output/workbench/")[-1]
        out[name] = r
        print(name, game, r["driver"], "versions", len(r["versions"]), "fails", r["edit_fails"], "final", r["final_matches"], r["totals"])
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions.json"), "w", encoding="utf-8"), indent=1)
