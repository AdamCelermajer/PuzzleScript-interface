import json, subprocess, sys

for action in sys.argv[1:]:
    p = subprocess.run([sys.executable, "avo_tool.py", "probe", action,
                        "--rationale", "Execute a planned move and inspect the resulting board."],
                       capture_output=True, text=True)
    if p.returncode:
        print(p.stdout, p.stderr)
        raise SystemExit(p.returncode)
    d = json.loads(p.stdout)
    tr = d["transition"]
    aft = tr["after"]
    frames = aft.get("payload", {}).get("frame", [])
    board = frames[-1] if frames else []
    print(f'{tr["sequence"]}: {action} status={aft["status"]} progress={aft.get("progress")}')
    for row in board:
        print(" ".join(map(str,row)))
    print()
    if d.get("task", {}).get("terminal"):
        break
