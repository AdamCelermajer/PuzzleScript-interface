"""In-container dispatcher: ``python -m harnesses.entry --spec /results/run_spec.json [--resume]``.

Prepares the harness credentials staged by ``harnesses.launch``, then runs the
campaign (``avo.evolve``) or a direct-play baseline (``studies.codex_agent.run``)
with arguments derived from the run spec.
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

RESULTS = Path("/results")
PARENT = Path("/parent")


def prepare_credentials(harness: str, credentials: Path = Path("/credentials"), home: Path | None = None) -> None:
    home = home or Path(os.environ.get("HOME", str(Path.home())))
    os.environ.setdefault("HARNESS_PRIVATE_ROOT", str(home / ".harness"))
    if harness == "codex":
        codex_home = home / ".codex"
        codex_home.mkdir(parents=True, exist_ok=True)
        source = credentials / "auth.json"
        if not source.is_file():
            raise SystemExit("codex harness: /credentials/auth.json was not staged")
        # Codex refreshes tokens in place, so it needs a writable copy.
        shutil.copyfile(source, codex_home / "auth.json")
        (codex_home / "auth.json").chmod(0o600)
        os.environ["CODEX_HOME"] = str(codex_home)
    if harness == "antigravity":
        from harnesses.antigravity import install_web_deny_hook
        install_web_deny_hook(home / ".gemini")


def campaign_argv(spec: dict[str, Any], resume: bool, results: Path = RESULTS) -> list[str]:
    budget = spec["budget"]
    wall = str(int(budget.get("max_wall_seconds") or 0))
    argv = ["avo.evolve", "--profile", "puzzlescript",
            "--set", f"game_id={spec['game_id']}", "--set", f"backend_url={spec['backend_url']}",
            "--output-dir", str(results / "campaign"), "--harness", spec["harness"],
            "--player-model", spec["model"], "--player-effort", spec["effort"],
            "--optimizer-model", spec.get("optimizer_model") or spec["model"],
            "--optimizer-effort", spec.get("optimizer_effort") or spec["effort"],
            "--world-model-mode", spec.get("world_model_mode") or "final-only",
            "--max-evaluations", str(budget["max_evaluations"]),
            "--player-max-environment-steps", str(budget["research_moves"]),
            "--fresh-solver-max-environment-steps", str(budget["solver_moves"]),
            "--solver-self-check-max-environment-steps", str(budget["solver_moves"]),
            "--max-wall-seconds", wall, "--player-max-wall-seconds", wall,
            "--provider", spec.get("provider") or ""]
    if resume:
        argv.append("--resume-saved-campaign")
    return argv


def baseline_argv(spec: dict[str, Any], results: Path = RESULTS, parent: Path = PARENT) -> list[str]:
    budget = spec["budget"]
    argv = ["studies.codex_agent.run", "--no-window", "--harness", spec["harness"], "--model", spec["model"],
            "--effort", spec["effort"], "--condition", spec["mode"], "--game-id", spec["game_id"],
            "--backend-url", spec["backend_url"], "--max-steps", str(budget["max_steps"]),
            "--max-wall-seconds", str(int(budget.get("max_wall_seconds") or 0)),
            "--output-dir", str(results), "--provider", spec.get("provider") or ""]
    if spec.get("continued_from"):
        argv += ["--continue-from", str(parent)]
    return argv


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--spec", default=str(RESULTS / "run_spec.json"))
    parser.add_argument("--resume", action="store_true")
    options = parser.parse_args(argv)
    spec = json.loads(Path(options.spec).read_text(encoding="utf-8"))
    prepare_credentials(spec["harness"])
    if spec["mode"] == "campaign":
        module_argv = campaign_argv(spec, options.resume)
        campaign = RESULTS / "campaign"
        campaign.mkdir(parents=True, exist_ok=True)
        # The run catalog's campaign artifact is DIR/campaign; it gets the spec too.
        (campaign / "run_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    else:
        module_argv = baseline_argv(spec)
    sys.argv = [module_argv[0], *module_argv[1:]]
    runpy.run_module(module_argv[0], run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
