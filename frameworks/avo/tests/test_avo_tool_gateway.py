import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from frameworks.avo.core.framework import Action, AvoLaboratory, Comparison, Observation
from frameworks.avo.core.profile import TaskEvaluation
from frameworks.avo.core.tool_gateway import AGENT_INTERFACE, AvoToolGateway, FileToolServer, GatewayBudget


class CounterEnvironment:
    def __init__(self) -> None:
        self.value = 0

    def reset(self) -> Observation:
        self.value = 0
        return self._observation()

    def step(self, action: Action) -> Observation:
        if action.id == "A1":
            self.value += 1
        return self._observation()

    def save_state(self) -> str:
        return str(self.value)

    def restore_state(self, token: str) -> Observation:
        self.value = int(token)
        return self._observation()

    def _observation(self) -> Observation:
        return Observation(
            payload={"value": self.value},
            status="DONE" if self.value else "RUNNING",
            available_actions=("A1", "A2"),
        )

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        exact = expected.payload == actual.payload and expected.status == actual.status
        return Comparison(exact, float(expected.payload == actual.payload), float(expected.status == actual.status), 1)


class CounterProfile:
    profile_id = "counter"
    objective = "Reach DONE."

    def __init__(self, environment: CounterEnvironment) -> None:
        self.environment = environment

    def evaluate(self, history, current) -> TaskEvaluation:
        success = current.status == "DONE"
        return TaskEvaluation(
            terminal=success,
            success=success,
            fitness=float(success),
            score={"success": int(success), "environment_actions": len(history)},
        )


class AvoToolGatewayTests(unittest.TestCase):
    def test_zero_wall_limit_preserves_the_action_budget(self):
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            gateway = AvoToolGateway(AvoLaboratory(environment, [], root), CounterProfile(environment),
                                     budget=GatewayBudget(max_environment_steps=1, max_wall_seconds=0))
            gateway.started_at -= 1_000_000
            self.assertIsNone(gateway.handle("status")["budgets"]["wall_seconds_remaining"])
            gateway.handle("probe", {"action_id": "A2"})
            with self.assertRaisesRegex(RuntimeError, "step budget exhausted"):
                gateway.handle("probe", {"action_id": "A2"})

    def test_solver_self_checks_are_fresh_separate_and_limited_to_two(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            calls: list[tuple[int, int]] = []

            def self_check(check_number: int, max_actions: int):
                calls.append((check_number, max_actions))
                return {
                    "fitness": float(check_number),
                    "evidence": "must-not-be-returned-by-real-self-check",
                }

            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
                budget=GatewayBudget(max_environment_steps=3),
                solver_self_check=self_check,
                max_solver_self_checks=2,
                max_solver_self_check_steps=20,
            )

            first = gateway.handle("evaluate_solver", {"max_actions": 10})
            second = gateway.handle("evaluate_solver", {"max_actions": 20})

            self.assertEqual(calls, [(1, 10), (2, 20)])
            self.assertEqual(first["result"], {"fitness": 1.0})
            self.assertNotIn("evidence", json.dumps(first))
            self.assertEqual(first["checks_remaining"], 1)
            self.assertEqual(second["checks_remaining"], 0)
            self.assertEqual(gateway.environment_steps, 0)
            self.assertEqual(
                gateway.handle("status")["budgets"]["environment_steps_remaining"],
                3,
            )
            with self.assertRaisesRegex(RuntimeError, "limit exhausted"):
                gateway.handle("evaluate_solver", {"max_actions": 1})

    def test_observation_has_opaque_actions_and_probe_needs_no_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
                budget=GatewayBudget(max_environment_steps=2),
            )
            observed = gateway.handle("observe")
            self.assertEqual(observed["observation"]["available_actions"], ["A1", "A2"])
            self.assertNotIn("action_meanings", json.dumps(observed))

            result = gateway.handle("probe", {"action_id": "A1", "rationale": "first test"})
            self.assertEqual(result["evaluations"], [])
            self.assertTrue(result["task"]["terminal"])
            self.assertTrue(result["task"]["success"])
            self.assertEqual(result["task"]["fitness"], 1)

    def test_file_rpc_exposes_the_same_generic_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(lab, CounterProfile(environment))
            server = FileToolServer(gateway, workspace)
            server.start()
            try:
                completed = subprocess.run(
                    [sys.executable, "avo_tool.py", "observe"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            finally:
                server.stop()

            # The game commands print plain text; a payload that is not a board is compact JSON.
            self.assertIn('payload: {"value":0}', completed.stdout)
            self.assertIn("available_actions=A1, A2", completed.stdout)
            self.assertTrue((workspace / "AGENT_INTERFACE.md").is_file())
            self.assertEqual((workspace / "MISSION.md").read_text(encoding="utf-8").splitlines()[2], "Reach DONE.")
            self.assertIn("Action IDs are opaque", AGENT_INTERFACE)
            self.assertNotIn("Up", AGENT_INTERFACE)
            self.assertNotIn("Down", AGENT_INTERFACE)

    def test_workspace_has_no_theory_package_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
            )
            server = FileToolServer(gateway, workspace)
            server.start()
            try:
                help_result = subprocess.run(
                    [sys.executable, "avo_tool.py", "--help"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                status = gateway.handle("status")
            finally:
                server.stop()

            interface = (workspace / "AGENT_INTERFACE.md").read_text(encoding="utf-8")
            self.assertNotIn("publish", help_result.stdout)
            self.assertNotIn("candidates", help_result.stdout)
            self.assertNotIn("executable hypotheses", interface)
            self.assertIn("You own the workspace", interface)
            self.assertNotIn("candidate_slots_remaining", status["budgets"])
            self.assertFalse((workspace / "drafts").exists())
            with self.assertRaisesRegex(ValueError, "Unknown AVO tool"):
                gateway.handle("publish", {})

    def test_agent_can_archive_research_workspace_through_rpc(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "agent"
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "run")
            gateway = AvoToolGateway(lab, CounterProfile(environment))
            server = FileToolServer(gateway, workspace)
            server.start()
            try:
                (workspace / "research").mkdir()
                (workspace / "research" / "probe.py").write_text("pass", encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, "avo_tool.py", "archive", "."],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            finally:
                server.stop()

            payload = json.loads(completed.stdout)
            self.assertIn("research/probe.py", payload["archived"])
            self.assertTrue((Path(root) / "run" / "workspace" / "research" / "probe.py").is_file())
            self.assertFalse((Path(root) / "run" / "workspace" / ".avo_rpc").exists())

    def test_finish_does_not_claim_task_success(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
            )
            gateway.handle("observe")
            stopped = gateway.handle("finish", {"reason": "giving up"})

            self.assertTrue(stopped["finished"])
            self.assertFalse(stopped["task"]["success"])
            self.assertFalse(stopped["task"]["terminal"])

    def test_supervisor_redirect_blocks_actions_until_agent_acknowledges(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
                budget=GatewayBudget(max_environment_steps=10),
            )
            for _ in range(3):
                result = gateway.handle(
                    "probe",
                    {"action_id": "A2", "rationale": "test no-change behavior"},
                )

            self.assertTrue(result["supervisor"]["attention_required"])
            with self.assertRaisesRegex(RuntimeError, "requires acknowledgement"):
                gateway.handle("probe", {"action_id": "A1"})
            acknowledged = gateway.handle(
                "acknowledge_supervisor",
                {"response": "stop repeating A2 and test A1"},
            )
            self.assertTrue(acknowledged["acknowledged"])
            self.assertTrue(gateway.handle("probe", {"action_id": "A1"})["task"]["success"])

    def test_reset_starts_logged_episode_without_erasing_history(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            evidence = Path(root) / "evidence"
            lab = AvoLaboratory(environment, [], evidence)
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
                budget=GatewayBudget(max_environment_steps=10),
            )
            gateway.handle("probe", {"action_id": "A2", "rationale": "collect evidence"})
            restarted = gateway.handle("reset", {"reason": "test a new strategy"})

            self.assertEqual(restarted["episode"], 2)
            self.assertEqual(len(lab.history), 1)
            self.assertEqual(lab.history[0].episode, 1)
            self.assertEqual(gateway.environment_steps, 2)
            records = [
                json.loads(line)
                for line in (evidence / "evidence.jsonl").read_text().splitlines()
            ]
            starts = [record for record in records if record["type"] == "episode_started"]
            self.assertEqual([record["payload"]["episode"] for record in starts], [1, 2])
            self.assertEqual(starts[-1]["payload"]["reason"], "test a new strategy")

    def test_checkpoint_restores_state_without_spending_an_environment_step(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            environment = CounterEnvironment()
            lab = AvoLaboratory(environment, [], Path(root) / "evidence")
            gateway = AvoToolGateway(
                lab,
                CounterProfile(environment),
                budget=GatewayBudget(max_environment_steps=10),
            )
            gateway.handle("observe")
            saved = gateway.handle("checkpoint", {"label": "root"})
            gateway.handle("probe", {"action_id": "A1", "rationale": "advance"})
            restored = gateway.handle(
                "restore", {"checkpoint_id": saved["checkpoint_id"]}
            )

            self.assertEqual(restored["observation"]["payload"], {"value": 0})
            self.assertEqual(gateway.environment_steps, 1)
            self.assertEqual(lab.episode, 2)
            self.assertEqual(len(lab.history), 1)


if __name__ == "__main__":
    unittest.main()
