from pathlib import Path

from side_quests.goal_recognition_review.report import count_labels, svg_bar_chart
from side_quests.goal_recognition_review.review import (
    apply_verification,
    load_rows,
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
