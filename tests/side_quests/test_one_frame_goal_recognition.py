import json
from pathlib import Path
from types import SimpleNamespace
from urllib import request

from client.engine.llm_client import Config
from side_quests.one_frame_goal_recognition.prompt import build_prompt
from side_quests.one_frame_goal_recognition import run as run_module
from side_quests.one_frame_goal_recognition.run import (
    OpenRouterJsonClient,
    completed_game_ids,
    normalize_prediction,
    parse_args,
    run_batch,
    write_jsonl,
)


def test_prompt_uses_compact_numeric_grid() -> None:
    _, prompt = build_prompt(
        game_id="ls20",
        grid=[[0, 11], [2, 0]],
        available_actions=["ACTION1"],
    )

    assert "0b" in prompt
    assert "20" in prompt
    assert "b=11" in prompt
    assert "[0, 11]" not in prompt


def test_prompt_contains_grid_and_actions_without_game_identity() -> None:
    system, prompt = build_prompt(
        game_id="ls20",
        grid=[[0, 1], [2, 0]],
        available_actions=["ACTION1", "ACTION2"],
    )

    assert "goal recognition" in system.lower()
    assert "01" in prompt
    assert "20" in prompt
    assert "ACTION1" in prompt
    assert "ACTION2" in prompt
    assert "ls20" not in prompt
    assert "game source" not in prompt.lower()
    assert "readme" not in prompt.lower()
    assert "known solution" not in prompt.lower()


def test_normalize_prediction_keeps_expected_schema() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": " Reach the target. ",
            "win_condition_guess": "Player overlaps target.",
            "key_objects": [{"value": 2, "role_guess": "player"}],
            "confidence": "0.7",
            "uncertainties": ["one frame only"],
            "extra": "ignored",
        }
    )

    assert prediction == {
        "goal_guess": "Reach the target.",
        "win_condition_guess": "Player overlaps target.",
        "key_objects": [{"value": 2, "role_guess": "player"}],
        "confidence": 0.7,
        "uncertainties": ["one frame only"],
    }


def test_normalize_prediction_defaults_wrong_types() -> None:
    prediction = normalize_prediction(
        {
            "goal_guess": None,
            "win_condition_guess": None,
            "key_objects": "player",
            "confidence": "not-a-number",
            "uncertainties": "unclear",
        }
    )

    assert prediction == {
        "goal_guess": "",
        "win_condition_guess": "",
        "key_objects": [],
        "confidence": 0.0,
        "uncertainties": [],
    }


def test_completed_game_ids_reads_predictions_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    write_jsonl(path, {"game_id": "a", "prediction": {}})
    write_jsonl(path, {"game_id": "b", "prediction": {}})
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert completed_game_ids(path) == {"a", "b"}


def test_completed_game_ids_ignores_rows_without_game_id(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(json.dumps({"prediction": {}}) + "\n", encoding="utf-8")

    assert completed_game_ids(path) == set()


def test_parse_args_defaults_to_ten_game_batches() -> None:
    args = parse_args(["--api-key", "arc-key"])

    assert args.batch_size == 10


def test_openrouter_json_client_parses_message_content(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self):
            self._body = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "goal_guess": "Reach the target.",
                                        "confidence": 0.8,
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")
            self._sent = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int = -1) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return self._body

    captured = {}

    def fake_urlopen(api_request: request.Request, timeout: float):
        captured["timeout"] = timeout
        captured["body"] = json.loads(api_request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(run_module.request, "urlopen", fake_urlopen)
    client = OpenRouterJsonClient(
        Config(
            server_url="https://three.arcprize.org",
            flash_model="deepseek/deepseek-v4-pro",
            pro_model="deepseek/deepseek-v4-pro",
            game="goal_recognition",
            mode="one_frame",
            openrouter_api_key="key",
        )
    )

    response = client.call_json(
        "system",
        "prompt",
        model_type="flash",
        timeout_seconds=12,
    )

    assert response["goal_guess"] == "Reach the target."
    assert captured["timeout"] == 12
    assert captured["body"]["model"] == "deepseek/deepseek-v4-pro"
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_openrouter_json_client_zero_timeout_disables_urlopen_timeout(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int = -1) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({"goal_guess": "Escape."})
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    captured = {}

    def fake_urlopen(api_request: request.Request, timeout):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(run_module.request, "urlopen", fake_urlopen)
    client = OpenRouterJsonClient(
        Config(
            server_url="https://three.arcprize.org",
            flash_model="deepseek/deepseek-v4-pro",
            pro_model="deepseek/deepseek-v4-pro",
            game="goal_recognition",
            mode="one_frame",
            openrouter_api_key="key",
        )
    )

    assert client.call_json(
        "system",
        "prompt",
        model_type="flash",
        timeout_seconds=0,
    ) == {"goal_guess": "Escape."}
    assert captured["timeout"] is None


def test_run_batch_writes_predictions_and_errors(tmp_path: Path, monkeypatch) -> None:
    def fake_run_game_job(game_id, args, llm, frames_dir, prompts_dir):
        if game_id == "bad":
            return "error", {"game_id": game_id, "error": "boom"}
        return "prediction", {"game_id": game_id, "prediction": {}}

    monkeypatch.setattr(run_module, "run_game_job", fake_run_game_job)
    predictions_path = tmp_path / "predictions.jsonl"
    errors_path = tmp_path / "errors.jsonl"

    run_batch(
        ["good", "bad"],
        SimpleNamespace(),
        object(),
        tmp_path / "frames",
        tmp_path / "prompts",
        predictions_path,
        errors_path,
    )

    predictions = [
        json.loads(line)
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
    ]
    errors = [
        json.loads(line)
        for line in errors_path.read_text(encoding="utf-8").splitlines()
    ]
    assert predictions == [{"game_id": "good", "prediction": {}}]
    assert errors == [{"game_id": "bad", "error": "boom"}]
