from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from avo.core.framework import Action, Comparison, Observation
from avo.core.profile import TaskEvaluation
from avo.evolution.candidate import CandidateEvaluation, RunCandidate
from avo.evolution.evaluator import CandidateEvaluator, PlayerEvaluationConfig
from avo.evolution.gateway import EvolutionBudget, EvolutionGateway
from avo.evolution.solver_evaluation import SolverEvaluation, evaluate_solver_workspace
from avo.evolution.store import EvolutionStore
from avo.evolution.tool_server import EvolutionFileToolServer, OPTIMIZER_INTERFACE
from avo.run_once import PlayerRunResult, PlayerRunSettings


class DeterministicEvaluator:
    """Cheap evaluator whose strategy declares the score used by the tests."""

    def evaluate(self, candidate: RunCandidate, run_dir: Path) -> CandidateEvaluation:
        marker = next(
            line for line in candidate.strategy().splitlines() if line.startswith("fitness=")
        )
        fitness = float(marker.partition("=")[2])
        workspace = run_dir / "workspace"
        workspace.mkdir(parents=True)
        prior_notes = ""
        notes = candidate.workspace_path / "NOTES.md"
        if notes.is_file():
            prior_notes = notes.read_text(encoding="utf-8")
        (workspace / "NOTES.md").write_text(
            prior_notes + f"\nlearned by {candidate.candidate_id}\n",
            encoding="utf-8",
        )
        (workspace / "helper.py").write_text(
            f"FITNESS = {fitness}\n",
            encoding="utf-8",
        )
        (run_dir / "final_summary.json").write_text(
            json.dumps({"candidate_id": candidate.candidate_id, "fitness": fitness}),
            encoding="utf-8",
        )
        return CandidateEvaluation(
            evaluation_id=run_dir.name,
            candidate_id=candidate.candidate_id,
            fitness=fitness,
            success=fitness >= 10,
            terminal=fitness >= 10,
            score={"progress": fitness},
            finish_reason="fake evaluation completed",
            environment_steps=1,
            agent_turns=1,
            run_dir=run_dir,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )


class EvolutionTests(unittest.TestCase):
    def test_outer_loop_registers_evaluates_inherits_and_retains_equal_scores(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = EvolutionStore.create(root / "evolution")
            store.create_seed("x_0001", "fitness=4\nuse experiments")
            gateway = EvolutionGateway(
                store,
                DeterministicEvaluator(),
                mission="Improve the player.",
                budget=EvolutionBudget(max_evaluations=3),
            )

            first = gateway.handle("evaluate", {"candidate_id": "x_0001"})
            self.assertEqual(first["evaluation"]["fitness"], 4)
            inspected = gateway.handle("inspect", {"candidate_id": "x_0001"})
            self.assertEqual(inspected["latest_run"]["final_summary"]["fitness"], 4)
            self.assertIn(
                "learned by x_0001",
                inspected["latest_run"]["learned_notes"]["NOTES.md"],
            )
            with self.assertRaisesRegex(ValueError, "already evaluated"):
                gateway.handle("evaluate", {"candidate_id": "x_0001"})

            forked = gateway.handle(
                "fork", {"parent_id": "x_0001", "child_id": "x_0002"}
            )
            second_draft = Path(str(forked["draft_path"]))
            self.assertIn(
                "learned by x_0001",
                (second_draft / "workspace" / "NOTES.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((second_draft / "workspace" / "helper.py").is_file())
            (second_draft / "STRATEGY.md").write_text("fitness=6\nrefined", encoding="utf-8")
            gateway.handle("register", {"candidate_id": "x_0002"})
            (second_draft / "STRATEGY.md").write_text("fitness=999", encoding="utf-8")
            second = gateway.handle("evaluate", {"candidate_id": "x_0002"})
            self.assertEqual(second["evaluation"]["fitness"], 6)

            third_fork = gateway.handle(
                "fork", {"parent_id": "x_0002", "child_id": "x_0003"}
            )
            third_draft = Path(str(third_fork["draft_path"]))
            (third_draft / "STRATEGY.md").write_text("fitness=6\ndifferent", encoding="utf-8")
            gateway.handle("register", {"candidate_id": "x_0003"})
            gateway.handle("evaluate", {"candidate_id": "x_0003"})

            population = store.population_summary()
            self.assertEqual(population["candidate_count"], 3)
            self.assertEqual(population["evaluation_count"], 3)
            self.assertEqual(
                [item["fitness"] for item in population["evaluations"]],
                [4.0, 6.0, 6.0],
            )
            self.assertEqual(population["best"]["candidate_id"], "x_0002")
            self.assertEqual(gateway.handle("status")["finish_reason"], "candidate evaluation budget exhausted")

    def test_optimizer_rpc_exposes_candidate_tools_but_no_gameplay_tools(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = EvolutionStore.create(root / "evolution")
            store.create_seed("x_0001", "fitness=1")
            gateway = EvolutionGateway(
                store,
                DeterministicEvaluator(),
                mission="Improve the player.",
            )
            server = EvolutionFileToolServer(gateway, store.optimizer_workspace)
            server.start()
            try:
                completed = subprocess.run(
                    [sys.executable, "avo_evolve_tool.py", "population"],
                    cwd=store.optimizer_workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            finally:
                server.stop()

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["candidate_count"], 1)
            self.assertIn("fork PARENT_ID CHILD_ID", OPTIMIZER_INTERFACE)
            self.assertNotIn(" probe ", OPTIMIZER_INTERFACE)
            self.assertNotIn("checkpoint", OPTIMIZER_INTERFACE)

    def test_optimizer_rpc_keeps_concurrent_responses_separate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = EvolutionStore.create(root / "evolution")
            store.create_seed("x_0001", "fitness=1")
            gateway = EvolutionGateway(
                store,
                DeterministicEvaluator(),
                mission="Improve the player.",
            )
            population_started = threading.Event()
            original_handle = gateway.handle

            def delayed_handle(method: str, params=None):
                if method == "population":
                    population_started.set()
                    time.sleep(0.25)
                return original_handle(method, params)

            gateway.handle = delayed_handle  # type: ignore[method-assign]
            server = EvolutionFileToolServer(gateway, store.optimizer_workspace)
            server.start()
            try:
                population = subprocess.Popen(
                    [sys.executable, "avo_evolve_tool.py", "population"],
                    cwd=store.optimizer_workspace,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertTrue(population_started.wait(timeout=5))
                status = subprocess.Popen(
                    [sys.executable, "avo_evolve_tool.py", "status"],
                    cwd=store.optimizer_workspace,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                population_stdout, population_stderr = population.communicate(timeout=10)
                status_stdout, status_stderr = status.communicate(timeout=10)
            finally:
                server.stop()

            self.assertEqual(population.returncode, 0, population_stderr)
            self.assertEqual(status.returncode, 0, status_stderr)
            self.assertEqual(json.loads(population_stdout)["candidate_count"], 1)
            self.assertFalse(json.loads(status_stdout)["finished"])

    def test_candidate_evaluator_reloads_profile_for_every_fresh_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            candidate_root = root / "candidate"
            (candidate_root / "workspace").mkdir(parents=True)
            (candidate_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "candidate_id": "x_test",
                        "parent_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            (candidate_root / "STRATEGY.md").write_text("test strategy", encoding="utf-8")
            (candidate_root / "workspace" / "NOTES.md").write_text("seed", encoding="utf-8")
            candidate = RunCandidate.load(candidate_root)
            evaluator = CandidateEvaluator(
                PlayerEvaluationConfig(
                    profile="fake",
                    profile_settings={"value": 1},
                    player=PlayerRunSettings(),
                )
            )
            loaded_instances = [
                SimpleNamespace(name="research-one"),
                SimpleNamespace(name="solver-one"),
                SimpleNamespace(name="research-two"),
                SimpleNamespace(name="solver-two"),
            ]
            seen_workspaces: list[str] = []

            def fake_execute_player_run(**kwargs):
                workspace = Path(kwargs["workspace"])
                seen_workspaces.append(str(workspace))
                self.assertTrue(workspace.is_relative_to(Path(kwargs["output_dir"])))
                self.assertEqual((workspace / "NOTES.md").read_text(encoding="utf-8"), "seed")
                run_dir = Path(kwargs["output_dir"])
                run_dir.mkdir(parents=True, exist_ok=True)
                return PlayerRunResult(
                    task=TaskEvaluation(False, False, 2.0, {"progress": 2}),
                    finish_reason="done",
                    agent_turns=1,
                    environment_steps=3,
                    output_dir=run_dir,
                    summary={},
                )

            with patch(
                "avo.evolution.evaluator.load_profile",
                side_effect=loaded_instances,
            ) as load, patch(
                "avo.evolution.evaluator.execute_player_run",
                side_effect=fake_execute_player_run,
            ), patch(
                "avo.evolution.evaluator.evaluate_solver_workspace",
                return_value=SolverEvaluation(
                    fitness=1.5,
                    success=False,
                    terminal=False,
                    score={"solver_levels_completed": 2, "model_score": 0.75},
                    finish_reason="completed",
                    environment_steps=2,
                ),
            ):
                evaluator.evaluate(candidate, root / "run_001")
                evaluator.evaluate(candidate, root / "run_002")

            self.assertEqual(load.call_count, 4)
            self.assertNotEqual(seen_workspaces[0], seen_workspaces[1])

    def test_fresh_solver_evaluation_combines_model_accuracy_and_progress(self) -> None:
        class CounterEnvironment:
            value = 0

            def reset(self):
                self.value = 0
                return self._observation()

            def step(self, action: Action):
                self.value += 1
                return self._observation()

            def _observation(self):
                won = self.value >= 2
                return Observation(
                    payload={"value": self.value},
                    status="WIN" if won else "PLAYING",
                    progress={"levels_completed": self.value, "win_levels": 2},
                    available_actions=("A1",),
                )

            def compare(self, expected: Observation, actual: Observation):
                exact = (
                    expected.payload == actual.payload
                    and expected.status == actual.status
                    and expected.progress == actual.progress
                )
                return Comparison(
                    exact=exact,
                    prospective_accuracy=float(expected.payload == actual.payload),
                    status_accuracy=float(expected.status == actual.status),
                    progress_accuracy=float(expected.progress == actual.progress),
                )

        class CounterProfile:
            profile_id = "counter"
            objective = "solve"

            def __init__(self):
                self.environment = CounterEnvironment()

            def evaluate(self, history, current):
                completed = int(current.progress["levels_completed"])
                return TaskEvaluation(
                    terminal=current.status == "WIN",
                    success=current.status == "WIN",
                    fitness=float(completed),
                    score={"levels_completed": completed},
                )

        solver_source = r'''import argparse, json, subprocess, sys

parser = argparse.ArgumentParser()
parser.add_argument("--play", action="store_true")
parser.add_argument("--max-steps", type=int, default=10)
args = parser.parse_args()
if args.play:
    for _ in range(2):
        subprocess.run(
            [sys.executable, "avo_tool.py", "probe", "A1", "--rationale", "solve"],
            check=True,
            capture_output=True,
            text=True,
        )
else:
    request = json.load(sys.stdin)
    current = request["current"]
    value = current["payload"]["value"] + 1
    print(json.dumps({
        "protocol": "avo-theory-prediction-v1",
        "expected": {
            "payload": {"value": value},
            "status": "WIN" if value >= 2 else "PLAYING",
            "progress": {"levels_completed": value, "win_levels": 2},
            "available_actions": ["A1"],
        },
        "confidence": 1.0,
        "rationale": "counter rule",
    }))
'''
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "solver.py").write_text(solver_source, encoding="utf-8")
            result = evaluate_solver_workspace(
                loaded_profile=SimpleNamespace(implementation=CounterProfile()),
                workspace=workspace,
                output_dir=root / "evaluation",
                max_environment_steps=10,
                max_wall_seconds=10,
            )

            self.assertEqual(result.score["solver_levels_completed"], 2)
            self.assertEqual(result.score["model_exact_rate"], 1.0)
            self.assertEqual(result.fitness, 2.0)
            self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
