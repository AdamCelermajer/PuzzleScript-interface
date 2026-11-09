"""Join the 5 Nov grading into one data file for the presentation: per run, the curve of rule scores, levels, tokens, time,
restarts and the final labels, next to the Chutes batch and the earlier study where they can be compared.

Run from the repo root: uv run python docs/research/rule-learning-vast-20261105/combine.py
"""
import glob
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

here = Path(__file__).resolve().parent
key = json.load(open("output/vast/rule-grading-key.json", encoding="utf-8"))
rules = json.load(open(here.parent / "rule-learning-20261028/rules.json", encoding="utf-8"))
VALUE = {"correct": 1, "partial": 0.5, "wrong": 0, "absent": 0}


def calls(folders):
    total = Counter()
    per_move_seconds = []
    for folder in folders:
        for path in glob.glob(f"{folder}/calls/[0-9][0-9][0-9][0-9].json"):
            d = json.load(open(path, encoding="utf-8"))
            if d.get("method") != "POST":
                continue
            r = d.get("response") or {}
            u = r.get("usage") or {}
            total["calls"] += 1
            total["input"] += u.get("prompt_tokens") or 0
            total["cached"] += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            total["output"] += u.get("completion_tokens") or 0
            total["thinking"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
            total["model_seconds"] += float(d.get("seconds") or 0)
            error = str(d.get("error") or r.get("error") or "")
            total["cut_calls"] += "BrokenPipe" in error
            total["overflow_calls"] += "maximum context" in error
    return dict(total)


def graded(letter):
    labels = []
    for seg in sorted((here / f"grade/run-{letter}").glob("seg-*"), key=lambda p: int(p.name.split("-")[1])):
        if (seg / "labels.json").is_file():
            labels += json.load(open(seg / "labels.json", encoding="utf-8"))
    return labels


out = {}
for letter, info in key.items():
    folders = info["folders"]
    meta = {c["cp"]: c for c in info["checkpoints"]}
    moves = [json.loads(line) for line in open(f"{folders[-1]}/transitions.jsonl", encoding="utf-8")]
    labels = graded(letter)
    curve = []
    for x in labels:
        ids = list(x["labels"])
        c = meta[x["cp"]]
        curve.append({"move": c["actions"], "cp": x["cp"], "minutes": c["minutes"], "generated": c["gen_tokens"], "restart": c["restart"],
                      "score": sum(VALUE[x["labels"][r]["belief"]] for r in ids) / len(ids),
                      "notebook": sum(VALUE[x["labels"][r]["notebook"]] for r in ids) / len(ids)})
    first_correct = {}
    for x in labels:
        for r, v in x["labels"].items():
            if v["belief"] == "correct" and r not in first_correct:
                first_correct[r] = meta[x["cp"]]["actions"]
    start = datetime.fromisoformat(moves[0]["timestamp"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(moves[-1]["timestamp"]).replace(tzinfo=timezone.utc)
    result = json.load(open(f"{folders[-1]}/result.json", encoding="utf-8"))
    blocks = []
    for s in range(0, len(moves), 50):
        part = moves[s:s + 50]
        blocks.append({"from": s, "changed": sum(m["changed"] for m in part), "boards": len({json.dumps(m["after"]["grid"]) for m in part}),
                       "resets": sum(m["action"] == "RESET" for m in part), "undos": sum(m["action"] == "ACTION7" for m in part)})
    out[letter] = {"game": info["game"][3:-3], "driver": "agentic" if info["driver"] == "agent" else "turn-based", "folders": folders,
                   "moves": len(moves), "levels": result.get("levels_completed"), "win_levels": info["win_levels"], "solved": bool(result.get("solved")),
                   "reason": result.get("reason"), "levelups": info["levelups"], "resumes": len(folders) - 1, "hours": round((end - start).total_seconds() / 3600, 2),
                   "tokens": calls(folders), "curve": curve, "graded_checkpoints": len(labels), "checkpoints": len(meta),
                   "final": labels[-1]["labels"] if labels else None, "first_correct": first_correct,
                   "rules": {r["id"]: r["rule"] for r in rules[info["game"]]},
                   "blocks": blocks}

earlier = json.load(open(here.parent / "rule-learning-20261028/curves-combined.json", encoding="utf-8"))
old = {}
for name, r in earlier.items():
    cps = r.get("checkpoints") or []
    old[name] = {"game": (r.get("game") or "")[3:-3], "driver": "agentic" if r.get("driver") == "agent" else "turn-based",
                 "curve": [{"move": c.get("actions"), "score": c.get("score", c.get("combined_score"))} for c in cps],
                 "levelups": r.get("levelups")}
data = {"runs": out, "oct21": old}
json.dump(data, open(here / "results.json", "w", encoding="utf-8"), indent=1)
for letter, r in out.items():
    t = r["tokens"]
    print(letter, r["game"], r["driver"], "moves", r["moves"], "levels", r["levels"], "/", r["win_levels"], "resumes", r["resumes"], "hours", r["hours"], "graded", r["graded_checkpoints"], "of", r["checkpoints"],
          "| output", t.get("output"), "thinking", t.get("thinking"), "cut", t.get("cut_calls"), "overflow", t.get("overflow_calls"), "end score", round(r["curve"][-1]["score"] * 100, 1) if r["curve"] else None)
print("oct21 keys sample:", list(next(iter(earlier.values())).keys())[:14], list((next(iter(earlier.values())).get("checkpoints") or [{}])[0].keys())[:16])
