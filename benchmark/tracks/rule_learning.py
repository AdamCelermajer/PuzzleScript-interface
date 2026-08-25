from __future__ import annotations

from collections import defaultdict
from typing import Any


def _shape(grid: Any) -> tuple[int, int] | None:
    if not isinstance(grid, list) or not grid or not all(
        isinstance(row, list) for row in grid
    ):
        return None
    widths = {len(row) for row in grid}
    if len(widths) != 1:
        return None
    return len(grid), next(iter(widths))


def _edits(
    before: list[list[int]],
    after: list[list[int]],
) -> set[tuple[int, int, int, int]]:
    return {
        (row, col, before[row][col], after[row][col])
        for row in range(len(before))
        for col in range(len(before[row]))
        if before[row][col] != after[row][col]
    }


def _cell_metrics(
    before: list[list[int]],
    expected: list[list[int]],
    predicted: Any,
) -> tuple[bool, float, float, float]:
    expected_shape = _shape(expected)
    if expected_shape is None or _shape(before) != expected_shape:
        return False, 0.0, 0.0, 0.0
    if _shape(predicted) != expected_shape:
        return False, 0.0, 0.0, 0.0
    cells = expected_shape[0] * expected_shape[1]
    correct = sum(
        predicted[row][col] == expected[row][col]
        for row in range(expected_shape[0])
        for col in range(expected_shape[1])
    )
    expected_positions = {
        (row, col)
        for row, col, _old, _new in _edits(before, expected)
    }
    predicted_positions = {
        (row, col)
        for row, col, _old, _new in _edits(before, predicted)
    }
    position_overlap = len(expected_positions & predicted_positions)
    if not expected_positions and not predicted_positions:
        changed_f1 = 1.0
    else:
        precision = (
            position_overlap / len(predicted_positions)
            if predicted_positions
            else 0.0
        )
        recall = (
            position_overlap / len(expected_positions)
            if expected_positions
            else 0.0
        )
        changed_f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    expected_edits = _edits(before, expected)
    predicted_edits = _edits(before, predicted)
    edit_overlap = len(expected_edits & predicted_edits)
    if not expected_edits and not predicted_edits:
        edit_f1 = 1.0
    else:
        precision = (
            edit_overlap / len(predicted_edits) if predicted_edits else 0.0
        )
        recall = (
            edit_overlap / len(expected_edits) if expected_edits else 0.0
        )
        edit_f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return (
        predicted == expected,
        correct / cells if cells else 0.0,
        changed_f1,
        edit_f1,
    )


def _game_score(
    probes: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    totals = {
        "exact_frame": 0.0,
        "cell_accuracy": 0.0,
        "changed_cell_f1": 0.0,
        "transition_edit_f1": 0.0,
    }
    answered = 0
    correct_rule_families: set[str] = set()
    tested_rule_families: set[str] = set()
    for probe in probes:
        tested_rule_families.update(probe.get("fired_rule_ids") or [])
        prediction = predictions.get(str(probe["probe_id"]))
        if prediction is None:
            continue
        answered += 1
        exact, cell_accuracy, changed_f1, edit_f1 = _cell_metrics(
            probe["before_frame"],
            probe["expected_frame"],
            prediction.get("predicted_frame"),
        )
        totals["exact_frame"] += float(exact)
        totals["cell_accuracy"] += cell_accuracy
        totals["changed_cell_f1"] += changed_f1
        totals["transition_edit_f1"] += edit_f1
        if exact:
            correct_rule_families.update(probe.get("fired_rule_ids") or [])
    divisor = len(probes) or 1
    return {
        "probes": len(probes),
        "answered": answered,
        "coverage": round(answered / len(probes), 6) if probes else 0.0,
        **{
            key: round(value / divisor, 6)
            for key, value in totals.items()
        },
        "rule_families_tested": len(tested_rule_families),
        "rule_families_correct": len(correct_rule_families),
    }


def score_rule_predictions(
    probes: list[dict[str, Any]],
    submitted_predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    predictions = {
        str(item["probe_id"]): item
        for item in submitted_predictions
        if item.get("probe_id")
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for probe in probes:
        grouped[str(probe["game_alias"])].append(probe)
    games = [
        {"alias": alias, **_game_score(game_probes, predictions)}
        for alias, game_probes in sorted(grouped.items())
    ]
    divisor = len(games) or 1
    metric_names = [
        "exact_frame",
        "cell_accuracy",
        "changed_cell_f1",
        "transition_edit_f1",
        "coverage",
    ]
    return {
        "track": "rule_learning",
        "mode": "hidden_transition_challenges",
        "primary_metric": "macro_exact_frame_accuracy",
        "games": games,
        "summary": {
            metric: round(sum(game[metric] for game in games) / divisor, 6)
            for metric in metric_names
        },
    }
