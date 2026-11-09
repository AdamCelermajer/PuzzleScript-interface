"""Check a whole graded run: every segment passes grade/check.py's rules, labels carry on across segments, and every
evidence quote is word for word in the text available by then, at most 20 words.
Usage: uv run python docs/research/rule-learning-vast-20261105/grade/check_run.py run-X"""
import glob
import json
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
run = os.path.join(here, sys.argv[1])
segs = sorted(glob.glob(f"{run}/seg-*"), key=lambda p: int(p.rsplit("-", 1)[1]))
errors, quotes, found, previous = [], 0, 0, {}
seen = ""
norm = lambda text: re.sub(r"\s+", " ", text.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()
LABELS, SOURCES = {"correct", "partial", "wrong", "absent"}, {"notebook", "thinking", "both", "none"}
if not os.path.isfile(f"{run}/report.md"):
    errors.append("no report.md yet")
for s in segs:
    name = os.path.basename(s)
    files = sorted(glob.glob(f"{s}/cp-*.md"))
    if not os.path.isfile(f"{s}/labels.json"):
        errors.append(f"{name}: no labels.json")
        continue
    rules = [r["id"] for r in json.load(open(f"{s}/rules.json", encoding="utf-8"))]
    labels = json.load(open(f"{s}/labels.json", encoding="utf-8"))
    if not os.path.isfile(f"{s}/handoff.md"):
        errors.append(f"{name}: no handoff.md")
    if [x.get("cp") for x in labels] != [int(os.path.basename(f)[3:6]) for f in files]:
        errors.append(f"{name}: the checkpoints do not match the files")
    for x, f in zip(labels, files):
        seen += " " + norm(open(f, encoding="utf-8").read())
        for r in rules:
            v = (x.get("labels") or {}).get(r)
            if not v:
                errors.append(f"cp {x.get('cp')} {r}: missing")
                continue
            if v.get("belief") not in LABELS or v.get("notebook") not in LABELS or v.get("source") not in SOURCES:
                errors.append(f"cp {x['cp']} {r}: bad value")
            if (v.get("belief") == "absent") != (v.get("source") == "none"):
                errors.append(f"cp {x['cp']} {r}: source must be none exactly when belief is absent")
            note = (v.get("note") or "").strip()
            changed = v.get("belief") != previous.get(r)
            if changed and not note and not (r not in previous and v.get("belief") == "absent"):
                errors.append(f"cp {x['cp']} {r}: belief changed without a note")
            previous[r] = v.get("belief")
            if note and note[:2] in ("N:", "T:"):
                quote = note[2:].strip()
                parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", quote) if p.strip()]
                quotes += 1
                if len(quote.split()) > 24:
                    errors.append(f"cp {x['cp']} {r}: quote over 20 words")
                if all(norm(p).strip(" '\"") in seen for p in parts):
                    found += 1
                else:
                    errors.append(f"cp {x['cp']} {r}: quote not in the text: {quote[:90]}")
print(f"{os.path.basename(run)}: {len(segs)} segments, {found} of {quotes} quotes found word for word, {len(errors)} problems")
print("\n".join(errors[:40]))
