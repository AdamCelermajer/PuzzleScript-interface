"""One compact status line for a running batch, plus an ALERT line when something needs attention.

Alerts: a run ended, new error events, a running run idle for over 15 minutes, requests waiting
on the server, or the server unreachable. Error counts are remembered between calls in
output/thursday/monitor-line-state.json.

    uv run python -m studies.thursday.monitor_line output/workbench/<job> [more jobs…]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from studies.thursday.monitor import run_status, server_status

STATE = Path("output/thursday/monitor-line-state.json")
SHORT = {"baseline": "B", "avo": "AVO", "harness2": "H2"}


def main(argv: list[str]) -> None:
    previous = json.loads(STATE.read_text()) if STATE.is_file() else {}
    runs = sorted(Path(arg) if (Path(arg) / "run_spec.json").is_file() else run for arg in argv
                  for run in ([Path(arg)] if (Path(arg) / "run_spec.json").is_file() else Path(arg).glob("run-*"))
                  if run.is_dir())
    parts, alerts, seen = [], [], {}
    for run in runs:
        s = run_status(run)
        framework, game = s["run"].split("/", 1)
        label = f"{SHORT.get(framework, framework)}-{game.removeprefix('ps_').split('-')[0][:4]}"
        parts.append(f"{label} {s['actions']}a/{s['levels']}L/{s['written_k']}k")
        key = str(run)
        seen[key] = {"errors": s["errors"], "ended": s["ended"]}
        before = previous.get(key, {})
        if s["ended"] != "running" and before.get("ended") == "running":
            alerts.append(f"{label} ended: {s['ended']}")
        if s["errors"] > before.get("errors", 0):
            alerts.append(f"{label} +{s['errors'] - before.get('errors', 0)} errors")
        if s["ended"] == "running" and s["idle_s"] is not None and s["idle_s"] > 900:
            alerts.append(f"{label} idle {s['idle_s'] // 60} min")
    server = server_status()
    if "server" in server:
        alerts.append(f"server {server['server']}")
    elif server.get("waiting"):
        alerts.append(f"server: {server['waiting']} requests waiting")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(seen))
    print(time.strftime("%H:%M"), "|", " · ".join(parts), "| server", server, flush=True)
    if alerts:
        print("ALERT:", "; ".join(alerts), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
