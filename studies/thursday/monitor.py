"""Live status of a batch of runs on the self-hosted server: speed, problems, progress.

Per run: game actions and levels (all transitions.jsonl below the run), tokens written
(OpenCode step records in raw/turn-*.jsonl), seconds since the last model step, error events,
compactions, world-model copies, and the result when it has finished. Then the vLLM server's own
counters through the tunnel: requests running and waiting, KV cache use, tokens per second since
the previous call (kept in output/thursday/monitor-state.json).

    uv run python -m studies.thursday.monitor output/workbench/<job> [more jobs…]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

METRICS = "http://127.0.0.1:18100/metrics"
STATE = Path("output/thursday/monitor-state.json")


def _lines(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            yield from stream
    except OSError:
        return


def run_status(run: Path) -> dict:
    spec = json.loads((run / "run_spec.json").read_text(encoding="utf-8")) if (run / "run_spec.json").is_file() else {}
    actions = levels = 0
    for path in run.rglob("transitions.jsonl"):
        rows = 0
        for line in _lines(path):
            rows += 1
            match = re.search(r'"after": \{.*?"levels_completed": (\d+)', line)
            if match:
                levels = max(levels, int(match.group(1)))
        actions += rows
    for path in run.rglob("evidence.jsonl"):  # AVO research sessions record their moves here
        for line in _lines(path):
            if '"type": "transition"' in line:
                actions += 1
                for match in re.finditer(r'"levels_completed": (\d+)', line):
                    levels = max(levels, int(match.group(1)))
    written = steps = compactions = 0
    last = 0.0
    for path in run.rglob("raw/turn-*.jsonl"):
        for line in _lines(path):
            if '"step_finish"' in line:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                tokens = (event.get("part") or {}).get("tokens") or {}
                written += int(tokens.get("output") or 0) + int(tokens.get("reasoning") or 0)
                steps += 1
                last = max(last, float(event.get("timestamp") or 0) / 1000)
            elif "compact" in line:
                compactions += 1
    errors = sum(1 for path in run.rglob("agent_events.jsonl") for line in _lines(path) if '"type": "error"' in line)
    result = run / "result.json"
    ended = json.loads(result.read_text(encoding="utf-8")).get("reason") if result.is_file() else ""
    return {"run": f"{spec.get('framework', '?')}/{spec.get('game_id', '?')}", "actions": actions, "levels": levels,
            "steps": steps, "written_k": round(written / 1000), "idle_s": round(time.time() - last) if last else None,
            "errors": errors, "compactions": compactions,
            "wm_copies": len(list(run.rglob("world_model_snapshots/*.md"))), "ended": ended or "running"}


def server_status() -> dict:
    try:
        text = urllib.request.urlopen(METRICS, timeout=10).read().decode()
    except OSError as exc:
        return {"server": f"unreachable ({exc})"}
    def metric(name: str) -> float:
        values = [float(m.group(1)) for m in re.finditer(rf"^{re.escape(name)}(?:{{[^}}]*}})? ([0-9.e+-]+)$", text, re.M)]
        return sum(values)
    now, generated = time.time(), metric("vllm:generation_tokens_total")
    previous = json.loads(STATE.read_text()) if STATE.is_file() else {}
    rate = ((generated - previous["generated"]) / (now - previous["time"])
            if previous.get("time") and now > previous["time"] else None)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"time": now, "generated": generated}))
    return {"running": int(metric("vllm:num_requests_running")), "waiting": int(metric("vllm:num_requests_waiting")),
            "kv_cache_used": f"{100 * metric('vllm:kv_cache_usage_perc'):.0f}%",
            "tokens_per_s_since_last_check": round(rate) if rate is not None else None}


def main(argv: list[str]) -> None:
    runs = sorted(Path(arg) if (Path(arg) / "run_spec.json").is_file() else run for arg in argv
                  for run in ([Path(arg)] if (Path(arg) / "run_spec.json").is_file() else Path(arg).glob("run-*"))
                  if run.is_dir())
    print(f"{'run':40s} {'actions':>7s} {'lvl':>3s} {'steps':>5s} {'written':>8s} {'idle':>6s} {'err':>3s} {'cmp':>3s} {'wm':>3s}  ended")
    for run in runs:
        s = run_status(run)
        print(f"{s['run'][:40]:40s} {s['actions']:7d} {s['levels']:3d} {s['steps']:5d} {str(s['written_k']) + 'k':>8s} "
              f"{str(s['idle_s']) + 's' if s['idle_s'] is not None else '-':>6s} {s['errors']:3d} {s['compactions']:3d} "
              f"{s['wm_copies']:3d}  {s['ended']}")
    print("server:", server_status())


if __name__ == "__main__":
    main(sys.argv[1:])
