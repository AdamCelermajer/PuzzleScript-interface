import json
import subprocess
import sys


def run(plan):
    start_level = None
    for i, action in enumerate(plan, 1):
        reason = f"Execute verified offline Sokoban BFS plan step {i}/{len(plan)} from the currently observed state."
        p = subprocess.run(
            [sys.executable, "avo_tool.py", "probe", action, "--rationale", reason],
            text=True,
            capture_output=True,
            check=True,
        )
        d = json.loads(p.stdout)
        t = d["transition"]
        after = t["after"]
        progress = after.get("progress") or {}
        if start_level is None:
            # The before level is authoritative for detecting the boundary.
            start_level = (t.get("before", {}).get("progress") or {}).get("levels_completed", 0)
        frame = after.get("payload", {}).get("frame") or []
        grid = "/".join("".join(map(str, row)) for row in frame[-1]) if frame else ""
        print(json.dumps({
            "i": i,
            "sequence": t.get("sequence"),
            "action": action,
            "grid": grid,
            "status": after.get("status"),
            "progress": progress,
            "remaining": (d.get("budgets") or {}).get("environment_steps_remaining"),
        }, separators=(",", ":")), flush=True)
        if after.get("status") != "PLAYING" or progress.get("levels_completed", 0) > start_level:
            break


if __name__ == "__main__":
    run(json.loads(sys.argv[1]))
