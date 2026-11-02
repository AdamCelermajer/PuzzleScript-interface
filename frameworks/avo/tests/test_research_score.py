"""AVO's score: no solver; a candidate scores the levels its own research session completes."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from frameworks import world_model
from frameworks.avo import evolve, research_score
from frameworks.avo.client.turns import DEFAULT_PROMPT_PATH, INNER_RUN_INSTRUCTION
from frameworks.avo.core.agent_backend import AgentRunResult
from frameworks.avo.core.framework import Action, Comparison, Observation
from frameworks.avo.core.profile import LoadedProfile, TaskEvaluation
from frameworks.avo.core.tool_gateway import AGENT_INTERFACE, FileToolServer
from frameworks.avo.environments.puzzlescript.profile import PuzzleScriptProfile
from frameworks.avo.evolution.evaluator import CandidateEvaluator, PlayerEvaluationConfig
from frameworks.avo.evolution.store import EvolutionStore
from frameworks.avo.evolution.tool_server import OPTIMIZER_INTERFACE
from frameworks.avo.run_once import PlayerRunResult, PlayerRunSettings, execute_player_run

PUZZLESCRIPT = Path(research_score.__file__).parent / "environments" / "puzzlescript"


def observation(levels: int, win_levels: int = 3) -> Observation:
    return Observation(payload={"levels": levels}, status="WIN" if levels >= win_levels else "PLAYING",
                       progress={"levels_completed": levels, "win_levels": win_levels}, available_actions=("A1",))


class LevelEnvironment:
    """Each A1 completes one more level; a reset starts the game again."""

    def __init__(self) -> None:
        self.levels = 0

    def reset(self) -> Observation:
        self.levels = 0
        return observation(0)

    def step(self, action: Action) -> Observation:
        self.levels += 1
        return observation(self.levels)

    def compare(self, expected: Observation, actual: Observation) -> Comparison:
        exact = expected == actual
        return Comparison(exact, float(exact), float(exact), float(exact))


class LevelProfile:
    profile_id = "levels"
    objective = "Reach the last level."

    def __init__(self) -> None:
        self.environment = LevelEnvironment()

    def evaluate(self, history, current) -> TaskEvaluation:
        levels = current.progress["levels_completed"]
        return TaskEvaluation(terminal=current.status == "WIN", success=current.status == "WIN", fitness=float(levels),
                              score={"levels_completed": levels, "win_levels": 3})


def loaded_profile(root: Path) -> LoadedProfile:
    prompt = root / "prompt.md"
    prompt.write_text("Advance through the game.", encoding="utf-8")
    (root / "profile.toml").write_text("id='levels'", encoding="utf-8")
    return LoadedProfile(implementation=LevelProfile(), prompt="Advance through the game.", settings={},
                         manifest_path=root / "profile.toml", prompt_path=prompt, manifest_hash="m", prompt_hash="p")


def transitions(*levels: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(after=observation(level)) for level in levels]


def test_best_progress_is_the_most_levels_reached_even_after_a_reset() -> None:
    assert research_score.best_progress(transitions(1, 2, 0, 1)) == {
        "best_levels_completed": 2, "actions_to_best": 2, "win_levels": 3}
    assert research_score.best_progress([]) == {"best_levels_completed": 0, "actions_to_best": 0, "win_levels": 0}


def test_rank_breaks_fitness_ties_by_fewer_actions_and_keeps_archived_solver_order() -> None:
    research = [{"id": "a", "fitness": 2.0, "score": {"actions_to_best": 90}},
                {"id": "b", "fitness": 2.0, "score": {"actions_to_best": 40}},
                {"id": "c", "fitness": 1.0, "score": {"actions_to_best": 5}}]
    assert max(research, key=research_score.rank)["id"] == "b"
    solver = [{"id": "a", "fitness": 2.0, "score": {}}, {"id": "b", "fitness": 2.0, "score": {}}]
    assert max(solver, key=research_score.rank)["id"] == "a"  # the earliest, as before


def test_prompts_and_interfaces_have_no_solver() -> None:
    texts = {"base": DEFAULT_PROMPT_PATH.read_text(encoding="utf-8"),
             "outer": evolve.OUTER_PROMPT.read_text(encoding="utf-8"),
             "task": (PUZZLESCRIPT / "prompt.md").read_text(encoding="utf-8"),
             "objective": PuzzleScriptProfile.objective,
             "agent interface": AGENT_INTERFACE, "optimizer interface": OPTIMIZER_INTERFACE,
             "first instruction": INNER_RUN_INSTRUCTION}
    for name, text in texts.items():
        for word in ("solver.py", "evaluate_solver", "self-check", "self_check", "solver change", "solver delta"):
            assert word not in text, (name, word)
    assert "Do not write solver code, simulators, mock games or test harnesses" in texts["outer"]
    assert "world_model.md" in texts["base"] and "avo_tool.py archive ." in texts["base"]
    assert "evidence CANDIDATE_ID research --offset" in texts["optimizer interface"]


class ResearchingAgent:
    seen: dict = {}

    def __init__(self, config) -> None:
        self.config = config

    def run(self, gateway, workspace) -> AgentRunResult:
        workspace = Path(workspace)
        FileToolServer(gateway, workspace).install()
        (workspace / "world_model.md").write_text("A1 completes a level.", encoding="utf-8")
        for _ in range(2):
            gateway.handle("probe", {"action_id": "A1"})
        gateway.handle("reset", {"reason": "replay from the start"})
        gateway.handle("probe", {"action_id": "A1"})
        with pytest.raises(ValueError, match="Unknown AVO tool"):
            gateway.handle("evaluate_solver", {"max_actions": 5})
        type(self).seen = {"config": self.config, "budgets": gateway.handle("status")["budgets"],
                           "interface": (workspace / "AGENT_INTERFACE.md").read_text(encoding="utf-8"),
                           "mission": (workspace / "MISSION.md").read_text(encoding="utf-8")}
        transcript = workspace / "agent_transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        return AgentRunResult(finish_reason="done", terminal=False, turns=1, final_response="", transcript_path=transcript)


def test_research_session_has_no_solver_and_scores_its_best_level(tmp_path) -> None:
    with patch("frameworks.avo.run_once.CliAgent", ResearchingAgent):
        result = execute_player_run(loaded_profile=loaded_profile(tmp_path), output_dir=tmp_path / "run",
                                    workspace=tmp_path / "workspace",
                                    settings=PlayerRunSettings())

    seen = ResearchingAgent.seen
    assert Path(seen["config"].prompt_path) == DEFAULT_PROMPT_PATH
    assert "Advance through the game." in seen["config"].task_instructions
    assert world_model.keep_instruction() in seen["config"].task_instructions
    assert seen["interface"] == AGENT_INTERFACE and LevelProfile.objective in seen["mission"]
    assert not any("solver" in key for key in seen["budgets"])
    summary = result.summary
    assert (summary["best_levels_completed"], summary["actions_to_best"], summary["win_levels"]) == (2, 2, 3)
    assert result.task.fitness == 1  # the last board, after the reset
    config = json.loads((tmp_path / "run" / "run_config.json").read_text(encoding="utf-8"))
    assert config["fitness"] == "research" and config["objective"] == LevelProfile.objective
    assert not (tmp_path / "run" / "self_check").exists()


def test_evaluator_scores_research_progress_and_children_inherit_the_workspace(tmp_path) -> None:
    root = tmp_path / "evolution"
    store = EvolutionStore.create(root, root / "outer")
    evaluator = CandidateEvaluator(PlayerEvaluationConfig(
        profile="fake", profile_settings={}, player=PlayerRunSettings()))
    best = iter([(2, 90), (2, 40)])

    def fake_execute_player_run(**kwargs):
        levels, actions = next(best)
        research = Path(kwargs["output_dir"])
        (research / "workspace").mkdir(parents=True)
        (research / "workspace" / "world_model.md").write_text(f"{levels} levels", encoding="utf-8")
        (research / "final_summary.json").write_text("{}", encoding="utf-8")
        step = {"type": "transition", "payload": {"action": {"id": "A1"}, "before": {"progress": {"levels_completed": 0}},
                                                  "after": {"progress": {"levels_completed": levels}}}}
        (research / "evidence.jsonl").write_text(json.dumps(step) + "\n", encoding="utf-8")
        return PlayerRunResult(task=TaskEvaluation(False, False, 0.0, {"levels_completed": 0, "win_levels": 3}),
                               finish_reason="research complete", agent_turns=2, environment_steps=100,
                               output_dir=research, summary={"best_levels_completed": levels,
                                                             "actions_to_best": actions, "win_levels": 3})

    with patch("frameworks.avo.evolution.evaluator.load_profile", return_value=SimpleNamespace()), \
            patch("frameworks.avo.evolution.evaluator.execute_player_run", side_effect=fake_execute_player_run):
        store.create_seed("x_0001", "play")
        first = evaluator.evaluate(store.get_candidate("x_0001"), store.next_run_dir("x_0001"))
        store.record_evaluation(first)
        child = store.fork("x_0001", "x_0002")
        inherited = (Path(str(child["draft_path"])) / "seed" / "world_model.md").read_text(encoding="utf-8")
        store.register_draft("x_0002")
        store.record_evaluation(evaluator.evaluate(store.get_candidate("x_0002"), store.next_run_dir("x_0002")))

    assert inherited == "2 levels"
    assert (first.fitness, first.success, first.environment_steps) == (2.0, False, 100)
    assert first.score["actions_to_best"] == 90 and first.score["research_levels_completed"] == 2
    generation = root / "x_0001"
    assert not (generation / "evaluation").exists() and (generation / "solver" / "world_model.md").is_file()
    assert "solver_evaluation" not in json.loads((generation / "summary.json").read_text(encoding="utf-8"))
    assert store.population_summary()["best"]["candidate_id"] == "x_0002"  # same levels in fewer actions
    assert store.inspect("x_0001")["latest_run"]["trace_summary"]["deepest_level"] == 2


def test_continue_levels_starts_each_research_session_where_the_previous_one_stopped(tmp_path) -> None:
    root = tmp_path / "evolution"
    store = EvolutionStore.create(root, root / "outer")
    progress = root / "level_progress.json"
    evaluator = CandidateEvaluator(PlayerEvaluationConfig(
        profile="fake", profile_settings={"game_id": "g"}, player=PlayerRunSettings(),
        level_progress=progress))
    reached = iter([2, 0, 3])  # the second session takes no action: its best is 0, but it started at level 3
    settings = []

    def fake_load_profile(profile, profile_settings):
        settings.append(dict(profile_settings))
        return SimpleNamespace()

    def fake_execute_player_run(**kwargs):
        levels = next(reached)
        research = Path(kwargs["output_dir"])
        (research / "workspace").mkdir(parents=True)
        (research / "final_summary.json").write_text("{}", encoding="utf-8")
        (research / "evidence.jsonl").write_text("", encoding="utf-8")
        return PlayerRunResult(task=TaskEvaluation(False, False, 0.0, {"levels_completed": levels, "win_levels": 4}),
                               finish_reason="research complete", agent_turns=1, environment_steps=10,
                               output_dir=research, summary={"best_levels_completed": levels,
                                                             "actions_to_best": 5, "win_levels": 4})

    with patch("frameworks.avo.evolution.evaluator.load_profile", side_effect=fake_load_profile),             patch("frameworks.avo.evolution.evaluator.execute_player_run", side_effect=fake_execute_player_run):
        scores = []
        for number in (1, 2, 3):
            candidate = f"x_{number:04d}"
            store.create_seed(candidate, "play")
            evaluation = evaluator.evaluate(store.get_candidate(candidate), store.next_run_dir(candidate))
            store.record_evaluation(evaluation)
            scores.append((evaluation.score["research_start_level"], evaluation.fitness))

    assert [s.get("start_level", 1) for s in settings] == [1, 3, 3]
    assert scores == [(1, 2.0), (3, 0.0), (3, 3.0)]
    assert json.loads(progress.read_text(encoding="utf-8"))["next_start_level"] == 4


class ResearchOptimizer:
    seen: dict = {}

    def __init__(self, config) -> None:
        self.config = config

    def run(self, gateway, workspace, *, tool_server):
        tool_server.install()
        type(self).seen = {"prompt": Path(self.config.prompt_path), "mission": gateway.mission,
                           "interface": (Path(workspace) / "AGENT_INTERFACE.md").read_text(encoding="utf-8"),
                           "evaluator": gateway.evaluator.config}
        (Path(workspace) / "world_model.md").write_text("rules", encoding="utf-8")
        return SimpleNamespace(finish_reason="done", turns=1)


def test_campaign_records_the_research_score_and_resumes(tmp_path, monkeypatch) -> None:
    profile = loaded_profile(tmp_path)
    output = tmp_path / "campaign"
    argv = ["evolve", "--output-dir", str(output), "--harness", "opencode"]
    monkeypatch.setattr(sys, "argv", argv)
    with patch("frameworks.avo.evolve.load_profile", return_value=profile), \
            patch("frameworks.avo.evolve.new_workspace", return_value=tmp_path / "optimizer"), \
            patch("frameworks.avo.evolve.CliAgent", ResearchOptimizer):
        evolve.main()

    seen = ResearchOptimizer.seen
    assert seen["prompt"] == evolve.OUTER_PROMPT and seen["interface"] == OPTIMIZER_INTERFACE
    assert LevelProfile.objective in seen["mission"]
    assert Path(seen["evaluator"].player.base_prompt) == DEFAULT_PROMPT_PATH
    config = json.loads((output / "evolution_config.json").read_text(encoding="utf-8"))
    assert config["fitness"] == "research" and config["objective"] == LevelProfile.objective
    assert "fresh_solver_max_environment_steps" not in config and "final_solver" not in config
    assert "research_success" in json.loads((output / "evolution_summary.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", [*argv, "--resume-saved-campaign"])
    with patch("frameworks.avo.evolve.load_profile", return_value=profile), \
            patch("frameworks.avo.evolve.new_workspace", return_value=tmp_path / "optimizer-2"), \
            patch("frameworks.avo.evolve.CliAgent", ResearchOptimizer):
        evolve.main()
    assert ResearchOptimizer.seen["prompt"] == evolve.OUTER_PROMPT


def test_a_solver_score_campaign_cannot_resume(tmp_path, monkeypatch) -> None:
    output = tmp_path / "campaign"
    output.mkdir()
    (output / "lineage.json").write_text(json.dumps({"schema_version": 1, "candidates": [], "evaluations": []}),
                                         encoding="utf-8")
    for saved in ({"harness": "opencode"}, {"harness": "opencode", "fitness": "solver"}):  # no fitness = solver
        (output / "evolution_config.json").write_text(json.dumps(saved), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["evolve", "--output-dir", str(output), "--harness", "opencode",
                                          "--resume-saved-campaign"])
        with patch("frameworks.avo.evolve.load_profile", return_value=loaded_profile(tmp_path)), \
                patch("frameworks.avo.evolve.new_workspace", return_value=tmp_path / "optimizer"), \
                pytest.raises(ValueError, match="archived on 2 Nov 2026"):
            evolve.main()
