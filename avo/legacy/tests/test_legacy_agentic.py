import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from avo.core.framework import Action, AvoLaboratory, Comparison, Observation
from avo.legacy.agentic import AgentDecision, AgenticVariationRunner, SearchBudget


class CounterEnvironment:
    def __init__(self) -> None:
        self.value = 0

    def observation(self) -> Observation:
        return Observation(
            payload={"value": self.value},
            status="DONE" if self.value else "RUNNING",
            available_actions=("ADD",),
        )

    def reset(self) -> Observation:
        self.value = 0
        return self.observation()

    def step(self, action: Action) -> Observation:
        self.value += 1
        return self.observation()

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        exact = expected.payload == actual.payload and expected.status == actual.status
        return Comparison(
            exact=exact,
            prospective_accuracy=float(expected.payload == actual.payload),
            status_accuracy=float(expected.status == actual.status),
            progress_accuracy=1,
        )


class PackageWritingAgent:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, context) -> AgentDecision:
        self.calls += 1
        package = context.workspace / "x_counter"
        package.mkdir(exist_ok=True)
        package.joinpath("manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "candidate_id": "x_counter",
                    "parent_id": None,
                    "claim": "ADD increments value and ends the task",
                    "complexity": 0.1,
                    "command": ["$PYTHON", "predict.py"],
                }
            ),
            encoding="utf-8",
        )
        package.joinpath("predict.py").write_text(
            textwrap.dedent(
                """
                import json, sys
                request = json.load(sys.stdin)
                value = request["current"]["payload"]["value"] + 1
                json.dump({
                    "protocol": "avo-theory-prediction-v1",
                    "expected": {
                        "payload": {"value": value},
                        "status": "DONE",
                        "progress": None,
                        "available_actions": ["ADD"]
                    },
                    "confidence": 0.9,
                    "rationale": "counter model"
                }, sys.stdout)
                """
            ).strip(),
            encoding="utf-8",
        )
        return AgentDecision(action=Action("ADD"), rationale="falsify the counter theory")


class AgenticAvoTests(unittest.TestCase):
    def test_agent_creates_theory_and_owns_probe_choice(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_root = Path(root)
            laboratory = AvoLaboratory(CounterEnvironment(), [], run_root / "evidence")
            agent = PackageWritingAgent()
            result = AgenticVariationRunner(
                laboratory,
                agent,
                run_root / "candidates",
                budget=SearchBudget(max_decisions=3, max_environment_steps=2),
                terminal_statuses=("DONE",),
            ).run()

            self.assertEqual(result.stop_reason, "environment_terminal:DONE")
            self.assertEqual(result.candidates_created, 1)
            self.assertTrue(result.cycles[0].evaluations[0].exact)
            records = [
                json.loads(line)
                for line in laboratory.store.path.read_text(encoding="utf-8").splitlines()
            ]
            types = [record["type"] for record in records]
            self.assertLess(types.index("candidate_registered"), types.index("agent_decision"))
            self.assertLess(types.index("agent_decision"), types.index("prediction_frozen"))
            self.assertLess(types.index("prediction_frozen"), types.index("transition"))

    def test_exploratory_probe_without_a_theory_is_allowed(self) -> None:
        class EmptyAgent:
            def decide(self, context) -> AgentDecision:
                return AgentDecision(action=Action("ADD"), rationale="guess")

        with tempfile.TemporaryDirectory() as root:
            laboratory = AvoLaboratory(CounterEnvironment(), [], Path(root) / "evidence")
            result = AgenticVariationRunner(
                laboratory,
                EmptyAgent(),
                Path(root) / "candidates",
                budget=SearchBudget(max_decisions=1, max_environment_steps=1),
                terminal_statuses=("DONE",),
            ).run()
            self.assertEqual(result.stop_reason, "environment_terminal:DONE")
            self.assertEqual(result.candidates_created, 0)
            self.assertEqual(result.cycles[0].evaluations, ())


if __name__ == "__main__":
    unittest.main()
