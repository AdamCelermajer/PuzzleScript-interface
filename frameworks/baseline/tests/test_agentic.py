import base64
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from game.types import GameAction, GameState

from frameworks.baseline import agentic as player
from frameworks.baseline import prompt as baseline_prompt
from frameworks.baseline.agentic import GameServer, play

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()


class Corridor:
    """Player 5 walks right along one row; reaching the end completes the level."""

    def __init__(self, width=3, levels=2):
        self.width, self.levels, self.done, self.position = width, levels, 0, 0

    def _frame(self):
        row = [2] * self.width
        row[self.position] = 5
        won = self.done >= self.levels
        return SimpleNamespace(frame=[[row]], state=GameState.WIN if won else GameState.PLAYING,
                               levels_completed=self.done, win_levels=self.levels,
                               available_actions=[GameAction.ACTION3, GameAction.ACTION4],
                               rendered_frame=SimpleNamespace(data_url=PNG))

    def reset(self):
        self.position = 0
        return self._frame()

    def step(self, action, data=None):
        self.position = max(0, self.position + (1 if action == GameAction.ACTION4 else -1))
        if self.position == self.width - 1:
            self.done, self.position = self.done + 1, 0
        return self._frame()


def game(workspace, *args):
    out = subprocess.run([sys.executable, "game.py", *args], cwd=workspace, capture_output=True, text=True, timeout=30)
    return out.returncode, out.stdout


def test_game_command_plays_records_and_enforces_the_budget(tmp_path):
    workspace, output = tmp_path / "ws", tmp_path / "out"
    workspace.mkdir()
    server = GameServer(Corridor(), workspace, output, max_steps=3).start()
    try:
        code, text = game(workspace, "look")
        assert code == 0 and "levels=0/2 actions_used=0/3" in text and "5 2 2" in text
        assert "available_actions=ACTION3, ACTION4, RESET" in text
        assert (workspace / "frame.png").read_bytes() == b"\x89PNG fake"
        code, text = game(workspace, "do", "action4")
        assert code == 0 and text.startswith("Last action: ACTION4: changed (0,0) 5->2, (0,1) 2->5")
        code, text = game(workspace, "do", "ACTION4")
        assert "LEVEL COMPLETED (1/2)" in text
        assert game(workspace, "do", "ACTION9")[0] == 1
        code, text = game(workspace, "do", "reset")  # RESET is one more action
        assert code == 0 and "actions_used=3/3" in text
        code, text = game(workspace, "do", "ACTION4")
        assert code == 1 and "step_budget_exhausted" in text
    finally:
        server.stop()
    rows = [json.loads(line) for line in (output / "transitions.jsonl").read_text().splitlines()]
    assert [r["action"] for r in rows] == ["ACTION4", "ACTION4", "RESET"] and [r["action_index"] for r in rows] == [1, 2, 3]
    assert rows[1]["after"]["levels_completed"] == 1 and rows[0]["changed_cells"][0] == {"row": 0, "col": 0, "before": 5, "after": 2}
    assert sorted(p.name for p in (output / "frames").iterdir()) == ["000.png", "001.png", "002.png", "003.png"]


class ScriptedSession:
    """Stands in for a harness session: each turn runs some game.py commands in the workspace."""

    def __init__(self, plan):
        self.plan, self.instructions, self.turn_number = list(plan), [], 0

    def start(self, workspace, system_prompt, model, effort, role, analysis_dir, provider=""):
        self.workspace, self.system_prompt = Path(workspace), system_prompt
        assert (self.workspace / "AGENTS.md").read_text() == "Coach advice"
        return self

    def turn(self, instruction, images=(), timeout=None):
        self.turn_number += 1
        self.instructions.append(instruction)
        if instruction.startswith("The game has ended"):
            self.refused = game(self.workspace, "do", "ACTION4")  # the game is closed for the final reports
            (self.workspace / "world_model.md").write_text("ACTION4 moves right.")
        else:
            for args in (self.plan.pop(0) if self.plan else []):
                game(self.workspace, *args)
            (self.workspace / "notes.md").write_text(f"turn {len(self.instructions)}")
        return SimpleNamespace(text="ok", error="", timed_out=False, events=[])

    def close(self):
        pass


def test_play_continues_the_same_session_until_done_and_keeps_the_folder(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "AGENTS.md").write_text("Coach advice")
    session = ScriptedSession([[("look",), ("do", "ACTION4")], [("do", "ACTION4"), ("do", "ACTION4"), ("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=harness)
    assert result["levels_completed"] == 2 and result["solved"] and result["reason"] == "task_goal_reached"
    assert result["action_count"] == 4 and result["agent_turns"] == 2
    assert "levels 0/2, 9 of 10 actions left" in session.instructions[1]
    assert (tmp_path / "out" / "world_model.md").read_text() == "ACTION4 moves right."
    kept = tmp_path / "out" / "workspace"
    assert (kept / "notes.md").read_text() == "turn 2" and (kept / "AGENTS.md").is_file() and not (kept / ".game").exists()


def test_play_stops_an_idle_agent(tmp_path, monkeypatch):
    session = ScriptedSession([[("look",)], [], []])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "AGENTS.md").write_text("Coach advice")
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=harness)
    assert result["reason"] == "agent_idle" and result["agent_turns"] == 2 and result["action_count"] == 0
    assert session.refused[0] == 1 and "No more actions" in session.refused[1]  # 10 actions left, still refused
    assert result["solver"] is None  # both drivers end with the world-model report only


class FlakySession(ScriptedSession):
    """The provider fails each turn's first attempt, as NanoGPT's 503s did."""

    def turn(self, instruction, images=(), timeout=None):
        if len(self.instructions) == 0 or self.instructions[-1] != "FAILED " + instruction:
            self.instructions.append("FAILED " + instruction)
            return SimpleNamespace(text="", error="Service temporarily unavailable. Please try again later.",
                                   timed_out=False, events=[])
        self.instructions.pop()
        return super().turn(instruction, images, timeout)


def test_provider_hiccups_are_retried_and_the_report_still_arrives(tmp_path, monkeypatch):
    session = FlakySession([[("do", "ACTION4"), ("do", "ACTION4"), ("do", "ACTION4"), ("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    monkeypatch.setattr(player.time, "sleep", lambda seconds: None)
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "AGENTS.md").write_text("Coach advice")
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=harness)
    assert result["status"] == "completed" and result["levels_completed"] == 2
    assert (tmp_path / "out" / "world_model.md").read_text() == "ACTION4 moves right."


def test_the_prompt_is_the_shared_one_and_notes_are_mirrored_live(tmp_path, monkeypatch):
    class NoteTaker(ScriptedSession):
        def turn(self, instruction, images=(), timeout=None):
            if not instruction.startswith("The game has ended"):
                (self.workspace / "notes").mkdir(exist_ok=True)
                (self.workspace / "notes" / "strategy.md").write_text("ACTION4 = right")
            return super().turn(instruction, images, timeout)

    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "AGENTS.md").write_text("Coach advice")
    session = NoteTaker([[("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
         max_steps=10, max_wall_seconds=0, harness_dir=harness, notes=True)
    assert session.system_prompt == baseline_prompt.system_prompt("agent", False)  # no native tools: the scripts
    assert session.instructions[0] == baseline_prompt.first_message(10, 1, Corridor().reset())
    assert (tmp_path / "out" / "workspace" / "notes" / "strategy.md").read_text() == "ACTION4 = right"


def coach(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "AGENTS.md").write_text("Coach advice")
    return harness


class LevelPictures(Corridor):
    """The picture names the level, so a test can tell which level reached frame.png."""

    def _frame(self):
        frame = super()._frame()
        frame.rendered_frame = SimpleNamespace(
            data_url="data:image/png;base64," + base64.b64encode(f"level {self.done}".encode()).decode())
        return frame


def test_level_target_ends_the_game_without_showing_the_next_level(tmp_path):
    workspace, output = tmp_path / "ws", tmp_path / "out"
    workspace.mkdir()
    server = GameServer(LevelPictures(levels=3), workspace, output, max_steps=10, stop_after_levels=1).start()
    try:
        game(workspace, "do", "ACTION4")
        code, text = game(workspace, "do", "ACTION4")
        assert code == 0 and text.strip() == "ACTION4: LEVEL COMPLETED (1/3). Level target reached; the game is over."
        code, text = game(workspace, "look")
        assert "level target is reached" in text and "grid" not in text and "frame.png" not in text
        assert game(workspace, "do", "ACTION4")[0] == 1 and server.reason == "level_target_reached"
        assert (workspace / "frame.png").read_bytes() == b"level 0"  # the next level's picture never arrives
        assert len((output / "transitions.jsonl").read_text().splitlines()) == 1
    finally:
        server.stop()
    server.release()  # after the session: the last move is recorded, with its after-frame
    rows = [json.loads(line) for line in (output / "transitions.jsonl").read_text().splitlines()]
    assert [r["after"]["levels_completed"] for r in rows] == [0, 1] and len(server.actions) == 2
    assert (output / "frames" / "002.png").read_bytes() == b"level 1"


def test_play_stops_at_the_level_target_and_still_asks_for_the_reports(tmp_path, monkeypatch):
    session = ScriptedSession([[("do", "ACTION4"), ("do", "ACTION4"), ("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    result = play(LevelPictures(levels=3), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=coach(tmp_path), stop_after_levels=1)
    assert result["reason"] == "level_target_reached" and result["status"] == "completed"
    assert result["levels_completed"] == 1 and result["action_count"] == 2 and result["stop_after_levels"] == 1
    assert "level_target_reached" in session.instructions[1] and result["world_model"]
    assert (tmp_path / "out" / "workspace" / "frame.png").read_bytes() == b"level 0"
    assert len((tmp_path / "out" / "transitions.jsonl").read_text().splitlines()) == 2


def test_a_level_task_starts_at_level_k_stops_at_its_win_and_scores_that_level(tmp_path, monkeypatch):
    env = LevelPictures(levels=3)
    env.done, env.game_id = 1, "ps_modality-v1"  # the env opened at level 2, as ArcadeEnv(start_level=2) does
    session = ScriptedSession([[("do", "ACTION3"), ("do", "ACTION4"), ("do", "ACTION4"), ("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    result = play(env, tmp_path / "out", harness="opencode", model="m", effort="low", provider="", max_steps=10,
                  max_wall_seconds=0, harness_dir=coach(tmp_path), stop_after_levels=1, start_level=2)
    assert "The game starts at level 2 of 3." in session.instructions[0]
    assert result["reason"] == "level_target_reached" and result["levels_completed"] == 2
    assert result["start_level"] == 2 and result["level_solved"] is True and result["level_moves"] == 3
    assert result["level_shortest"] == 33 and result["level_ratio"] == 0.09
    assert result["levels"] == [{"level": 2, "solved": True, "moves": 3, "shortest": 33, "ratio": 0.09}]
    assert (tmp_path / "out" / "workspace" / "frame.png").read_bytes() == b"level 1"  # level 3 never shown


def test_world_model_is_copied_every_n_actions_at_each_level_and_at_the_end(tmp_path, monkeypatch):
    monkeypatch.setattr(player.world_model, "EVERY", 2)

    class ModelKeeper(ScriptedSession):
        def turn(self, instruction, images=(), timeout=None):
            if not instruction.startswith("The game has ended"):
                (self.workspace / "world_model.md").write_text(f"belief {len(self.instructions) + 1}")
            return super().turn(instruction, images, timeout)

    session = ModelKeeper([[("do", "ACTION4"), ("do", "ACTION4")], [("do", "ACTION4"), ("do", "ACTION4")]])
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
         max_steps=10, max_wall_seconds=0, harness_dir=coach(tmp_path))
    copies = tmp_path / "out" / "world_model_snapshots"
    assert sorted(p.name for p in copies.iterdir()) == [
        "a0002.md", "a0004.md", "final.md", "level-1-a0002.md", "level-2-a0004.md"]
    assert (copies / "level-1-a0002.md").read_text() == "belief 1" and (copies / "a0004.md").read_text() == "belief 2"
    assert (copies / "final.md").read_text() == "ACTION4 moves right."  # the end-of-game report
    assert "research-note style" in baseline_prompt.REPORT_PROMPT


class FailingSession(ScriptedSession):
    """Fails the given calls (1-based, counting every turn) with a provider error, doing no work."""

    def __init__(self, plan, failures):
        super().__init__(plan)
        self.failures, self.calls = dict(failures), 0

    def turn(self, instruction, images=(), timeout=None):
        self.calls += 1
        if self.calls in self.failures:
            self.turn_number += 1
            self.instructions.append(instruction)
            return SimpleNamespace(text="", error=self.failures[self.calls], timed_out=False, events=[])
        return super().turn(instruction, images, timeout)


MALFORMED = "Upstream emitted malformed tool call data that could not be repaired."
FULL = "Invalid request parameters. Please check your input and try again."


def test_a_failed_turn_is_followed_by_another_turn_in_the_same_session(tmp_path, monkeypatch):
    session = FailingSession([[("do", "ACTION4")], [("do", "ACTION4")] * 3], {2: MALFORMED})
    created = []
    monkeypatch.setattr(player, "create_session", lambda harness_id: created.append(session) or session)
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=coach(tmp_path))
    assert result["status"] == "completed" and result["levels_completed"] == 2 and len(created) == 1
    assert session.instructions[2].startswith("The last reply failed; continue playing the game: levels 0/2, 9 of 10")
    assert result["failed_turns"] == [{"turn": 2, "action_count": 1, "error": MALFORMED, "new_session": False}]


def test_a_full_context_continues_in_a_fresh_session_in_the_same_folder(tmp_path, monkeypatch):
    first = FailingSession([[("do", "ACTION4")]], {2: FULL})
    second = ScriptedSession([[("do", "ACTION4")] * 3])
    sessions = [first, second]
    monkeypatch.setattr(player, "create_session", lambda harness_id: sessions.pop(0))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "session.json").write_text("{}")  # the first session's manifest is kept aside
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=coach(tmp_path))
    assert result["status"] == "completed" and result["levels_completed"] == 2 and not sessions
    assert second.instructions[0].startswith("This is a new session") and "9 of 10 actions left" in second.instructions[0]
    assert second.turn_number == 2 + 2  # raw/turn-<n> numbering continues: 2 turns before, play and report after
    assert result["failed_turns"][0]["new_session"] is True and (tmp_path / "out" / "session-2.json").is_file()


def test_three_failed_turns_in_a_row_end_the_run_with_an_error(tmp_path, monkeypatch):
    session = FailingSession([], {1: MALFORMED, 2: MALFORMED, 3: MALFORMED})
    monkeypatch.setattr(player, "create_session", lambda harness_id: session)
    result = play(Corridor(), tmp_path / "out", harness="opencode", model="m", effort="low", provider="",
                  max_steps=10, max_wall_seconds=0, harness_dir=coach(tmp_path))
    assert result["status"] == "error" and result["reason"] == "error" and "3 in a row" in result["error"]
    assert len(result["failed_turns"]) == 3 and result["agent_turns"] == 3


def test_baseline_start_and_level_target_options(tmp_path):
    from frameworks.baseline.framework import BASELINE, ROOT

    start = "studies/thursday/start/rules"
    options = BASELINE.check_options({"driver": "agent", "start": start, "stop_after_levels": 3})
    for given in ({"start": start}, {"driver": "agent", "start": "no/such/folder"},
                  {"driver": "agent", "start": "../outside"}):
        with pytest.raises(ValueError):
            BASELINE.check_options(given)
    spec = {"harness": "opencode", "model": "m", "effort": "low", "game_id": "g", "backend_url": "u",
            "max_wall_seconds": 0, "provider": "", "options": options}
    argv = BASELINE.entry(spec, False, Path("/results"), Path("/parent"))
    assert Path(argv[argv.index("--harness-dir") + 1]).as_posix() == "/results/start"
    assert argv[argv.index("--start") + 1] == start and argv[argv.index("--stop-after-levels") + 1] == "3"
    plain = BASELINE.entry({**spec, "options": BASELINE.check_options({"driver": "agent"})}, False,
                           Path("/results"), Path("/parent"))
    assert "--harness-dir" not in plain and "--stop-after-levels" not in plain
    assert BASELINE.variant_label(options) == "Baseline · agent · start=rules · first 3 levels"
    BASELINE.prepare(spec, tmp_path / "run")
    assert (tmp_path / "run" / "start" / "AGENTS.md").read_bytes() == (ROOT / start / "AGENTS.md").read_bytes()


def test_launch_copies_the_start_folder_into_the_run(tmp_path, monkeypatch):
    from harnesses import launch

    monkeypatch.setenv("NANOGPT_API_KEY", "unit-test")
    monkeypatch.setattr(launch, "_run_owned", lambda command, name, env=None: 0)
    code = launch.launch(["--framework", "baseline", "--driver", "agent", "--start", "studies/thursday/start/planner",
                          "--stop-after-levels", "3", "--harness", "opencode",
                          "--model", "nanogpt/qwen/qwen3.8-27b:thinking", "--effort", "medium", "--game-id", "g",
                          "--backend-url", "http://localhost:8000", "--output-dir", str(tmp_path / "run")])
    assert code == 0
    spec = json.loads((tmp_path / "run" / "run_spec.json").read_text())
    assert spec["options"]["start"] == "studies/thursday/start/planner" and spec["options"]["stop_after_levels"] == 3
    assert sorted(p.relative_to(tmp_path / "run" / "start").as_posix()
                  for p in (tmp_path / "run" / "start").rglob("*") if p.is_file()) == ["AGENTS.md", "scripts/search.py"]
