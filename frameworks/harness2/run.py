"""Score-aware recursion, adoption from every rollout, and one independent final run.

With ``levels`` > 0 each level is its own task instead, played in order (``run_levels``).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness2.core import recursion, tree
from harness2.core.ledger import Ledger
from harness2.core.spec import RunView
from harness2.substrate.opencode import OpencodeSubstrate

from frameworks.harness2.adapter import Played, PuzzleScriptAdapter, level_solved, read_result
from frameworks.harness2.framework import HARNESS2, check_restart
from frameworks.harness2.proposer import InstalledProposer
from frameworks.levels import shortest

UPSTREAM_COMMIT = "1cfe254e8d25b15f37048c3730134686abe60335"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def rollout_row(run: RunView) -> dict:
    result = read_result(run.run_dir) if run.ok else None
    return {"label": run.label, "run_id": run.run_id, "run_dir": str(run.run_dir),
            "ok": result is not None, "error": run.error,
            **{key: (result or {}).get(key) for key in
               ("levels_completed", "action_count", "win_levels", "total_levels", "solved", "reason")}}


def adopt(rollouts: dict[str, RunView]) -> RunView:
    eligible = [run for run in rollouts.values() if run.ok and read_result(run.run_dir) is not None]
    if not eligible:
        raise RuntimeError("No completed rollout to adopt")

    def rank(run):
        result = read_result(run.run_dir)
        return (-result["levels_completed"], result["action_count"], not run.label.startswith("base"))

    return min(eligible, key=rank)


def start(spec: dict, root: Path, resume: bool) -> None:
    if spec["harness"] != "opencode":
        raise ValueError("Harness² requires --harness opencode for both player and improver")
    root.mkdir(parents=True, exist_ok=True)
    config = root / "harness2_config.json"
    if config.exists():
        if not resume:
            raise ValueError("Existing Harness² run: use --resume")
        check_restart(spec, root)
    write_json(config, spec)


def run(spec: dict, root: Path, *, resume: bool = False, adapter=None, proposer=None) -> dict:
    start(spec, root, resume)
    adapter = adapter or PuzzleScriptAdapter(spec, root)
    proposer = proposer or InstalledProposer(adapter.spec.channels["proposer"], audit_dir=root / "improver",
                                             pin_provider=spec["provider"])
    task_id, k = spec["game_id"], spec["options"]["k"]
    mode = {"parallel": "agg", "sequential": "seq"}[spec["options"]["recursion"]]
    base_tree = tree.read_tree(adapter.substrate.surface(), adapter.base_harness())
    bases = [recursion._roll(adapter, Ledger(mode=mode, task_id=task_id, k=k), task_id,
                            f"base{i}", None, lambda label: label, root) for i in range(1, k + 1)]
    if not any(run.ok for run in bases):
        raise RuntimeError("No base rollout completed; inspect rollouts/*/player.log")
    evolved = recursion.run_mode(mode, task_id, k, bases, adapter=adapter, prop=proposer,
                                 work_dir=root, run_id_of=lambda label: label, base_tree=base_tree)
    write_json(root / "recursion.json", evolved.to_dict())
    chosen = adopt(evolved.rollouts)
    adopted_tree = base_tree if chosen.label.startswith("base") else evolved.trees[chosen.label]
    adopted_dir = tree.write_tree(adapter.substrate.surface(), adopted_tree, root / "adopted")
    rows = [rollout_row(item) for item in evolved.rollouts.values()]
    selection = {"adopted_label": chosen.label, "base_levels": [read_result(b.run_dir)["levels_completed"]
                  if read_result(b.run_dir) else None for b in bases],
                 "best_of_pool_levels": read_result(chosen.run_dir)["levels_completed"], "rollouts": rows}
    write_json(root / "adoption.json", selection)
    final_dir = adapter.execute(task_id, adopted_dir, "final")
    final = read_result(final_dir)
    if final is None:
        raise RuntimeError("The fresh final rollout did not complete")
    result = {**final, "framework": "harness2", "upstream_commit": UPSTREAM_COMMIT,
              "recursion": spec["options"]["recursion"], "k": k, **selection,
              "final_run": str(final_dir), "improver": evolved.to_dict()}
    write_json(root / "result.json", result)
    return result


# Per-level runs: each level is one task, in rounds at a growing game-action budget. Inside a
# round the labels keep upstream's k=1 names (base1, inv1, dom1, agg1); levels/L<k>/rounds/R<n>/
# holds that round's harnesses, rollouts and coach sessions.
KEEP_SOLVED = ("base", "agg", "inv", "dom")
KEEP_UNSOLVED = ("agg", "inv", "dom", "base")


def parse_budgets(text: str) -> list[int]:
    try:
        budgets = [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        budgets = []
    if not budgets or min(budgets) < 1 or budgets != sorted(budgets):
        raise ValueError("--budgets must be positive integers in increasing order, e.g. 30,50,100,200,500")
    return budgets


def keep(pool: dict[str, RunView]) -> RunView:
    """The round's kept rollout, among those played at the round's budget.

    A solving rollout wins: fewer actions first, then the starting harness. With no solve the
    action count says nothing (stopping early is not progress), so the composer's harness goes on.
    """
    eligible = [run for run in pool.values() if run.ok and read_result(run.run_dir) is not None]
    if not eligible:
        raise RuntimeError("No completed rollout in this round")

    def order(run: RunView, prefixes: tuple[str, ...]) -> tuple[int, str]:
        return prefixes.index(run.label.rstrip("0123456789")), run.label

    solved = [run for run in eligible if level_solved(read_result(run.run_dir))]
    if solved:
        return min(solved, key=lambda run: (read_result(run.run_dir)["action_count"], order(run, KEEP_SOLVED)))
    return min(eligible, key=lambda run: order(run, KEEP_UNSOLVED))


def run_round(spec: dict, rdir: Path, level: int, budget: int, harness: dict[str, str],
              evidence: tuple[RunView, int] | None, played: Played, adapter_factory, proposer_factory
              ) -> tuple[dict, RunView, dict[str, str]]:
    """One coaching cycle at one budget. The level's first round plays base1 from the starting
    harness; a later round's evidence is the previous round's kept rollout, not replayed."""
    adapter = adapter_factory(spec, rdir, level=level, budget=budget, played=played)
    tree.write_tree(adapter.substrate.surface(), harness, adapter.base_harness())
    task_id = spec["game_id"]
    if evidence is None:
        bases = [recursion._roll(adapter, Ledger(mode="agg", task_id=task_id, k=1), task_id, "base1", None,
                                 lambda label: label, rdir)]
        if not bases[0].ok:
            raise RuntimeError(f"The base rollout did not complete: {bases[0].error}")
    else:
        bases = [RunView("base1", evidence[0].run_id, evidence[0].run_dir, ok=True, delivered=True)]
    evolved = recursion.run_mode("agg", task_id, 1, bases, adapter=adapter, prop=proposer_factory(adapter, rdir),
                                 work_dir=rdir, run_id_of=lambda label: label, base_tree=harness)
    write_json(rdir / "recursion.json", evolved.to_dict())
    same_budget = evidence is None or evidence[1] == budget
    chosen = keep({label: item for label, item in evolved.rollouts.items()
                   if same_budget or not label.startswith("base")})
    kept_tree = harness if chosen.label.startswith("base") else evolved.trees[chosen.label]
    result = read_result(chosen.run_dir)
    reused = {}
    for label in evolved.rollouts:
        marker = rdir / "rollouts" / label / "reused.json"
        if marker.is_file():
            reused[label] = json.loads(marker.read_text(encoding="utf-8"))["same_as"]
    row = {"round": rdir.name, "budget": budget, "evidence": str(bases[0].run_dir), "kept": chosen.label,
           "kept_run": str(chosen.run_dir), "solved": level_solved(result), "action_count": result["action_count"],
           "reused": reused, "fell_back": evolved.fell_back,
           "rollouts": [{**rollout_row(item), "level_solved": level_solved(read_result(item.run_dir) or {})}
                        for item in evolved.rollouts.values()]}
    write_json(rdir / "round.json", row)
    return row, chosen, kept_tree


def level_entry(level: int, status: str, rounds: list[dict], index: int, error: str = "") -> dict:
    last = rounds[-1] if rounds else {}
    return {"level": level, "status": status, "solved": bool(last.get("solved")), "rounds": len(rounds),
            "kept": last.get("kept"), "budget": last.get("budget"), "budget_index": index,
            "action_count": last.get("action_count") if last.get("solved") else None,
            "rollouts_reused": sum(len(row["reused"]) for row in rounds), "error": error}


def run_levels(spec: dict, root: Path, *, resume: bool = False, adapter_factory=PuzzleScriptAdapter,
               proposer_factory=None) -> dict:
    """Levels 1..N in order. A level starts from the previous level's kept harness and at the
    budget the previous level ended on. An unsolved round moves on to the next budget (the last
    one repeats) from that round's kept harness, until the level is solved or max_rounds."""
    start(spec, root, resume)
    options = spec["options"]
    if options["recursion"] != "parallel" or options["k"] != 1:
        raise ValueError("Per-level Harness² runs use k=1 with parallel recursion")
    budgets = parse_budgets(options["budgets"])
    proposer_factory = proposer_factory or (lambda adapter, rdir: InstalledProposer(
        adapter.spec.channels["proposer"], audit_dir=rdir / "improver", pin_provider=spec["provider"]))
    surface = OpencodeSubstrate().surface()
    harness: dict[str, str] = {}
    index, rows = 0, []
    for level in range(1, options["levels"] + 1):
        ldir = root / "levels" / f"L{level}"
        saved = read_json(ldir / "result.json")
        if saved.get("status") == "completed":
            rows.append(saved)
            harness, index = tree.read_tree(surface, ldir / "kept"), saved["budget_index"]
            continue
        fewest = shortest(spec["game_id"], level) if options["skip_below_shortest"] else None
        while fewest and index < len(budgets) - 1 and budgets[index] < fewest:
            index += 1
        played, rounds, evidence = Played(ldir), [], None
        try:
            for number in range(1, options["max_rounds"] + 1):
                if number > 1:
                    index = min(index + 1, len(budgets) - 1)
                row, chosen, harness = run_round(spec, ldir / "rounds" / f"R{number}", level, budgets[index],
                                                 harness, evidence, played, adapter_factory, proposer_factory)
                rounds.append(row)
                evidence = (chosen, budgets[index])
                if row["solved"]:
                    break
            entry = level_entry(level, "completed", rounds, index)
        except Exception as exc:  # a broken level is recorded and the next level still runs
            entry = level_entry(level, "error", rounds, index, f"{type(exc).__name__}: {exc}"[:600])
        # The kept harness lands before result.json, so a stop between the two leaves no half level.
        tree.write_tree(surface, harness, ldir / "kept")
        write_json(ldir / "result.json", entry)
        rows.append(entry)
    solved = [row for row in rows if row["solved"]]
    result = {"status": "completed", "framework": "harness2", "upstream_commit": UPSTREAM_COMMIT, "per_level": True,
              "levels_completed": len(solved), "win_levels": options["levels"],
              "solved": len(solved) == options["levels"], "action_count": sum(row["action_count"] for row in solved),
              "levels": rows}
    write_json(root / "result.json", result)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    for key in ("harness", "model", "effort", "optimizer_model", "optimizer_effort", "game_id", "backend_url"):
        parser.add_argument("--" + key.replace("_", "-"), required=True)
    parser.add_argument("--provider", default="")
    parser.add_argument("--max-wall-seconds", type=int, default=0)
    parser.add_argument("--k", type=int, default=1)
    parser.add_argument("--recursion", choices=("parallel", "sequential"), default="parallel")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--stop-after-levels", type=int, default=0)
    parser.add_argument("--levels", type=int, default=0)
    parser.add_argument("--budgets", default="30,50,100,200,500")
    parser.add_argument("--skip-below-shortest", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=5)
    args = vars(parser.parse_args(argv))
    root, resume = args.pop("output_dir"), args.pop("resume")
    args["options"] = HARNESS2.check_options({key: args.pop(key) for key in
                                              ("k", "recursion", "max_steps", "stop_after_levels", "levels",
                                               "budgets", "skip_below_shortest", "max_rounds")})
    if args["options"]["levels"]:
        result = run_levels(args, root.resolve(), resume=resume)
        print(f"levels_completed={result['levels_completed']} of {result['win_levels']}")
        return
    result = run(args, root.resolve(), resume=resume)
    print(f"levels_completed={result['levels_completed']} adopted={result['adopted_label']} final={result['final_run']}")


if __name__ == "__main__":
    main()
