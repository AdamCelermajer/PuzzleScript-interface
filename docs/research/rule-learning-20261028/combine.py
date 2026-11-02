"""Join the graders' labels (grade/run-*/seg-*/labels.json) with the checkpoint counters into curves-combined.json.

Per run: every checkpoint with its counters, the combined label per rule (notebook + thinking, with persistence),
its source, and the label the notebook alone earns at that moment. The old notebook-only curve (curves.json,
at most 12 graded versions) is copied alongside for comparison.
"""
import json, glob, os

here = os.path.dirname(os.path.abspath(__file__))
g = f"{here}/grade"
key = json.load(open(f"{g}/key.json", encoding="utf-8"))
old = json.load(open(f"{here}/curves.json", encoding="utf-8"))
rules = json.load(open(f"{here}/rules.json", encoding="utf-8"))
VAL = {"correct": 1.0, "partial": 0.5, "absent": 0.0, "wrong": 0.0}
# Grader errors found in the hand spot-check, fixed here (the raw labels stay in grade/):
# (run letter, first cp, last cp, rule, field -> value, reason)
CORRECTIONS = [
    ("F", 0, 7, "I5", {"belief": "absent", "source": "none"},
     "the 'pit'/'rimmed dark blockers' of levels 1-3 are walls; the first water appears in level 4"),
    ("F", 2, 11, "I5", {"notebook": "absent"}, "same: the notebook's impassable dark blocks are walls, not water"),
]


def score(labels, game):
    return round(100 * sum(VAL[labels[r["id"]]] for r in rules[game]) / len(rules[game]), 1)


out = {}
for letter, k in sorted(key.items()):
    meta = json.load(open(f"{g}/run-{letter}/meta.json", encoding="utf-8"))
    lab = {}
    for f in glob.glob(f"{g}/run-{letter}/seg-*/labels.json"):
        for x in json.load(open(f, encoding="utf-8")):
            lab[x["cp"]] = x["labels"]
    for L_, a, b, rule, fix, why in CORRECTIONS:
        if L_ == letter:
            for cp in range(a, b + 1):
                lab[cp][rule] = dict(lab[cp][rule]) | fix | {"corrected": why}
    cps = []
    for c in meta["checkpoints"]:
        L = lab[c["cp"]]
        belief = {r: v["belief"] for r, v in L.items()}
        nb = {r: v["notebook"] for r, v in L.items()}
        cps.append({kk: c[kk] for kk in ("cp", "why", "actions", "levels", "minutes", "gen_tokens", "tool_calls", "notebook_version", "notebook_changed",
                                          "thinking_chars")}
                   | {"belief": belief, "source": {r: v["source"] for r, v in L.items()}, "notebook": nb,
                      "notes": {r: v["note"] for r, v in L.items() if (v.get("note") or "").strip()},
                      "corrected": {r: v["corrected"] for r, v in L.items() if v.get("corrected")},
                      "score": score(belief, k["game"]), "notebook_score": score(nb, k["game"])})
    o = old[k["run"]]
    old_pts = [{"actions": v["actions"], "tool_calls": v["tool_calls"], "gen_tokens": v["gen_tokens"],
                "score": score(v["grades"], k["game"])} for v in o["versions"] if v.get("grades")]
    out[k["run"]] = {"game": k["game"], "driver": k["driver"], "blind_id": letter, "levelups": meta["levelups"],
                     "totals": meta["totals"], "checkpoints": cps, "old_notebook_curve": old_pts,
                     "old_final": next(v["grades"] for v in reversed(o["versions"]) if v.get("grades"))}
    print(letter, k["game"], k["driver"], len(cps), "checkpoints;",
          " ".join(f"{c['actions']}:{c['score']:.0f}/{c['notebook_score']:.0f}" for c in cps))
json.dump(out, open(f"{here}/curves-combined.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("labels:", sum(len(c["belief"]) for r in out.values() for c in r["checkpoints"]))
