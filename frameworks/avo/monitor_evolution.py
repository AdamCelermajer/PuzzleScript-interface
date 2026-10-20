from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _event_stats(path: Path) -> dict[str, Any]:
    events = _read_events(path)
    transitions = [event for event in events if event.get("type") == "transition"]
    levels = []
    for event in transitions:
        try:
            levels.append(
                int(event["payload"]["after"]["progress"]["levels_completed"])
            )
        except (KeyError, TypeError, ValueError):
            pass
    return {
        "actions": len(transitions),
        "levels": max(levels, default=0),
        "events": len(events),
        "last_event": str(events[-1].get("type", "")) if events else "",
    }


def evolution_snapshot(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    config = _read_json(root / "evolution_config.json")
    lineage = _read_json(root / "lineage.json")
    candidates = lineage.get("candidates", [])
    evaluations = lineage.get("evaluations", [])
    candidate_ids = [
        str(item.get("candidate_id", ""))
        for item in candidates
        if isinstance(item, dict) and item.get("candidate_id")
    ]
    current_id = candidate_ids[-1] if candidate_ids else ""
    current = root / current_id if current_id else root
    research = _event_stats(current / "research" / "evidence.jsonl")
    fresh = _event_stats(current / "evaluation" / "evidence.jsonl")
    summary = _read_json(current / "summary.json")
    solver_evaluation = _read_json(current / "evaluation" / "solver_evaluation.json")
    solver_archived = (current / "solver" / "solver.py").is_file()
    solver_draft = any(
        path.is_file()
        for path in (root / ".sandboxes").glob(
            f"avo-player-{current_id}-*/solver.py"
        )
    ) if current_id else False

    if summary:
        phase = "evaluated"
    elif solver_evaluation:
        phase = "finishing_evaluation"
    elif fresh["events"]:
        phase = "fresh_evaluation"
    elif solver_archived:
        phase = "starting_fresh_evaluation"
    elif research["events"]:
        phase = "research"
    elif current_id:
        phase = "pending"
    else:
        phase = "initializing"

    modified = []
    activity_paths = [
        root / "evolution_config.json",
        root / "lineage.json",
        current / "summary.json",
        current / "research" / "evidence.jsonl",
        current / "evaluation" / "evidence.jsonl",
        current / "evaluation" / "solver_evaluation.json",
        current / "solver" / "solver.py",
    ]
    if current_id:
        activity_paths.extend(
            (root / ".sandboxes").glob(f"avo-player-{current_id}-*/*")
        )
    for path in activity_paths:
        try:
            modified.append(path.stat().st_mtime)
        except OSError:
            pass
    latest_evaluation = evaluations[-1] if evaluations else {}
    return {
        "run_dir": str(root),
        "current": current_id or None,
        "phase": phase,
        "hypotheses_registered": len(candidate_ids),
        "hypotheses_evaluated": len(evaluations),
        "max_hypotheses": config.get("max_evaluations"),
        "research": {
            **research,
            "budget": (config.get("player") or {}).get("max_environment_steps"),
        },
        "solver": {
            "draft_present": solver_draft,
            "archived_present": solver_archived,
        },
        "fresh_evaluation": {
            **fresh,
            "budget": config.get("fresh_solver_max_environment_steps"),
        },
        "latest_fitness": latest_evaluation.get("fitness"),
        "latest_success": latest_evaluation.get("success"),
        "last_activity": (
            datetime.fromtimestamp(max(modified)).isoformat(timespec="seconds")
            if modified
            else None
        ),
    }


def _render(snapshot: dict[str, Any]) -> str:
    research = snapshot["research"]
    fresh = snapshot["fresh_evaluation"]
    solver = snapshot["solver"]
    return "\n".join(
        [
            f"AVO evolution: {snapshot['run_dir']}",
            (
                f"hypothesis: {snapshot['current'] or '-'}  "
                f"phase: {snapshot['phase']}  "
                f"evaluated: {snapshot['hypotheses_evaluated']}/"
                f"{snapshot['max_hypotheses'] or '?'}"
            ),
            (
                f"research: {research['actions']}/{research['budget'] or '?'} actions  "
                f"levels: {research['levels']}  last: {research['last_event'] or '-'}"
            ),
            (
                f"solver.py: draft={'yes' if solver['draft_present'] else 'no'}  "
                f"archived={'yes' if solver['archived_present'] else 'no'}"
            ),
            (
                f"fresh eval: {fresh['actions']}/{fresh['budget'] or '?'} actions  "
                f"levels: {fresh['levels']}  last: {fresh['last_event'] or '-'}"
            ),
            (
                f"latest fitness: {snapshot['latest_fitness']}  "
                f"success: {snapshot['latest_success']}  "
                f"activity: {snapshot['last_activity'] or '-'}"
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor one AVO evolution run")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    while True:
        snapshot = evolution_snapshot(args.run_dir)
        output = json.dumps(snapshot, indent=2) if args.json else _render(snapshot)
        if args.watch:
            print("\033[2J\033[H", end="")
        print(output, flush=True)
        if not args.watch:
            break
        time.sleep(max(0.5, args.interval))


if __name__ == "__main__":
    main()
