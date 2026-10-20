"""Score-aware recursion, adoption from every rollout, and one independent final run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness2.core import recursion, tree
from harness2.core.ledger import Ledger
from harness2.core.spec import RunView

from frameworks.harness2.adapter import PuzzleScriptAdapter, read_result
from frameworks.harness2.framework import HARNESS2, check_restart
from frameworks.harness2.proposer import InstalledProposer

UPSTREAM_COMMIT = "1cfe254e8d25b15f37048c3730134686abe60335"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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


def run(spec: dict, root: Path, *, resume: bool = False, adapter=None, proposer=None) -> dict:
    if spec["harness"] != "opencode":
        raise ValueError("Harness² requires --harness opencode for both player and improver")
    root.mkdir(parents=True, exist_ok=True)
    config = root / "harness2_config.json"
    if config.exists():
        if not resume:
            raise ValueError("Existing Harness² run: use --resume")
        check_restart(spec, root)
    write_json(config, spec)
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
    args = vars(parser.parse_args(argv))
    root, resume = args.pop("output_dir"), args.pop("resume")
    args["options"] = HARNESS2.check_options({key: args.pop(key) for key in ("k", "recursion", "max_steps")})
    result = run(args, root.resolve(), resume=resume)
    print(f"levels_completed={result['levels_completed']} adopted={result['adopted_label']} final={result['final_run']}")


if __name__ == "__main__":
    main()
