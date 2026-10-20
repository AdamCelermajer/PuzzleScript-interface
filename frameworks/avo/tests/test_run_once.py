from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from frameworks.avo.core.agent_backend import AgentRunResult
from frameworks.avo.core.framework import Action, Comparison, Observation
from frameworks.avo.core.profile import LoadedProfile, TaskEvaluation
from frameworks.avo.run_once import PlayerRunSettings, execute_player_run


class OneStepEnvironment:
    def __init__(self) -> None:
        self.done = False

    def reset(self) -> Observation:
        self.done = False
        return Observation(payload={"done": False}, status="PLAYING", available_actions=("A1",))

    def step(self, action: Action) -> Observation:
        self.done = True
        return Observation(payload={"done": True}, status="WIN", available_actions=("A1",))

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        exact = expected == actual
        return Comparison(exact, float(exact), float(exact), float(exact))


class OneStepProfile:
    profile_id = "one-step"
    objective = "Win in one step."

    def __init__(self) -> None:
        self.environment = OneStepEnvironment()

    def evaluate(self, history, current) -> TaskEvaluation:
        success = current.status == "WIN"
        return TaskEvaluation(
            terminal=success,
            success=success,
            fitness=float(success),
            score={"success": int(success)},
        )


class ScriptedAgent:
    def __init__(self, config) -> None:
        self.config = config

    def run(self, gateway, workspace) -> AgentRunResult:
        workspace = Path(workspace)
        (workspace / "NOTES.md").write_text("learned", encoding="utf-8")
        transcript = workspace / "agent_transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        gateway.handle("probe", {"action_id": "A1", "rationale": "test"})
        gateway.handle("finish", {"reason": "environment terminal"})
        return AgentRunResult(
            finish_reason="environment terminal",
            terminal=True,
            turns=1,
            final_response="done",
            transcript_path=transcript,
        )


class SelfCheckingAgent:
    checks = []

    def __init__(self, config) -> None:
        self.config = config

    def run(self, gateway, workspace) -> AgentRunResult:
        workspace = Path(workspace)
        (workspace / "solver.py").write_text(
            """import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument('--play', action='store_true')
parser.add_argument('--max-steps')
parser.parse_args()
for line in sys.stdin:
    json.loads(line)
    print(json.dumps({'action': 'A1'}), flush=True)
""",
            encoding="utf-8",
        )
        gateway.handle("observe")
        type(self).checks = [
            gateway.handle("evaluate_solver", {"max_actions": 5}),
            gateway.handle("evaluate_solver", {"max_actions": 5}),
        ]
        transcript = workspace / "agent_transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        return AgentRunResult(
            finish_reason="self checks complete",
            terminal=False,
            turns=1,
            final_response="done",
            transcript_path=transcript,
        )


def test_execute_player_run_preserves_single_run_behavior_and_fitness() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        manifest = root / "profile.toml"
        prompt = root / "prompt.md"
        base_prompt = root / "base.txt"
        manifest.write_text("id='one-step'", encoding="utf-8")
        prompt.write_text("environment instructions", encoding="utf-8")
        base_prompt.write_text("base instructions", encoding="utf-8")
        loaded = LoadedProfile(
            implementation=OneStepProfile(),
            prompt=prompt.read_text(encoding="utf-8"),
            settings={},
            manifest_path=manifest,
            prompt_path=prompt,
            manifest_hash="manifest-hash",
            prompt_hash="prompt-hash",
        )

        with patch("frameworks.avo.run_once.CliAgent", ScriptedAgent):
            result = execute_player_run(
                loaded_profile=loaded,
                output_dir=root / "run",
                workspace=root / "workspace",
                settings=PlayerRunSettings(base_prompt=base_prompt),
                candidate_id="x_test",
                candidate_strategy="try A1",
            )

        assert result.task.success
        assert result.task.fitness == 1
        assert result.summary["candidate_id"] == "x_test"
        assert (root / "run" / "workspace" / "NOTES.md").read_text() == "learned"
        assert (root / "run" / "final_summary.json").is_file()


def test_player_run_has_no_internal_theory_budget() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        manifest = root / "profile.toml"
        prompt = root / "prompt.md"
        base_prompt = root / "base.txt"
        manifest.write_text("id='one-step'", encoding="utf-8")
        prompt.write_text("environment instructions", encoding="utf-8")
        base_prompt.write_text("solver builder instructions", encoding="utf-8")
        loaded = LoadedProfile(
            implementation=OneStepProfile(),
            prompt=prompt.read_text(encoding="utf-8"),
            settings={},
            manifest_path=manifest,
            prompt_path=prompt,
            manifest_hash="manifest-hash",
            prompt_hash="prompt-hash",
        )

        with patch("frameworks.avo.run_once.CliAgent", ScriptedAgent):
            result = execute_player_run(
                loaded_profile=loaded,
                output_dir=root / "run",
                workspace=root / "workspace",
                settings=PlayerRunSettings(base_prompt=base_prompt),
            )

        config = json.loads((root / "run/run_config.json").read_text(encoding="utf-8"))
        assert "max_candidates" not in config
        assert "candidates" not in result.summary
        assert "theory_candidates" not in result.summary
        assert not (root / "run/candidates").exists()


def test_player_can_run_two_fresh_solver_self_checks_without_research_steps() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        manifest = root / "profile.toml"
        prompt = root / "prompt.md"
        base_prompt = root / "base.txt"
        manifest.write_text("id='one-step'", encoding="utf-8")
        prompt.write_text("environment instructions", encoding="utf-8")
        base_prompt.write_text("solver builder instructions", encoding="utf-8")

        def loaded_profile() -> LoadedProfile:
            return LoadedProfile(
                implementation=OneStepProfile(),
                prompt=prompt.read_text(encoding="utf-8"),
                settings={},
                manifest_path=manifest,
                prompt_path=prompt,
                manifest_hash="manifest-hash",
                prompt_hash="prompt-hash",
            )

        with patch("frameworks.avo.run_once.CliAgent", SelfCheckingAgent), patch(
            "frameworks.avo.run_once.load_profile", side_effect=lambda *_: loaded_profile()
        ):
            result = execute_player_run(
                loaded_profile=loaded_profile(),
                output_dir=root / "run",
                workspace=root / "workspace",
                settings=PlayerRunSettings(
                    base_prompt=base_prompt,
                    max_solver_self_checks=2,
                    solver_self_check_max_environment_steps=5,
                ),
            )

        assert result.environment_steps == 0
        assert len(result.summary["solver_self_checks"]) == 2
        expected_fitness = json.loads(
            (root / "run/self_check/check_01/solver_evaluation.json").read_text(
                encoding="utf-8"
            )
        )["fitness"]
        assert [check["result"] for check in SelfCheckingAgent.checks] == [
            {"fitness": expected_fitness},
            {"fitness": expected_fitness},
        ]
        assert "evidence" not in json.dumps(SelfCheckingAgent.checks)
        assert "output_dir" not in json.dumps(SelfCheckingAgent.checks)
        assert (root / "run/self_check/check_01/evidence.jsonl").is_file()
        assert (root / "run/self_check/check_02/evidence.jsonl").is_file()
