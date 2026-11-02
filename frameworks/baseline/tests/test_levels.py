import json

from frameworks import levels
from workbench.catalog import level_fields


def move(before, after, total=4):
    return {"before": {"levels_completed": before, "win_levels": total},
            "after": {"levels_completed": after, "win_levels": total}}


def test_shortest_is_known_or_none():
    assert levels.shortest("ps_modality-v1", 4) == 158
    assert levels.shortest("ps_modality-v1", 5) is None and levels.shortest("ps_unknown-v1", 1) is None


def test_stop_after_levels_counts_from_the_start_level():
    assert levels.stop_target(1, 0) == 0 and levels.stop_target(1, 2) == 2 and levels.stop_target(3, 1) == 3


def test_every_level_played_is_scored_and_the_unseen_next_level_is_not():
    # From level 2: 7 moves solve it, 4 more are spent on level 3 without solving it.
    records = [move(1, 1)] * 6 + [move(1, 2)] + [move(2, 2)] * 4
    assert levels.level_scores(records, "ps_modality-v1", 2) == [
        {"level": 2, "solved": True, "moves": 7, "shortest": 33, "ratio": 0.21},
        {"level": 3, "solved": False, "moves": 4, "shortest": 66, "ratio": None}]
    # The one-level task stops at level 2's win: level 3 is not part of it.
    assert [s["level"] for s in levels.level_scores(records[:7], "ps_modality-v1", 2, 1)] == [2]
    # The last level of a game: nothing after it.
    assert [s["level"] for s in levels.level_scores([move(3, 4)], "ps_modality-v1", 4)] == [4]


def test_result_fields_without_moves_score_the_start_level_unsolved(tmp_path):
    fields = levels.result_fields(tmp_path / "missing.jsonl", "ps_icecrates-v1", 3, 1)
    assert fields["levels"] == [{"level": 3, "solved": False, "moves": 0, "shortest": 12, "ratio": None}]
    path = tmp_path / "transitions.jsonl"
    path.write_text("\n".join(json.dumps(move(2, 2, 6)) for _ in range(23)) + "\n" + json.dumps(move(2, 3, 6)) + "\n")
    fields = levels.result_fields(path, "ps_icecrates-v1", 3, 1)
    assert (fields["start_level"], fields["level_solved"], fields["level_moves"], fields["level_shortest"],
            fields["level_ratio"]) == (3, True, 24, 12, 2.0)


def test_catalog_marks_one_level_tasks_and_older_first_level_runs():
    result = {"level_solved": True, "level_moves": 9, "level_shortest": 6, "level_ratio": 1.5}
    assert level_fields({"start_level": 3, "stop_after_levels": 1}, {}, result) == {
        "start_level": 3, "level": 3, "level_score": {"solved": True, "moves": 9, "shortest": 6, "ratio": 1.5}}
    assert level_fields({}, {"start_level": 2, "one_level": True}, {})["level"] == 2  # queued: options only
    assert level_fields({"stop_after_levels": 1}, {}, {}) == {"start_level": 1, "level": 1, "level_score": None}
    assert level_fields({"start_level": 2}, {}, {})["level"] is None  # plays on from level 2
