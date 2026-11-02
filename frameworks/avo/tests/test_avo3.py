"""AVO3: research budget per attempt, the end-of-attempt world model, and the launch options."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from frameworks.avo.evolution.gateway import EvolutionBudget, EvolutionGateway
from frameworks.avo.evolution.store import EvolutionStore
from frameworks.avo.framework import AVO, entry, research_schedule
from frameworks.avo.tests.test_evolution import DeterministicEvaluator


class BudgetRecorder(DeterministicEvaluator):
    def __init__(self) -> None:
        self.budgets: list[int | None] = []

    def evaluate(self, candidate, run_dir, research_moves=None):
        self.budgets.append(research_moves)
        return super().evaluate(candidate, run_dir)


class Avo3Test(unittest.TestCase):
    def test_schedule_parses_and_rejects_bad_values(self) -> None:
        self.assertEqual(research_schedule("30, 50,100,200,500"), [30, 50, 100, 200, 500])
        self.assertEqual(research_schedule(""), [])
        for bad in ("30,x", "0,50", "20000"):
            with self.assertRaises(ValueError):
                research_schedule(bad)

    def test_each_attempt_gets_the_next_budget(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = EvolutionStore.create(Path(raw) / "campaign")
            store.create_seed("x_0001", "fitness=1")
            evaluator = BudgetRecorder()
            gateway = EvolutionGateway(store, evaluator, mission="m", budget=EvolutionBudget(max_evaluations=3),
                                       research_moves_schedule=(30, 50, 100))
            self.assertEqual(gateway.handle("status")["budgets"]["next_attempt_research_moves"], 30)
            gateway.handle("evaluate", {"candidate_id": "x_0001"})
            self.assertEqual(gateway.handle("status")["budgets"]["next_attempt_research_moves"], 50)
            store.fork("x_0001", "x_0002")
            store.register_draft("x_0002")
            gateway.handle("evaluate", {"candidate_id": "x_0002"})
            self.assertEqual(evaluator.budgets, [30, 50])

    def test_no_schedule_keeps_the_old_call(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            store = EvolutionStore.create(Path(raw) / "campaign")
            store.create_seed("x_0001", "fitness=1")
            gateway = EvolutionGateway(store, DeterministicEvaluator(), mission="m")
            gateway.handle("evaluate", {"candidate_id": "x_0001"})  # a 2-argument evaluator still works
            self.assertNotIn("next_attempt_research_moves", gateway.handle("status")["budgets"])

    def test_launch_flags(self) -> None:
        options = AVO.check_options({"fitness": "research", "research_moves_schedule": "30,50,100,200,500",
                                     "attempt_world_model": True, "final_solver": True, "solver_moves": 1000})
        spec = {"options": options, "max_wall_seconds": 0, "game_id": "ps_modality-v1", "backend_url": "http://b",
                "harness": "opencode", "model": "openrouter/qwen/qwen3.8-27b", "effort": "high",
                "optimizer_model": "openrouter/qwen/qwen3.8-27b", "optimizer_effort": "high", "provider": "near-ai"}
        argv = entry(spec, False, Path("results"), Path("parent"))
        self.assertEqual(argv[argv.index("--max-evaluations") + 1], "5")
        self.assertEqual(argv[argv.index("--player-max-environment-steps") + 1], "30")
        self.assertEqual(argv[argv.index("--research-moves-schedule") + 1], "30,50,100,200,500")
        self.assertIn("--attempt-world-model", argv)
        self.assertIn("--final-solver", argv)

    def test_inner_player_is_asked_for_its_world_model_once(self) -> None:
        from frameworks.avo.core.tool_gateway import AvoToolGateway
        gateway = AvoToolGateway(SimpleNamespace(current=None), SimpleNamespace(), final_report="write it")
        self.assertEqual(gateway.finalization_instruction(), "write it")
        self.assertIsNone(gateway.finalization_instruction())
        self.assertIsNone(AvoToolGateway(SimpleNamespace(current=None), SimpleNamespace()).finalization_instruction())


if __name__ == "__main__":
    unittest.main()
