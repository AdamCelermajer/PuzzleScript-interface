"""Per-level moves of an agent-driven player, split into moves typed by hand and moves made by its own scripts.

Each recorded transition is matched to the shell command running at that second. A command is
"by hand" when it is a plain `python game.py do|reset` call; anything else that made moves (its own
solver, a replay script) counts as "script". Also lists the scripts it wrote that called game.py.

    uv run python -m studies.thursday.premise_moves output/workbench/<job>/run-NNNN/rollouts/base1
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MANUAL = re.compile(r"^\s*(cd [^;&]+(&&|;)\s*)?python3? game\.py (do|reset)\b[^|;&]*$")


def commands(run: Path) -> list[tuple[float, float, str]]:
    rows = []
    for path in sorted((run / "raw").glob("turn-*.jsonl"), key=lambda p: int(p.stem.split("-")[1])):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            part = event.get("part") or {}
            if event.get("type") != "tool_use" or part.get("tool") != "bash":
                continue
            state = part.get("state") or {}
            span = state.get("time") or {}
            if span.get("start") and span.get("end"):
                rows.append((span["start"] / 1000, span["end"] / 1000, str((state.get("input") or {}).get("command") or "")))
    return sorted(rows, key=lambda row: row[1])


def main(run_dir: str) -> None:
    run = Path(run_dir)
    spans = commands(run)
    levels: dict[int, dict] = {}
    for line in (run / "transitions.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        second = datetime.fromisoformat(t["timestamp"]).replace(tzinfo=timezone.utc).timestamp()
        # OpenCode stamps a command's start and end when it reports it, so a move belongs to the
        # first command that finished at or after that second.
        owner = next((c for s, e, c in spans if e + 1 >= second), "")
        kind = "hand" if MANUAL.match(owner.strip()) else "script" if owner else "unmatched"
        level = t["before"]["levels_completed"] + 1
        row = levels.setdefault(level, {"moves": 0, "hand": 0, "script": 0, "unmatched": 0, "won_at": None})
        row["moves"] += 1
        row[kind] += 1
        if t["after"]["levels_completed"] > t["before"]["levels_completed"]:
            row["won_at"] = t["action_index"]
    print(f"{run}")
    print("level  moves  by-hand  by-script  unmatched  won-at")
    for level, row in sorted(levels.items()):
        print(f"{level:5d}  {row['moves']:5d}  {row['hand']:7d}  {row['script']:9d}  {row['unmatched']:9d}  {row['won_at']}")
    scripts = sorted({c.split()[1] for _, _, c in spans if re.match(r"\s*python3? (?!game\.py)\S+\.py", c)})
    print("own scripts run:", ", ".join(scripts[:15]))


if __name__ == "__main__":
    main(sys.argv[1])
