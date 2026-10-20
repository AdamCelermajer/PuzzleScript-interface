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

from frameworks.avo.core.framework import Action, Comparison, Observation
from frameworks.avo.core.profile import TaskEvaluation
from frameworks.avo.evolution.candidate import CandidateEvaluation, RunCandidate
from frameworks.avo.evolution.evaluator import CandidateEvaluator, PlayerEvaluationConfig
from frameworks.avo.evolution.gateway import EvolutionBudget, EvolutionGateway
from frameworks.avo.evolution.solver_evaluation import SolverEvaluation, evaluate_solver_workspace
from frameworks.avo.evolution.store import EvolutionStore
from frameworks.avo.evolution.tool_server import EvolutionFileToolServer, OPTIMIZER_INTERFACE
from frameworks.avo.run_once import PlayerRunResult, PlayerRunSettings


class DeterministicEvaluator:
    """Cheap evaluator whose strategy declares the score used by the tests."""

    def evaluate(self, candidate: RunCandidate, run_dir: Path) -> CandidateEvaluation:
        marker = next(
            line for line in candidate.strategy().splitlines() if line.startswith("fitness=")
        )
        fitness = float(marker.partition("=")[2])
        workspace = run_dir / "solver"
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
        (workspace / "solver.py").write_text(
            f"FITNESS = {fitness}\n",
            encoding="utf-8",
        )
        evaluation_dir = run_dir / "evaluation"
        evaluation_dir.mkdir()
        before_observation = {
            "payload": {"frame": [[[int(fitness)]]]},
            "status": "PLAYING",
            "progress": {"levels_completed": int(fitness)},
            "metadata": {"rendered_frame": {"path": "frames/before.png"}},
        }
        after_observation = {
            **before_observation,
            "metadata": {"rendered_frame": {"path": "frames/after.png"}},
        }
        (evaluation_dir / "evidence.jsonl").write_text(
            json.dumps(
                {
                    "type": "transition",
                    "payload": {
                        "action": {"id": "A1", "data": {}},
                        "before": before_observation,
                        "after": after_observation,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "summary.json").write_text(
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
    def test_zero_wall_limit_still_stops_at_candidate_budget(self):
        with tempfile.TemporaryDirectory() as raw:
            store = EvolutionStore.create(Path(raw) / "campaign")
            store.prepare_seed_draft("x_0001", "fitness=1")
            gateway = EvolutionGateway(store, DeterministicEvaluator(), mission="test",
                                       budget=EvolutionBudget(max_evaluations=1, max_wall_seconds=0))
            gateway.started_at -= 1_000_000
            self.assertFalse(gateway.terminal)
            self.assertIsNone(gateway.handle("status")["budgets"]["wall_seconds_remaining"])
            gateway.handle("register", {"candidate_id": "x_0001"})
            gateway.handle("evaluate", {"candidate_id": "x_0001"})
            self.assertTrue(gateway.terminal)
            self.assertEqual(gateway.finish_reason, "candidate evaluation budget exhausted")

    def test_final_world_model_prompt_is_shared_and_rules_first(self):
        from frameworks.avo.evolution.gateway import FINAL_WORLD_MODEL_PROMPT

        self.assertIn("start with the objective", FINAL_WORLD_MODEL_PROMPT)
        self.assertIn("movement and interactions", FINAL_WORLD_MODEL_PROMPT)
        self.assertIn("remaining uncertainty", FINAL_WORLD_MODEL_PROMPT)
        self.assertNotIn("Ice Crates", FINAL_WORLD_MODEL_PROMPT)

    def test_world_model_modes_preserve_normal_registration_and_inheritance(self):
        for mode in ("final-only", "between-hypotheses"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as raw:
                store = EvolutionStore.create(Path(raw) / "campaign")
                store.prepare_seed_draft("x_0001", "fitness=1")
                gateway = EvolutionGateway(store, DeterministicEvaluator(), mission="test", world_model_mode=mode)
                # Neither mode requires a model file to register the initial hypothesis.
                gateway.handle("register", {"candidate_id": "x_0001"})
                gateway.handle("evaluate", {"candidate_id": "x_0001"})
                # A naturally produced note follows the ordinary inheritance path.
                model = store.root / "x_0001/solver/world_model.md"
                model.write_text("A learned rule.", encoding="utf-8")
                gateway.handle("fork", {"parent_id": "x_0001", "child_id": "x_0002"})
                draft_model = store.drafts_dir / "x_0002/seed/world_model.md"
                self.assertEqual(draft_model.read_text(encoding="utf-8"), "A learned rule.")
                gateway.handle("register", {"candidate_id": "x_0002"})
                frozen = store.get_candidate("x_0002").workspace_path / "world_model.md"
                self.assertEqual(frozen.read_text(encoding="utf-8"), "A learned rule.")

    def test_outer_designs_x1_from_frozen_initial_observation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = EvolutionStore.create(root / "evolution")
            draft = store.prepare_seed_draft("x_0001")
            gateway = EvolutionGateway(
                store,
                DeterministicEvaluator(),
                mission="Improve the player.",
                initial_observation={"payload": {"frame": [[[7]]]}},
            )

            self.assertEqual(store.population_summary()["candidate_count"], 0)
            self.assertEqual(store.population_summary()["drafts"], ["x_0001"])
            self.assertEqual(
                gateway.handle("initial")["observation"]["payload"]["frame"],
                [[[7]]],
            )
            strategy = Path(str(draft["draft_path"])) / "STRATEGY.md"
            strategy.write_text("fitness=1\nouter-designed baseline", encoding="utf-8")
            gateway.handle("register", {"candidate_id": "x_0001"})
            self.assertEqual(store.get_candidate("x_0001").strategy(), "fitness=1\nouter-designed baseline")

    def test_existing_population_keeps_legacy_layout(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "evolution"
            root.mkdir()
            (root / "population.json").write_text(
                json.dumps(
                    {"schema_version": 1, "candidates": [], "evaluations": []}
                ),
                encoding="utf-8",
            )

            store = EvolutionStore.create(root)
            candidate = store.create_seed("x_0001", "legacy strategy")

            self.assertTrue(store.legacy_layout)
            self.assertEqual(store.population_path, root / "population.json")
            self.assertEqual(candidate.workspace_path, root / "candidates/x_0001/workspace")
            self.assertEqual(
                store.next_run_dir("x_0001"),
                root / "evaluations/x_0001/run_001",
            )

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
            self.assertIn("FITNESS = 4.0", inspected["latest_run"]["solver"]["source"])
            self.assertIsNotNone(inspected["latest_run"]["solver"]["sha256"])
            self.assertEqual(inspected["latest_run"]["trace_summary"]["deepest_level"], 4)
            self.assertEqual(
                inspected["latest_run"]["trace_summary"][
                    "unchanged_actions_at_deepest_level"
                ],
                1,
            )
            self.assertEqual(
                inspected["latest_run"]["trace_summary"][
                    "unique_observations_at_deepest_level"
                ],
                1,
            )
            self.assertEqual(
                inspected["latest_run"]["trace_summary"]["action_counts_at_deepest_level"],
                {"A1": 1},
            )
            evidence = gateway.handle(
                "evidence",
                {
                    "candidate_id": "x_0001",
                    "phase": "evaluation",
                    "offset": 0,
                    "limit": 1,
                },
            )
            self.assertEqual(evidence["total_events"], 1)
            self.assertIsNone(evidence["next_offset"])
            self.assertEqual(
                evidence["events"][0]["payload"]["before"]["payload"]["frame"],
                [[[4]]],
            )
            self_check_dir = (
                root
                / "evolution"
                / "x_0001"
                / "research"
                / "self_check"
                / "check_01"
            )
            self_check_dir.mkdir(parents=True)
            (self_check_dir / "evidence.jsonl").write_text(
                json.dumps({"type": "episode_started", "payload": {"board": [[4]]}})
                + "\n",
                encoding="utf-8",
            )
            self_check_evidence = gateway.handle(
                "evidence",
                {
                    "candidate_id": "x_0001",
                    "phase": "self_check_01",
                },
            )
            self.assertEqual(
                self_check_evidence["events"][0]["payload"]["board"], [[4]]
            )
            with self.assertRaisesRegex(ValueError, "already evaluated"):
                gateway.handle("evaluate", {"candidate_id": "x_0001"})

            forked = gateway.handle(
                "fork", {"parent_id": "x_0001", "child_id": "x_0002"}
            )
            second_draft = Path(str(forked["draft_path"]))
            self.assertIn(
                "learned by x_0001",
                (second_draft / "seed" / "NOTES.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((second_draft / "seed" / "helper.py").is_file())
            (second_draft / "STRATEGY.md").write_text("fitness=6\nrefined", encoding="utf-8")
            gateway.handle("register", {"candidate_id": "x_0002"})
            self.assertFalse(second_draft.exists())
            second = gateway.handle("evaluate", {"candidate_id": "x_0002"})
            self.assertEqual(second["evaluation"]["fitness"], 6)
            second_inspected = gateway.handle("inspect", {"candidate_id": "x_0002"})
            self.assertNotEqual(
                second_inspected["latest_run"]["solver"]["sha256"],
                second_inspected["latest_run"]["solver"]["parent_sha256"],
            )
            self.assertIn(
                "-FITNESS = 4.0",
                second_inspected["latest_run"]["solver"]["diff_from_parent"],
            )
            self.assertIn(
                "+FITNESS = 6.0",
                second_inspected["latest_run"]["solver"]["diff_from_parent"],
            )

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
                initial_observation={"payload": {"frame": [[[3]]]}},
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
                initial = subprocess.run(
                    [sys.executable, "avo_evolve_tool.py", "initial"],
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
            self.assertEqual(
                json.loads(initial.stdout)["observation"]["payload"]["frame"],
                [[[3]]],
            )
            self.assertIn("fork PARENT_ID CHILD_ID", OPTIMIZER_INTERFACE)
            self.assertIn("evidence CANDIDATE_ID", OPTIMIZER_INTERFACE)
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
                self.assertFalse(workspace.is_relative_to(Path(kwargs["output_dir"])))
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
                "frameworks.avo.evolution.evaluator.load_profile",
                side_effect=loaded_instances,
            ) as load, patch(
                "frameworks.avo.evolution.evaluator.execute_player_run",
                side_effect=fake_execute_player_run,
            ), patch(
                "frameworks.avo.evolution.evaluator.evaluate_solver_workspace",
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

    def test_clean_generation_layout_and_separate_fresh_solver_budget(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "evolution"
            store = EvolutionStore.create(root, root / "outer")
            candidate = store.create_seed("x_0001", "build a model")
            evaluator = CandidateEvaluator(
                PlayerEvaluationConfig(
                    profile="fake",
                    profile_settings={},
                    player=PlayerRunSettings(max_environment_steps=300),
                    fresh_solver_max_environment_steps=1_500,
                )
            )

            def fake_execute_player_run(**kwargs):
                research = Path(kwargs["output_dir"])
                archived = research / "workspace"
                archived.mkdir(parents=True)
                (archived / "solver.py").write_text("print('solver')\n", encoding="utf-8")
                (archived / "NOTES.md").write_text("learned movement\n", encoding="utf-8")
                (archived / "agent_transcript.jsonl").write_text("{}\n", encoding="utf-8")
                (research / "final_summary.json").write_text("{}", encoding="utf-8")
                return PlayerRunResult(
                    task=TaskEvaluation(False, False, 1.0, {"levels_completed": 1}),
                    finish_reason="research complete",
                    agent_turns=4,
                    environment_steps=300,
                    output_dir=research,
                    summary={
                        "transcript": str(archived / "agent_transcript.jsonl"),
                        "output_dir": str(research),
                    },
                )

            fresh_result = SolverEvaluation(
                fitness=0.5,
                success=False,
                terminal=False,
                score={"solver_levels_completed": 1, "model_score": 0.5},
                finish_reason="fresh evaluation complete",
                environment_steps=1_500,
            )
            with patch(
                "frameworks.avo.evolution.evaluator.load_profile",
                side_effect=[SimpleNamespace(name="research"), SimpleNamespace(name="fresh")],
            ), patch(
                "frameworks.avo.evolution.evaluator.execute_player_run",
                side_effect=fake_execute_player_run,
            ), patch(
                "frameworks.avo.evolution.evaluator.evaluate_solver_workspace",
                return_value=fresh_result,
            ) as fresh:
                evaluation = evaluator.evaluate(candidate, store.next_run_dir("x_0001"))

            generation = root / "x_0001"
            self.assertEqual(evaluation.run_dir, generation.resolve())
            self.assertTrue((generation / "seed" / "NOTES.md").is_file())
            self.assertTrue((generation / "research" / "summary.json").is_file())
            self.assertTrue((generation / "solver" / "solver.py").is_file())
            self.assertTrue((generation / "evaluation").is_dir())
            self.assertTrue((generation / "summary.json").is_file())
            self.assertFalse((generation / "research" / "workspace").exists())
            self.assertEqual(fresh.call_args.kwargs["max_environment_steps"], 1_500)
            self.assertEqual(fresh.call_args.kwargs["workspace"], generation / "solver")

            store.record_evaluation(evaluation)
            child = store.fork("x_0001", "x_0002")
            child_seed = Path(str(child["draft_path"])) / "seed"
            self.assertEqual(
                (child_seed / "NOTES.md").read_text(encoding="utf-8"),
                "learned movement\n",
            )

    def test_fresh_solver_evaluation_scores_fresh_progress(self) -> None:
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

        solver_source = r'''import argparse, json, sys

parser = argparse.ArgumentParser()
parser.add_argument("--play", action="store_true")
parser.add_argument("--max-steps", type=int, default=10)
args = parser.parse_args()
if args.play:
    for line in sys.stdin:
        json.loads(line)
        print(json.dumps({"action": "A1"}), flush=True)
else:
    raise SystemExit("fresh evaluation must use --play")
'''
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "solver.py").write_text(solver_source, encoding="utf-8")
            # The solver runs as a plain subprocess in its own scratch copy.
            result = evaluate_solver_workspace(
                loaded_profile=SimpleNamespace(implementation=CounterProfile()),
                workspace=workspace,
                output_dir=root / "evaluation",
                max_environment_steps=10,
                max_wall_seconds=10,
            )
            unlimited = evaluate_solver_workspace(
                loaded_profile=SimpleNamespace(implementation=CounterProfile()),
                workspace=workspace,
                output_dir=root / "evaluation-no-wall-limit",
                max_environment_steps=10,
                max_wall_seconds=0,
            )
            self.assertTrue(unlimited.success)
            self.assertEqual(unlimited.environment_steps, 2)

            self.assertEqual(result.score["solver_levels_completed"], 2)
            self.assertEqual(result.score["solver_environment_actions"], 2)
            self.assertEqual(result.fitness, 2.0)
            self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
