"""List the next segment to grade per run, writing its start.json and handoff.md from the previous segment."""
import json, glob, os

here = os.path.dirname(os.path.abspath(__file__))
for run in sorted(glob.glob(f"{here}/run-*")):
    segs = sorted(glob.glob(f"{run}/seg-*"), key=lambda p: int(p.rsplit("-", 1)[1]))
    for k, s in enumerate(segs):
        if os.path.exists(f"{s}/labels.json"):
            continue
        if k:
            prev = json.load(open(f"{segs[k-1]}/labels.json", encoding="utf-8"))
            start = {r: dict(v) for r, v in prev[-1]["labels"].items()}
            before = json.load(open(f"{segs[k-1]}/start.json", encoding="utf-8")) if os.path.exists(f"{segs[k-1]}/start.json") else {}
            for r in start:  # last evidence note per rule
                notes = [x["labels"][r].get("note") for x in prev if (x["labels"][r].get("note") or "").strip()]
                start[r]["note"] = notes[-1] if notes else (before.get(r) or {}).get("note", "")
            json.dump(start, open(f"{s}/start.json", "w", encoding="utf-8"), indent=1)
            if os.path.exists(f"{segs[k-1]}/handoff.md"):
                open(f"{s}/handoff.md", "w", encoding="utf-8").write(open(f"{segs[k-1]}/handoff.md", encoding="utf-8").read())
        print(os.path.relpath(s, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))).replace("\\", "/"))
        break
