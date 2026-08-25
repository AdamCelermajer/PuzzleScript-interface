import json, subprocess, sys

action = sys.argv[1]
rationale = "Systematic single-step navigation using the observed directional mapping and current collision geometry."
p = subprocess.run([sys.executable, "avo_tool.py", "probe", action, "--rationale", rationale], text=True, capture_output=True)
if p.returncode:
    print(p.stdout)
    print(p.stderr, file=sys.stderr)
    raise SystemExit(p.returncode)
j=json.loads(p.stdout)
o=j["transition"]["after"]
print("seq", j["transition"]["sequence"], action, o["status"], o.get("progress"), "task", j["task"])
for fno,g in enumerate(o["payload"]["frame"]):
    if fno==len(o["payload"]["frame"])-1:
        print("\n".join(" ".join(map(str,row)) for row in g))
