import json

from frameworks.baseline.agent_files import FileHistory


def test_every_added_changed_and_deleted_file_is_recorded_with_its_copy(tmp_path):
    folder, output = tmp_path / "work", tmp_path / "run"
    folder.mkdir()
    (folder / "frame.png").write_bytes(b"ours")  # the controller's picture is not the player's file
    history = FileHistory(folder, output)
    history.capture(0, "at the start")
    (folder / "notes.md").write_text("ACTION1 = up", encoding="utf-8")
    (folder / "scripts").mkdir()
    (folder / "scripts" / "solve.py").write_text("print(1)", encoding="utf-8")
    history.capture(3, "after 3 moves")
    history.capture(4, "after 4 moves")  # nothing changed: nothing recorded
    (folder / "notes.md").write_text("ACTION1 = up\nACTION2 = down", encoding="utf-8")
    (folder / "scripts" / "solve.py").unlink()
    history.capture(5, "after 5 moves")
    rows = [json.loads(line) for line in (output / "agent_files" / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["at"], r["path"], r["status"]) for r in rows] == [
        (3, "notes.md", "added"), (3, "scripts/solve.py", "added"),
        (5, "notes.md", "changed"), (5, "scripts/solve.py", "deleted")]
    assert (output / "agent_files" / rows[2]["file"]).read_text(encoding="utf-8") == "ACTION1 = up\nACTION2 = down"
    assert rows[3]["file"] is None
