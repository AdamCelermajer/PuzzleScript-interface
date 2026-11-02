from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from frameworks.avo.core.agent_backend import AgentRunResult
from frameworks.avo.core.framework import Action, Comparison, Observation
from frameworks.avo.core.profile import LoadedProfile, TaskEvaluation
from frameworks.avo.run_once import PlayerRunSettings, execute_player_run
from frameworks import world_model


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


class ModelKeepingAgent(ScriptedAgent):
    instructions = ""

    def run(self, gateway, workspace) -> AgentRunResult:
        type(self).instructions = self.config.task_instructions
        (Path(workspace) / "world_model.md").write_text("A1 wins.", encoding="utf-8")
        return super().run(gateway, workspace)


def test_research_session_keeps_a_world_model_that_is_copied_during_play() -> None:
    with tempfile.TemporaryDirectory() as raw, patch.object(world_model, "EVERY", 1):
        root = Path(raw)
        prompt = root / "prompt.md"
        base_prompt = root / "base.txt"
        prompt.write_text("environment instructions", encoding="utf-8")
        base_prompt.write_text("base instructions", encoding="utf-8")
        loaded = LoadedProfile(implementation=OneStepProfile(), prompt=prompt.read_text(encoding="utf-8"),
                               settings={}, manifest_path=root / "profile.toml", prompt_path=prompt,
                               manifest_hash="manifest-hash", prompt_hash="prompt-hash")
        (root / "profile.toml").write_text("id='one-step'", encoding="utf-8")
        with patch("frameworks.avo.run_once.CliAgent", ModelKeepingAgent):
            execute_player_run(loaded_profile=loaded, output_dir=root / "run", workspace=root / "workspace",
                               settings=PlayerRunSettings(base_prompt=base_prompt))

        assert world_model.keep_instruction() in ModelKeepingAgent.instructions
        copies = root / "run" / world_model.SNAPSHOT_DIR
        assert sorted(p.name for p in copies.iterdir()) == ["a0001.md", "final.md", "level-1-a0001.md"]
        assert (copies / "final.md").read_text(encoding="utf-8") == "A1 wins."


def test_player_run_has_no_internal_theory_budget() -> None:
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
            )

        config = json.loads((root / "run/run_config.json").read_text(encoding="utf-8"))
        assert "max_candidates" not in config
        assert "candidates" not in result.summary
        assert "theory_candidates" not in result.summary
        assert not (root / "run/candidates").exists()
