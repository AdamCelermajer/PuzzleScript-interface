import json
import random
from pathlib import Path

from client.arc.types import ActionInput, FrameData, GameAction, GameState
from studies.goal_recognition.experiment.collect import (
    action_label,
    collect_random_trajectory,
    collect_three_shot_trajectory,
    choose_random_action,
)
from studies.goal_recognition.experiment.games import load_curated_games
from studies.goal_recognition.experiment.prompts import (
    EVIDENCE_MODES,
    INPUT_MODES,
    PROMPT_ID,
    build_prompt_variants,
)
from studies.goal_recognition.experiment.schema import (
    make_run_paths,
    normalize_prediction,
    prediction_row,
)


def frame(
    step: int,
    actions: list[GameAction] | None = None,
    state: GameState = GameState.PLAYING,
) -> FrameData:
    return FrameData(
        frame=[[[step, 1], [2, 0]]],
        state=state,
        levels_completed=0,
        game_id="dummy",
        win_levels=1,
        guid=f"guid-{step}",
        full_reset=False,
        available_actions=actions if actions is not None else [GameAction.ACTION1],
        action_input=ActionInput(action=GameAction.RESET),
    )


class FakeEnv:
    def __init__(self) -> None:
        self.step_count = 0

    def reset(self) -> FrameData:
        return frame(0, [GameAction.ACTION1, GameAction.ACTION2])

    def step(self, action: GameAction, data=None) -> FrameData:
        self.step_count += 1
        return frame(self.step_count, [GameAction.ACTION1, GameAction.ACTION2])


def test_load_curated_games_reads_exact_50_game_pool() -> None:
    games = load_curated_games()

    assert len(games) == 50
    assert games[0] == "ps_2d_whale_world-v1"
    assert "ps_sokoban_basic-v1" in games
    assert len(set(games)) == 50


def test_choose_random_action_excludes_reset_and_undo_when_possible() -> None:
    action = choose_random_action(
        frame(0, [GameAction.RESET, GameAction.ACTION1, GameAction.ACTION7]),
        random.Random(1),
    )

    assert action == GameAction.ACTION1


def test_choose_random_action_never_uses_reset_or_undo() -> None:
    action = choose_random_action(
        frame(0, [GameAction.RESET, GameAction.ACTION7]),
        random.Random(1),
    )

    assert action is None


def test_three_shot_trajectory_is_seed_deterministic() -> None:
    first = collect_three_shot_trajectory(FakeEnv(), random.Random(5), steps=3)
    second = collect_three_shot_trajectory(FakeEnv(), random.Random(5), steps=3)

    assert first.actions_taken == second.actions_taken
    assert len(first.trajectory) == 4
    assert len(first.actions_taken) == 3
    assert first.trajectory[0]["action"] == "RESET"


def test_one_frame_trajectory_only_resets() -> None:
    result = collect_random_trajectory(FakeEnv(), random.Random(5), steps=0)

    assert result.evidence_mode == "one_frame"
    assert result.actions_taken == []
    assert len(result.trajectory) == 1
    assert result.trajectory[0]["action"] == "RESET"


def test_action_label_includes_click_coordinates() -> None:
    assert action_label(GameAction.ACTION6, {"x": 1, "y": 2}) == (
        'ACTION6 {"x": 1, "y": 2}'
    )


def test_prompt_matrix_uses_single_prompt_with_shared_prefix() -> None:
    trajectory = [
        {"action": "RESET", "grid": [[0, 1], [2, 0]]},
        {"action": "ACTION1", "grid": [[0, 1], [0, 2]]},
    ]

    prompts = build_prompt_variants(
        game_id="ps_sokoban_basic-v1",
        trajectory=trajectory,
        available_actions=["ACTION1", "ACTION2"],
        evidence_mode="three_random_actions",
        first_image_path=Path("dataset/ps_sokoban_basic-v1/screenshot.png"),
    )

    assert set(prompts) == {
        f"three_random_actions/{input_mode}/{PROMPT_ID}"
        for input_mode in INPUT_MODES
    }
    for key, payload in prompts.items():
        assert key == (
            f"{payload['evidence_mode']}/{payload['input_mode']}/"
            f"{payload['prompt_id']}"
        )
        assert "system" in payload
        assert "prompt" in payload
        assert payload["prompt"] == payload["prompt_prefix"] + payload["prompt_suffix"]
        assert "ps_sokoban_basic-v1" not in payload["prompt"]
        assert "ACTION1" in payload["prompt"]
        assert "01" in payload["prompt"]
        assert "[0, 1]" not in payload["prompt"]
        assert "Do not use hidden metadata" not in payload["prompt"]


def test_numeric_plus_first_image_prompt_carries_image_attachment() -> None:
    prompts = build_prompt_variants(
        game_id="ps_sokoban_basic-v1",
        trajectory=[{"action": "RESET", "grid": [[0, 1], [2, 0]]}],
        available_actions=["ACTION1"],
        first_image_path=Path("dataset/ps_sokoban_basic-v1/screenshot.png"),
    )

    image_payload = prompts[f"three_random_actions/text_plus_first_image/{PROMPT_ID}"]
    text_payload = prompts[f"three_random_actions/text_only/{PROMPT_ID}"]

    assert image_payload["image_paths"] == [
        "dataset\\ps_sokoban_basic-v1\\screenshot.png"
    ] or image_payload["image_paths"] == [
        "dataset/ps_sokoban_basic-v1/screenshot.png"
    ]
    assert "first rendered screenshot" in image_payload["prompt"].lower()
    assert text_payload["image_paths"] == []


def test_image_prompt_keeps_text_prefix_cacheable() -> None:
    prompts = build_prompt_variants(
        game_id="ps_sokoban_basic-v1",
        trajectory=[{"action": "RESET", "grid": [[0, 1], [2, 0]]}],
        available_actions=["ACTION1"],
        first_image_path=Path("dataset/ps_sokoban_basic-v1/screenshot.png"),
    )

    systems = {payload["system"] for payload in prompts.values()}
    assert len(systems) == 1

    text_prompt = prompts[f"three_random_actions/text_only/{PROMPT_ID}"]
    image_prompt = prompts[f"three_random_actions/text_plus_first_image/{PROMPT_ID}"]

    assert text_prompt["prompt_prefix"] == image_prompt["prompt_prefix"]
    assert text_prompt["prompt"].startswith(text_prompt["prompt_prefix"])
    assert image_prompt["prompt"].startswith(text_prompt["prompt_prefix"])


def test_run_paths_keep_outputs_inside_run_directory(tmp_path: Path) -> None:
    paths = make_run_paths(tmp_path, "run-1")

    assert paths.run_dir == tmp_path / "run-1"
    assert paths.manifest == paths.run_dir / "manifest.json"
    assert paths.sources == paths.run_dir / "sources"
    assert paths.evidence == paths.run_dir / "evidence"
    assert paths.trajectories == paths.run_dir / "trajectories"
    assert paths.prompts == paths.run_dir / "prompts"
    assert paths.batches == paths.run_dir / "batches"
    assert paths.predictions == paths.run_dir / "predictions.jsonl"
    assert paths.errors == paths.run_dir / "errors.jsonl"
    assert paths.skips == paths.run_dir / "skips.jsonl"


def test_normalize_prediction_defaults_wrong_types() -> None:
    assert normalize_prediction(
        {
            "goal_guess": None,
            "win_condition_guess": 7,
            "key_objects": "player",
            "confidence": "bad",
            "uncertainties": "unknown",
            "rationale": None,
        }
    ) == {
        "goal_guess": "",
        "win_condition_guess": "7",
        "key_objects": [],
        "confidence": 0.0,
        "uncertainties": [],
        "rationale": "",
    }


def test_prediction_row_has_stable_json_shape() -> None:
    row = prediction_row(
        run_id="run-1",
        game_id="game",
        evidence_mode="one_frame",
        input_mode="text_only",
        prompt_id=PROMPT_ID,
        model="openai/gpt-5.5",
        trajectory_path=Path("trajectories/game.json"),
        prompt_path=Path("prompts/game/one_frame/text_only/goal_recognition_v1.json"),
        raw_response={"goal_guess": " Reach target. ", "confidence": "0.8"},
    )

    assert json.loads(json.dumps(row)) == row
    assert row["prediction"]["goal_guess"] == "Reach target."
    assert row["prediction"]["confidence"] == 0.8
    assert row["manual_verification"] is None


def test_prediction_row_includes_matrix_dimensions() -> None:
    row = prediction_row(
        run_id="run-1",
        game_id="game",
        evidence_mode="three_random_actions",
        input_mode="text_plus_first_image",
        prompt_id=PROMPT_ID,
        model="moonshotai/kimi-k2.6",
        trajectory_path=Path("trajectories/game.json"),
        prompt_path=Path("prompts/game/three_random_actions/text_plus_first_image/goal_recognition_v1.json"),
        raw_response={},
    )

    assert row["evidence_mode"] == "three_random_actions"
    assert row["input_mode"] == "text_plus_first_image"
    assert row["prompt_id"] == PROMPT_ID
    assert row["model"] == "moonshotai/kimi-k2.6"
