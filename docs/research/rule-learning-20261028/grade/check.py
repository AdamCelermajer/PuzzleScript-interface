"""Check a segment's labels.json: every checkpoint, every rule, valid values, notes on changes."""
import json, glob, os, sys

d = sys.argv[1].rstrip("/\\")
rules = [r["id"] for r in json.load(open(f"{d}/rules.json", encoding="utf-8"))]
cps = sorted(int(os.path.basename(f)[3:6]) for f in glob.glob(f"{d}/cp-*.md"))
labels = json.load(open(f"{d}/labels.json", encoding="utf-8"))
prev = {}
if os.path.exists(f"{d}/start.json"):
    prev = {k: v["belief"] for k, v in json.load(open(f"{d}/start.json", encoding="utf-8")).items()}
L, S = {"correct", "partial", "wrong", "absent"}, {"notebook", "thinking", "both", "none"}
errs = []
if [x.get("cp") for x in labels] != cps:
    errs.append(f"checkpoints {[x.get('cp') for x in labels]} != files {cps}")
for x in labels:
    for r in rules:
        v = (x.get("labels") or {}).get(r)
        if not v:
            errs.append(f"cp {x.get('cp')}: missing {r}"); continue
        if v.get("belief") not in L or v.get("notebook") not in L or v.get("source") not in S:
            errs.append(f"cp {x['cp']} {r}: bad value {v}")
        if (v.get("belief") == "absent") != (v.get("source") == "none"):
            errs.append(f"cp {x['cp']} {r}: source must be none exactly when belief is absent")
        if v.get("belief") != prev.get(r) and not (v.get("note") or "").strip() and not (r not in prev and v.get("belief") == "absent"):
            errs.append(f"cp {x['cp']} {r}: belief changed without a note")
        prev[r] = v.get("belief")
print("\n".join(errs) if errs else f"ok: {len(labels)} checkpoints x {len(rules)} rules")
