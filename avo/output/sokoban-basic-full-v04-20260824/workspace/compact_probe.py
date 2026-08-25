import json
import subprocess
import sys


def main():
    action = sys.argv[1]
    rationale = sys.argv[2] if len(sys.argv) > 2 else "Controlled state-space experiment."
    p = subprocess.run(
        [sys.executable, "avo_tool.py", "probe", action, "--rationale", rationale],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(p.stdout)
    t = data["transition"]
    after = t["after"]
    frame = after.get("payload", {}).get("frame", [])
    grid = frame[-1] if frame else None
    print(json.dumps({
        "sequence": t["sequence"],
        "action": action,
        "grid": grid,
        "status": after.get("status"),
        "progress": after.get("progress"),
        "task": data.get("task"),
        "budgets": data.get("budgets"),
        "evaluations": data.get("evaluations"),
        "supervisor_events": data.get("supervisor_events"),
    }, indent=2))


if __name__ == "__main__":
    main()
