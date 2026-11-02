import json, os
here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(f"{here}/versions.json", encoding="utf-8"))
rules = json.load(open(f"{here}/rules.json", encoding="utf-8"))
MAX = 12
tasks = {}
for name, r in data.items():
    v = r["versions"]
    idx = sorted({round(i * (len(v) - 1) / (MAX - 1)) for i in range(MAX)}) if len(v) > MAX else list(range(len(v)))
    for i in idx:
        v[i]["graded"] = True
        vid = f"{name}#{i}"
        tasks.setdefault(r["game"], []).append({"id": vid, "text": v[i]["text"]})
json.dump(data, open(f"{here}/versions.json", "w", encoding="utf-8"), indent=1)
os.makedirs(f"{here}/tasks", exist_ok=True)
for game, items in tasks.items():
    chunks = [items] if len(items) <= 30 else [items[:len(items)//2], items[len(items)//2:]]
    for k, chunk in enumerate(chunks):
        path = f"{here}/tasks/{game}-{k}"
        os.makedirs(path, exist_ok=True)
        json.dump(rules[game], open(f"{path}/rules.json", "w", encoding="utf-8"), indent=1)
        for j, it in enumerate(chunk):
            open(f"{path}/v{j:02d}.md", "w", encoding="utf-8").write(it["text"])
        json.dump({f"v{j:02d}": it["id"] for j, it in enumerate(chunk)}, open(f"{path}/ids.json", "w", encoding="utf-8"), indent=1)
        print(path, len(chunk), sum(len(it["text"]) for it in chunk))
