"""Belief checkpoints and blind grading folders for the 800-move vast.ai runs of 5 Nov 2026.

The same method as docs/research/rule-learning-20261028/checkpoints.py (every 25 moves, every level, every notebook
version, the run end, extra ones inside more than 100k characters of thinking; segments of at most 280k characters),
with two changes: since 2 Nov the player keeps any files it likes, so the "notebook" is all its files, from the
record in agent_files/; and a run that was resumed is one game over several folders, with a marker where its
conversation ended.

Run from the repo root: uv run python docs/research/rule-learning-vast-20261105/prepare.py LETTER FOLDER [FOLDER...]
Folders go in order, parent first. The key goes to output/vast/rule-grading-key.json, outside what graders read.
"""
import bisect
import datetime
import glob
import json
import os
import re
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(os.path.dirname(here), "rule-learning-20261028")
MAX_CHARS = 280_000
SPLIT = 100_000
EVERY = 25
SCRIPT_LIMIT = 6000  # a player's script tells what it believes; a long one need not be there whole
KEY = "output/vast/rule-grading-key.json"


def _utc(text):
    value = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.timestamp()


def thinking(folder):
    out = []
    for path in glob.glob(f"{folder}/raw/turn-*.jsonl"):
        for line in open(path, encoding="utf-8"):
            if '"type":"reasoning"' not in line:
                continue
            event = json.loads(line)
            text = (event.get("part") or {}).get("text") or ""
            if text.strip():
                out.append((event["timestamp"] / 1000, text))
    return out


def counters(folder):
    steps, tools = [], []
    for path in glob.glob(f"{folder}/raw/turn-*.jsonl"):
        for line in open(path, encoding="utf-8"):
            event = json.loads(line)
            part = event.get("part") or {}
            if event["type"] == "step_finish":
                tokens = part.get("tokens") or {}
                steps.append((event["timestamp"] / 1000, (tokens.get("output") or 0) + (tokens.get("reasoning") or 0)))
            if event["type"] == "tool_use" and part.get("type") == "tool":
                tools.append((((part.get("state") or {}).get("time") or {}).get("end") or event["timestamp"]) / 1000)
    return steps, tools


def notebook_versions(folders):
    """(time, text of all the player's files at that time), one per moment any file changed."""
    current, versions = {}, []
    for folder in folders:
        index = f"{folder}/agent_files/index.jsonl"
        if not os.path.isfile(index):
            continue
        rows = [json.loads(line) for line in open(index, encoding="utf-8")]
        for row in rows:
            name = re.sub(r"^notes/", "", row["path"])
            if row["status"] == "deleted" or not row.get("file"):
                current.pop(name, None)
            else:
                try:
                    text = open(f"{folder}/agent_files/{row['file']}", encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):
                    continue
                if not name.endswith((".md", ".txt")) and len(text) > SCRIPT_LIMIT:
                    text = text[:SCRIPT_LIMIT] + "\n[... the rest of this script is cut here]"
                current[name] = text
            whole = "\n\n".join(f"### File: {k}\n\n{current[k]}" for k in sorted(current))
            when = _utc(row["t"])
            if versions and versions[-1][0] == when:
                versions[-1] = (when, whole)
            elif not versions or versions[-1][1] != whole:
                versions.append((when, whole))
    return versions


def build(folders):
    last = folders[-1]
    config = json.load(open(f"{last}/run_config.json", encoding="utf-8"))
    transitions = [json.loads(line) for line in open(f"{last}/transitions.jsonl", encoding="utf-8")]
    moves = [_utc(item["timestamp"]) for item in transitions]
    levelups = [(i, item["after"]["levels_completed"]) for i, item in enumerate(transitions, 1)
                if item["after"]["levels_completed"] > item["before"]["levels_completed"]]
    th = sorted(sum((thinking(folder) for folder in folders), []))
    restarts = []
    for folder in folders[1:]:
        own = sorted(thinking(folder))
        if own:
            restarts.append(own[0][0] - 0.001)
    steps, tools = [], []
    for folder in folders:
        s, t = counters(folder)
        steps += s
        tools += t
    versions = notebook_versions(folders)
    start = min(moves[:1] + [t for t, _ in th])
    end = max(moves[-1:] + [t for t, _ in th])
    cps = [(moves[n - 1] + 0.999, "moves") for n in range(EVERY, len(moves) + 1, EVERY)]
    cps += [(moves[n - 1] + 0.999, f"level {level} completed") for n, level in levelups]
    cps += [(when, "notebook") for when, _ in versions]
    cps += [(when, "the conversation restarted") for when in restarts]
    cps.append((end + 1, "run end"))
    cps.sort()
    merged = []
    for when, why in cps:
        if merged and when - merged[-1]["t"] < 1.0:
            merged[-1]["why"].add(why)
            merged[-1]["t"] = max(merged[-1]["t"], when)
        else:
            merged.append({"t": when, "why": {why}})
    extra, previous = [], -1e18
    for item in merged:
        size = 0
        for when, text in th:
            if previous < when <= item["t"]:
                size += len(text)
                if size > SPLIT:
                    extra.append({"t": when, "why": {"thinking"}})
                    size = 0
        previous = item["t"]
    merged = sorted(merged + extra, key=lambda item: item["t"])
    out, previous, previous_text = [], -1e18, None
    times = [when for when, _ in versions]
    for k, item in enumerate(merged):
        t = item["t"]
        i = bisect.bisect_right(times, t + 0.001) - 1
        text = versions[i][1] if i >= 0 else None
        chunk = [(when, x) for when, x in th if previous < when <= t]
        done = bisect.bisect_right(moves, t)
        out.append({"cp": k, "t": t, "why": sorted(item["why"]), "actions": done,
                    "levels": max([level for n, level in levelups if n <= done] or [0]), "minutes": round((t - start) / 60, 2),
                    "gen_tokens": sum(n for when, n in steps if when <= t), "tool_calls": sum(1 for when in tools if when <= t),
                    "notebook_changed": text != previous_text, "notebook": text,
                    "restart": any(previous < when <= t for when in restarts),
                    "thinking": [(bisect.bisect_right(moves, when), x) for when, x in chunk]})
        previous, previous_text = t, text
    return {"game": config["game_id"], "driver": config.get("driver") or "controller", "folders": folders,
            "levelups": levelups, "win_levels": transitions[-1]["after"]["win_levels"], "moves": len(moves), "checkpoints": out}


def render(c):
    lines = [f"# Checkpoint {c['cp']:03d} — after {c['actions']} game moves", ""]
    if c["restart"]:
        lines += ["(The model's conversation ended here and a new one began. It was told so; it kept its files and the game "
                  "position, but not its thinking so far. Beliefs it does not restate are no longer in its mind, so apply "
                  "persistence only to what its files still say or what it states again.)", ""]
    if c["notebook"] is None:
        lines += ["## Notebook (the player's files)", "", "(no files written yet)", ""]
    elif c["notebook_changed"]:
        lines += ["## Notebook (the player's files) — NEW VERSION, written at the end of this window", "", c["notebook"], ""]
    else:
        lines += ["## Notebook (the player's files)", "", "(unchanged since the previous checkpoint; older than the thinking below)", ""]
    lines += ["## Thinking written since the previous checkpoint", ""]
    if not c["thinking"]:
        lines.append("(none)")
    for n, text in c["thinking"]:
        lines += [f"--- [after {n} moves]", text.strip(), ""]
    return "\n".join(lines) + "\n"


def main():
    letter, folders = sys.argv[1], sys.argv[2:]
    rules = json.load(open(f"{OLD}/rules.json", encoding="utf-8"))
    d = build(folders)
    root = f"{here}/grade/run-{letter}"
    if os.path.isdir(root) and glob.glob(f"{root}/seg-*/labels.json"):
        raise SystemExit(f"{root} already has labels")
    shutil.rmtree(root, ignore_errors=True)
    segs, cur, size = [], [], 0
    for c in d["checkpoints"]:
        s = len(render(c))
        if cur and size + s > MAX_CHARS:
            segs.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += s
    segs.append(cur)
    for k, seg in enumerate(segs):
        path = f"{root}/seg-{k}"
        os.makedirs(path)
        json.dump([{"id": x["id"], "rule": x["rule"]} for x in rules[d["game"]]], open(f"{path}/rules.json", "w", encoding="utf-8"), indent=1)
        for c in seg:
            open(f"{path}/cp-{c['cp']:03d}.md", "w", encoding="utf-8").write(render(c))
    meta = {"checkpoints": [{k: v for k, v in c.items() if k not in ("notebook", "thinking")} | {"thinking_chars": sum(len(x) for _, x in c["thinking"])}
                            for c in d["checkpoints"]], "segments": [[c["cp"] for c in seg] for seg in segs]}
    os.makedirs("output/vast", exist_ok=True)
    key = json.load(open(KEY, encoding="utf-8")) if os.path.isfile(KEY) else {}
    key[letter] = {k: v for k, v in d.items() if k != "checkpoints"} | meta
    json.dump(key, open(KEY, "w", encoding="utf-8"), indent=1)
    print(letter, d["game"], d["driver"], d["moves"], "moves", len(d["checkpoints"]), "checkpoints", len(segs), "segments",
          sum(len(render(c)) for c in d["checkpoints"]) // 1000, "k chars, restarts", sum(c["restart"] for c in d["checkpoints"]))


if __name__ == "__main__":
    main()
