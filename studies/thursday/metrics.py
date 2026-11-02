"""One row per Modality run: when each level was completed, extra moves over the optimum,
blocked moves by cause, undo, turns, wall time, tokens and cost; then one row per arm.

A run folder is any folder with transitions.jsonl (a Baseline agent run, or a Harness² rollout
such as .../rollouts/base1). A folder without one is searched for run folders below it.

    python -m studies.thursday.metrics RUN_OR_JOB [...] [--label 'GLOB=ARM' ...] [--out DIR]

--label renames the arm of every run whose path matches GLOB (fnmatch on the posix path; first
match wins), e.g. --label '*/rollouts/base1=plain' --label '*/rollouts/*=flash coach'.
"""
from __future__ import annotations

import argparse
import ast
import csv
import fnmatch
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np

from studies.thursday.modality import BLOCKED, ROOT, levels, load_transitions, optimum_moves, replay

OUT = ROOT / "output" / "thursday"
# NanoGPT prices, USD per million tokens: (fresh input, output incl. reasoning, cached input).
PRICES = {
    "qwen3.8-27b": (0.15, 0.7, 0.04),
    "gpt-6-luna": (0.1, 0.5, 0.01),
    "qwen3.8-flash": (0.14, 0.42, 0.14),  # no cached price known: billed as fresh input
    "qwen3.8-max": (2.0, 6.0, 0.25),
}
LEVELS = len(levels())


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def find_runs(paths: list[Path]) -> list[Path]:
    runs: list[Path] = []
    for path in paths:
        if (path / "transitions.jsonl").is_file():
            runs.append(path)
        else:
            runs += sorted(p.parent for p in path.rglob("transitions.jsonl") if "workspace" not in p.parts)
    return list(dict.fromkeys(runs))


def parse_labels(pairs: list[str]) -> list[tuple[str, str]]:
    return [tuple(pair.split("=", 1)) for pair in pairs]  # type: ignore[misc]


def driver_of(config: dict) -> str:
    """Who drove the game: agent runs record it; Harness² rollouts say "player"; controller runs neither."""
    return str(config.get("driver") or ("agent" if config.get("player") else "controller"))


def arm_of(run: Path, config: dict, labels: list[tuple[str, str]]) -> str:
    for pattern, label in labels:
        if fnmatch.fnmatch(run.as_posix(), pattern):
            return label
    if run.parent.name == "rollouts":
        return f"h2 {run.name}"
    model = str(config.get("model", "")).split("/")[-1]
    parts = [config.get("harness", ""), model, driver_of(config)]
    if config.get("notes"):
        parts.append("notes")
    if config.get("start"):
        parts.append(f"start={Path(str(config['start'])).name}")
    return " ".join(p for p in parts if p)


# -- counters -------------------------------------------------------------------------------
def text_tool_calls(run: Path, events: list[dict]) -> int:
    """Tool calls that came back as plain text (Qwen's native <tool_call> / <function= format)."""
    return sum((e.get("text") or "").count("<tool_call>") + (e.get("text") or "").count("<function=")
               for e in events if e.get("type") in ("message", "reasoning"))


# Harness-specific counters, name -> f(run folder, agent events); add more here.
COUNTERS: dict[str, Callable[[Path, list[dict]], int]] = {"text_tool_calls": text_tool_calls}


def usage(events: list[dict]) -> dict[str, int]:
    """Token totals: every usage event, plus turn_end usage for turns that had no usage event."""
    totals = dict.fromkeys(("input", "cached", "output", "reasoning"), 0)
    seen = set()
    entries = []
    for e in events:
        if e.get("type") == "usage":
            seen.add((e.get("session"), e.get("turn")))
            entries.append(e.get("usage"))
    entries += [e.get("usage") for e in events
                if e.get("type") == "turn_end" and (e.get("session"), e.get("turn")) not in seen]
    for value in entries:
        if isinstance(value, str):
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                continue
        if isinstance(value, dict):
            for key in totals:
                totals[key] += int(value.get(key) or 0)
    return totals


def cost(model: str, tokens: dict[str, int]) -> float | None:
    price = next((p for key, p in PRICES.items() if key in model), None)
    if price is None:
        return None
    fresh, out, cached = price
    return (tokens["input"] * fresh + tokens["cached"] * cached + (tokens["output"] + tokens["reasoning"]) * out) / 1e6


def wall_minutes(events: list[dict]) -> float | None:
    times = []
    for e in events:
        try:
            times.append(datetime.fromisoformat(str(e["t"]).replace("Z", "+00:00")))
        except (KeyError, ValueError):
            continue
    return round((max(times) - min(times)).total_seconds() / 60, 1) if times else None


# -- one run --------------------------------------------------------------------------------
def run_row(run: Path, labels: list[tuple[str, str]] | None = None) -> dict:
    config, result = read_json(run / "run_config.json"), read_json(run / "result.json")
    transitions = load_transitions(run)
    events = read_jsonl(run / "agent_events.jsonl")
    steps = replay([t["action"] for t in transitions])
    best = optimum_moves()
    row: dict = {"run": run.relative_to(ROOT).as_posix() if run.is_relative_to(ROOT) else run.as_posix(),
                 "arm": arm_of(run, config, labels or []), "harness": config.get("harness", ""),
                 "model": config.get("model", ""), "driver": driver_of(config),
                 "start": config.get("start", ""), "status": result.get("status", "running"),
                 "reason": result.get("reason", ""), "actions": len(transitions)}
    level_at = [t["action_index"] for t in transitions
                if t["after"]["levels_completed"] > t["before"]["levels_completed"]]
    row["levels"] = len(level_at)
    previous = 0
    for k in range(LEVELS):
        at = level_at[k] if k < len(level_at) else None
        row[f"L{k + 1}_at"] = at if at is not None else ""
        row[f"L{k + 1}_extra"] = (at - previous - best[k]) if at is not None else ""
        previous = at if at is not None else previous
    row["moves_L1_3"] = level_at[2] if len(level_at) >= 3 else ""
    row["finished_L3"] = len(level_at) >= 3
    for k in range(LEVELS):
        in_level = [s for s in steps if s.level == k]
        row[f"noop_L{k + 1}"] = sum(s.kind in BLOCKED for s in in_level)
        row[f"white_dark_L{k + 1}"] = sum(s.kind == "white_dark" for s in in_level)
        row[f"wrong_push_L{k + 1}"] = sum(s.kind == "wrong_floor_push" for s in in_level)
        row[f"edge_L{k + 1}"] = sum(s.kind in ("edge", "push_edge") for s in in_level)
    row["undo"] = sum(s.action == "ACTION7" for s in steps)
    row["resets"] = sum(s.action == "RESET" for s in steps)
    row["agent_turns"] = result.get("agent_turns", "")
    row["wall_min"] = wall_minutes(events) or ""  # whole session, including the end-of-run reports
    stamps = [datetime.fromisoformat(t["timestamp"]) for t in transitions if t.get("timestamp")]
    row["play_min"] = round((max(stamps) - min(stamps)).total_seconds() / 60, 1) if stamps else ""
    tokens = usage(events)
    row.update({f"{key}_tokens": value for key, value in tokens.items()})
    spent = cost(str(row["model"]), tokens)
    row["cost_usd"] = round(spent, 3) if spent is not None else ""
    row["error"] = (result.get("error") or "")[:160]
    row["error_events"] = sum(e.get("type") == "error" for e in events)
    for name, counter in COUNTERS.items():
        row[name] = counter(run, events)
    return row


def arm_rows(rows: list[dict]) -> list[dict]:
    out = []
    for arm in sorted({r["arm"] for r in rows}):
        group = [r for r in rows if r["arm"] == arm]
        done = np.array([r["moves_L1_3"] for r in group if r["finished_L3"]], dtype=float)
        costs = [r["cost_usd"] for r in group if r["cost_usd"] != ""]
        out.append({"arm": arm, "n": len(group), "finished_L3": len(done),
                    "mean": round(float(done.mean()), 1) if len(done) else "",
                    "sd": round(float(done.std(ddof=1)), 1) if len(done) > 1 else "",
                    "min": int(done.min()) if len(done) else "", "max": int(done.max()) if len(done) else "",
                    "unfinished_actions": " ".join(str(r["actions"]) for r in group if not r["finished_L3"]),
                    "mean_cost_usd": round(sum(costs) / len(costs), 3) if costs else ""})
    return out


def markdown(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for _, title in columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(key, "")) for key, _ in columns) + " |")
    return "\n".join(lines)


RUN_COLUMNS = [("arm", "arm"), ("run_name", "run"), ("levels", "levels"), ("level_times", "L1/L2/L3/L4 at"),
               ("extras", "extra L1/L2/L3"), ("moves_L1_3", "moves L1–3"), ("noops", "blocked"),
               ("white_dark", "white↔dark"), ("wrong_push", "wrong-floor push"), ("undo", "undo"),
               ("agent_turns", "turns"), ("play_min", "play min"), ("cost_usd", "cost $"),
               ("reason", "ended"), ("text_tool_calls", "text tool calls")]
ARM_COLUMNS = [("arm", "arm"), ("n", "n"), ("finished_L3", "finished L1–3"), ("mean", "mean moves L1–3"),
               ("sd", "sd"), ("min", "min"), ("max", "max"), ("unfinished_actions", "unfinished (actions used)"),
               ("mean_cost_usd", "mean cost $")]


def display(row: dict) -> dict:
    view = dict(row, run_name=Path(row["run"]).name)
    view["level_times"] = "/".join(str(row[f"L{k}_at"]) or "–" for k in range(1, LEVELS + 1))
    view["extras"] = "/".join(f"{row[f'L{k}_extra']:+d}" if row[f"L{k}_extra"] != "" else "–" for k in range(1, 4))
    for key in ("noop", "white_dark", "wrong_push"):
        view["noops" if key == "noop" else key] = sum(row[f"{key}_L{k}"] for k in range(1, LEVELS + 1))
    return view


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--label", action="append", default=[], help="GLOB=ARM, repeatable")
    parser.add_argument("--out", type=Path, default=OUT / "metrics")
    args = parser.parse_args(argv)
    labels = parse_labels(args.label)
    rows = [run_row(run.resolve(), labels) for run in find_runs(args.paths)]
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    arms = arm_rows(rows)
    with (args.out / "arms.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(arms[0]))
        writer.writeheader()
        writer.writerows(arms)
    opt = optimum_moves()
    text = (f"Optimum moves per level: {'/'.join(map(str, opt))} (levels 1–3: {sum(opt[:3])}).\n\n"
            + markdown([display(r) for r in sorted(rows, key=lambda r: (r["arm"], r["run"]))], RUN_COLUMNS)
            + "\n\n" + markdown(arms, ARM_COLUMNS) + "\n")
    (args.out / "runs.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {args.out / 'runs.csv'}, {args.out / 'arms.csv'}, {args.out / 'runs.md'}")


if __name__ == "__main__":
    main()
