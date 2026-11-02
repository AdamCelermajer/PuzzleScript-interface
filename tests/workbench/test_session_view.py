"""Run page extras: diffs for file edits from raw turn records, and the prompts each turn received."""
import json
from pathlib import Path

from workbench.experiments import read_agent_events
from workbench.harness2_view import harness_diffs
from workbench.session_view import session_prompts


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _tool(tool: str, args: dict, metadata: dict | None = None) -> dict:
    return {"type": "tool_use", "part": {"tool": tool, "state": {"input": args, "metadata": metadata or {}, "output": "ok"}}}


def test_file_changes_get_diffs_from_raw_opencode_turns(tmp_path):
    _jsonl(tmp_path / "raw/turn-1.jsonl", [_tool("write", {"filePath": "/w/notes.md", "content": "a\nb\n"}, {"exists": False})])
    _jsonl(tmp_path / "raw/turn-2.jsonl", [
        _tool("edit", {"filePath": "/w/notes.md", "oldString": "b", "newString": "c"}),
        _tool("write", {"filePath": "/w/notes.md", "content": "a\nc\nd\n"}, {"exists": True}),
        _tool("write", {"filePath": "/w/other.md", "content": "x\n"}, {"exists": True}),
    ])
    _jsonl(tmp_path / "agent_events.jsonl", [
        {"type": "file_change", "turn": 1, "text": "/w/notes.md"},
        {"type": "message", "turn": 1, "text": "hi"},
        {"type": "file_change", "turn": 2, "text": "/w/notes.md"},
        {"type": "file_change", "turn": 2, "text": "/w/notes.md"},
        {"type": "file_change", "turn": 2, "text": "/w/other.md"},
    ])
    events = [e for e in read_agent_events(tmp_path / "agent_events.jsonl", 500)["events"] if e["type"] == "file_change"]
    assert events[0]["diff_note"] == "new file" and "+a" in events[0]["diff"]
    # The edit is applied to the known content, so the next whole-file write diffs against it.
    assert "-b" in events[1]["diff"] and "+c" in events[1]["diff"]
    assert "+d" in events[2]["diff"] and "-c" not in events[2]["diff"]
    assert "not recorded" in events[3]["diff_note"]
    assert all("_turn" not in e and "_file_index" not in e for e in events)


def test_windowed_events_still_match_their_raw_edit(tmp_path):
    _jsonl(tmp_path / "raw/turn-1.jsonl", [
        _tool("write", {"filePath": "/w/a.md", "content": "1\n"}, {"exists": False}),
        _tool("write", {"filePath": "/w/b.md", "content": "2\n"}, {"exists": False}),
    ])
    _jsonl(tmp_path / "agent_events.jsonl", [
        {"type": "file_change", "turn": 1, "text": "/w/a.md"},
        {"type": "file_change", "turn": 1, "text": "/w/b.md"},
    ])
    (only,) = read_agent_events(tmp_path / "agent_events.jsonl", 1)["events"]
    assert "b/w/b.md" in only["diff"] and "+2" in only["diff"]


def test_turn_prompts_follow_the_session_turns_and_skip_retries(tmp_path):
    (tmp_path / "system_prompt.txt").write_text("system", encoding="utf-8")
    _jsonl(tmp_path / "transcript.jsonl", [{"decision": 1, "prompt": "first"}, {"decision": 2, "prompt": "second"}])
    _jsonl(tmp_path / "turns.jsonl", [
        {"turn": 1, "turn_kind": "game_action", "text": "", "error": ""},
        {"turn": 2, "turn_kind": "game_action", "text": "", "error": "503 overloaded"},
        {"turn": 3, "turn_kind": "game_action", "text": "", "error": ""},
        {"turn": 4, "turn_kind": "final_world_model", "text": "", "error": ""},
    ])
    prompts = session_prompts(tmp_path)
    assert prompts["system"] == "system" and prompts["turns_recorded"]
    assert prompts["turns"] == {"1": "first", "2": "second", "3": "second"}


def test_session_without_turn_records_reports_only_its_system_prompt(tmp_path):
    (tmp_path / "mission.md").write_text("mission", encoding="utf-8")
    prompts = session_prompts(tmp_path)
    assert prompts == {"system": None, "mission": "mission", "turns": {}, "turns_recorded": False}


def test_stage_harness_diffs_against_the_starting_harness(tmp_path):
    (tmp_path / "harnesses/base").mkdir(parents=True)
    (tmp_path / "harnesses/base/systemprompt.md").write_text("old\n", encoding="utf-8")
    (tmp_path / "harnesses/inv1/skills").mkdir(parents=True)
    (tmp_path / "harnesses/inv1/systemprompt.md").write_text("new\n", encoding="utf-8")
    (tmp_path / "harnesses/inv1/skills/tip.md").write_text("tip\n", encoding="utf-8")
    diffs = harness_diffs(tmp_path)["inv1"]
    assert "-old" in diffs["systemprompt.md"] and "+new" in diffs["systemprompt.md"]
    assert "+tip" in diffs["skills/tip.md"]
