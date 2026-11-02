from frameworks import world_model
from frameworks.avo.evolution.gateway import FINAL_WORLD_MODEL_PROMPT


def test_copies_skip_a_missing_file_then_follow_actions_levels_and_the_end(tmp_path):
    source = tmp_path / "ws" / "world_model.md"
    copies = world_model.Snapshots(source, tmp_path / "out", every=3)
    copies.after_action(3, 0, 0)  # the player has not written it yet: nothing to copy
    source.parent.mkdir()
    source.write_text("v1")
    copies.after_action(4, 0, 1)
    copies.after_action(6, 1, 1)
    source.write_text("v2")
    copies.final()
    out = tmp_path / "out" / world_model.SNAPSHOT_DIR
    assert sorted(p.name for p in out.iterdir()) == ["a0006.md", "final.md", "level-1-a0004.md"]
    assert (out / "level-1-a0004.md").read_text() == "v1" and (out / "final.md").read_text() == "v2"


def test_every_player_uses_one_format():
    assert FINAL_WORLD_MODEL_PROMPT == world_model.final_prompt()  # AVO's optimizer report, unchanged
    assert world_model.final_prompt("notes/world_model.md").startswith(
        "Write notes/world_model.md in your current workspace now.")
    assert world_model.keep_instruction().startswith("Keep world_model.md as your current model of the game")
