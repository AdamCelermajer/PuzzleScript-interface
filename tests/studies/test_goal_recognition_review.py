import os
from pathlib import Path

from studies.goal_recognition.review.report import count_labels, svg_bar_chart
from studies.goal_recognition.review.review import (
    apply_verification,
    find_evidence_file,
    format_compact_review_grid,
    format_review_grid,
    load_rows,
    load_review_evidence,
    parse_args,
    review_evidence_grid,
    write_rows,
)


def test_apply_verification_sets_label_and_note() -> None:
    row = {"game_id": "ls20", "manual_verification": None}

    updated = apply_verification(row, label="correct", note="goal matched")

    assert updated["manual_verification"] == {
        "label": "correct",
        "note": "goal matched",
    }


def test_load_and_write_rows_round_trip_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    rows = [
        {"game_id": "a", "manual_verification": None},
        {"game_id": "b", "manual_verification": {"label": "wrong", "note": ""}},
    ]

    write_rows(path, rows)

    assert load_rows(path) == rows


def test_load_rows_accepts_utf8_bom_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '\ufeff{"game_id": "a", "manual_verification": null}\n',
        encoding="utf-8",
    )

    assert load_rows(path) == [{"game_id": "a", "manual_verification": None}]


def test_review_defaults_to_browser_verification() -> None:
    args = parse_args(["--predictions", "predictions.jsonl"])

    assert args.play is False


def test_review_can_still_launch_terminal_player() -> None:
    args = parse_args(["--predictions", "predictions.jsonl", "--play"])

    assert args.play is True


def test_load_review_evidence_prefers_embedded_row_data() -> None:
    row = {
        "review_evidence": {
            "frames": [[[1, 2], [3, 4]]],
            "available_actions": ["ACTION6"],
        }
    }

    assert load_review_evidence(row, roots=[]) == row["review_evidence"]


def test_find_evidence_file_loads_latest_frame_artifact(tmp_path: Path) -> None:
    old_file = tmp_path / "old" / "frames" / "tn36-ef4dde99.json"
    new_file = tmp_path / "new" / "frames" / "tn36-ef4dde99.json"
    old_file.parent.mkdir(parents=True)
    new_file.parent.mkdir(parents=True)
    old_file.write_text(
        '{"frames": [[[1]]], "available_actions": ["ACTION6"]}\n',
        encoding="utf-8",
    )
    new_file.write_text(
        '{"frames": [[[2]]], "available_actions": ["ACTION6"]}\n',
        encoding="utf-8",
    )
    os.utime(old_file, (1, 1))
    os.utime(new_file, (2, 2))

    found = find_evidence_file({"game_id": "tn36-ef4dde99"}, [tmp_path])
    evidence = load_review_evidence(
        {"game_id": "tn36-ef4dde99", "setup": "one_frame"},
        roots=[tmp_path],
    )

    assert found == new_file
    assert evidence is not None
    assert evidence["frames"] == [[[2]]]


def test_format_review_grid_uses_fixed_width_numbers() -> None:
    assert format_review_grid([[1, 11], [0, 5]]) == " 1 11\n 0  5"


def test_format_compact_review_grid_matches_prompt_symbols() -> None:
    assert format_compact_review_grid([[0, 11], [2, 0]]) == "0b\n20"


def test_review_evidence_grid_uses_latest_trajectory_frame() -> None:
    label, grid = review_evidence_grid(
        {
            "trajectory": [
                {"action": "RESET", "grid": [[1]]},
                {"action": "ACTION6 {\"x\": 1, \"y\": 0}", "grid": [[2]]},
            ]
        }
    )

    assert label.startswith("Latest observation 1")
    assert grid == [[2]]


def test_count_labels_groups_by_setup_and_label() -> None:
    rows = [
        {"setup": "one_frame", "manual_verification": {"label": "correct"}},
        {"setup": "one_frame", "manual_verification": {"label": "wrong"}},
        {"setup": "ten_frame_random", "manual_verification": {"label": "partial"}},
    ]

    counts = count_labels(rows)

    assert counts["one_frame"]["correct"] == 1
    assert counts["one_frame"]["wrong"] == 1
    assert counts["ten_frame_random"]["partial"] == 1


def test_svg_bar_chart_contains_setup_labels() -> None:
    svg = svg_bar_chart(
        {
            "one_frame": {"correct": 2, "partial": 1, "wrong": 1, "skipped": 0},
            "ten_frame_random": {
                "correct": 3,
                "partial": 0,
                "wrong": 1,
                "skipped": 1,
            },
        }
    )

    assert "<svg" in svg
    assert "one_frame" in svg
    assert "ten_frame_random" in svg
