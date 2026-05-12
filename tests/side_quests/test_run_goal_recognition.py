import json
from pathlib import Path

from side_quests.run_goal_recognition import count_jsonl, run_counts


def test_count_jsonl_ignores_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")

    assert count_jsonl(path) == 2


def test_run_counts_reads_latest_manifest_predictions_and_errors(tmp_path: Path) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (new / "manifest.json").write_text(
        json.dumps({"games": ["a", "b", "c"]}),
        encoding="utf-8",
    )
    (new / "predictions.jsonl").write_text('{"game_id": "a"}\n', encoding="utf-8")
    (new / "errors.jsonl").write_text('{"game_id": "b"}\n', encoding="utf-8")

    predictions, errors, total, run_dir = run_counts(tmp_path)

    assert predictions == 1
    assert errors == 1
    assert total == 3
    assert run_dir == new
