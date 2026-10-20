"""One PuzzleScript game, played by a coding agent that drives the game itself (frameworks.harness2.player)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from harness2.core import context, tree
from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
from harness2.substrate.opencode import OpencodeSubstrate, render_events

from frameworks.harness2.render import render_workspace


def read_result(run_dir: Path) -> dict | None:
    try:
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        if (result.get("status") == "completed"
                and isinstance(result.get("levels_completed"), int)
                and isinstance(result.get("action_count"), int)):
            return result
    except (OSError, ValueError, AttributeError):
        pass
    return None


def run_player(argv: list[str], run_dir: Path, timeout: int | None) -> None:
    with (run_dir / "player.log").open("w", encoding="utf-8") as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)


class PuzzleScriptAdapter:
    def __init__(self, spec: dict, root: Path, *, player=run_player):
        self.run_spec, self.root, self.player = spec, Path(root), player
        self.substrate = OpencodeSubstrate()
        channel = ChannelSpec("opencode", spec["optimizer_model"], effort=spec["optimizer_effort"], steps=120,
                              timeout=spec["max_wall_seconds"] or 3600)
        self.spec = BenchSpec(
            name="puzzlescript", runs_root=self.root / "rollouts", install_mode="workspace_agents_md",
            prompts=BenchPrompts(
                work="play an unfamiliar puzzle game through a command-line game tool, in a working folder that persists",
                domain_word="puzzle mechanics", deliverable_word="environment model",
                yardstick="Complete more levels; on a tie, use fewer game actions.",
                inv_levers="Improve observation, hypothesis tracking, notes, helper scripts that call `python game.py`, "
                           "planning, and recovery from dead ends.",
                dom_levers="Use the observed transitions to learn this game's objects, controls, and goals.",
                domain_guidance="Each trajectory begins with the run's levels completed and actions used. "
                                "Use these outcomes when comparing approaches. The player works in one session and "
                                "one folder for the whole run, plays only through `python game.py look | do ACTION | "
                                "reset`, and finds the harness files in that folder at the start.",
            ),
            channels={"proposer": channel, "selector": channel}, allow_subagents=True,
        )
        tree.write_tree(self.substrate.surface(), {}, self.base_harness())

    def tasks(self, split: str = "all") -> list[str]:
        return [self.run_spec["game_id"]]

    def domain_of(self, task_id: str) -> str:
        return "puzzlescript"

    def task_prompt(self, task_id: str) -> str:
        return ("Play the unknown puzzle game with `python game.py` in your working folder. "
                "Complete as many levels as possible within the game action budget.")

    def task_files(self, task_id: str) -> None:
        return None

    def base_harness(self) -> Path:
        return self.root / "base"

    def validate_tree(self, harness: dict[str, str]) -> None:
        surface = self.substrate.surface()
        bad = [name for name in harness if not tree.is_allowed(surface, name)]
        if bad:
            raise ValueError(f"Files outside the harness surface: {', '.join(bad)}")
        tree.validate(surface, harness, allow_subagents=self.spec.allow_subagents)
        context.assert_tree_has_no_grader_verdicts(harness)

    def execute(self, task_id: str, harness_dir: Path | None, run_id: str, *, timeout: int | None = None) -> Path:
        if task_id != self.run_spec["game_id"] or not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise ValueError("Unknown task or invalid run id")
        run_dir = self.spec.runs_root / run_id
        if read_result(run_dir) is not None:
            return run_dir
        # A killed player cannot resume its in-memory game. Retry only that rollout
        # from a fresh session, without appending to the interrupted transcript.
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True)
        source = harness_dir or self.base_harness()
        self.validate_tree(tree.read_tree(self.substrate.surface(), source))
        install = self.substrate.materialise(source, self.spec, {})
        try:
            seed = render_workspace(install.staging_dir, run_dir / "seed")
        finally:
            shutil.rmtree(install.staging_dir)
        spec = self.run_spec
        argv = [sys.executable, "-m", "frameworks.harness2.player", "--harness", "opencode"]
        for key in ("model", "effort", "game_id", "backend_url", "provider", "max_wall_seconds"):
            argv += ["--" + key.replace("_", "-"), str(spec[key])]
        argv += ["--max-steps", str(spec["options"]["max_steps"]), "--output-dir", str(run_dir),
                 "--harness-dir", str(seed)]
        self.player(argv, run_dir, timeout)
        if read_result(run_dir) is None:
            raise RuntimeError(f"Player did not finish: {run_dir}")
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        return read_result(run_dir) is not None

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        result = read_result(run_dir)
        if result is None:
            raise ValueError("No completed player result")
        total = result.get("win_levels", result.get("total_levels"))
        text = [f"Outcome of this run: completed {result['levels_completed']} of {total if total is not None else 'unknown'} "
                f"levels in {result['action_count']} game actions (ended: {result.get('reason', 'unknown')})."]
        # The player's OpenCode session: its reasoning, its game.py calls and their printed results.
        for raw in sorted((run_dir / "raw").glob("turn-*.jsonl"),
                          key=lambda p: int(p.stem.split("-")[-1])):
            text.append(render_events(raw, obs_trunc=obs_trunc, max_chars=sys.maxsize))
        return "\n\n".join(text)

    def deliverable_text(self, run_dir: Path) -> str:
        # Only the player's own environment-model report, never controller metrics.
        path = run_dir / "world_model.md"
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        text = self.deliverable_text(run_dir)
        return {"world_model.md": text} if text else {}

    def score(self, run_dir: Path, task_id: str) -> dict | None:
        return read_result(run_dir)
