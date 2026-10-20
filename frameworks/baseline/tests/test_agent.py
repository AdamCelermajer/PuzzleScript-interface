import base64
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from client.arc.types import GameAction, GameState

from frameworks.baseline import agent as player
from frameworks.baseline.agent import GameServer, play

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
        assert code == 0 and "levels=0/2 actions_used=0/3" in text and "5 2 2" in text and "frame.png" in text
        assert (workspace / "frame.png").read_bytes() == b"\x89PNG fake"
        code, text = game(workspace, "do", "action4")
        assert code == 0 and "ACTION4: changed (0,0) 5->2, (0,1) 2->5" in text
        code, text = game(workspace, "do", "ACTION4")
        assert "LEVEL COMPLETED (1/2)" in text
        assert game(workspace, "do", "ACTION9")[0] == 1
        code, text = game(workspace, "reset")
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
        self.plan, self.instructions = list(plan), []

    def start(self, workspace, system_prompt, model, effort, role, analysis_dir, provider=""):
        self.workspace, self.system_prompt = Path(workspace), system_prompt
        assert (self.workspace / "AGENTS.md").read_text() == "Coach advice"
        return self

    def turn(self, instruction, images=(), timeout=None):
        self.instructions.append(instruction)
        if instruction.startswith("The game session has ended"):
            self.refused = game(self.workspace, "do", "ACTION4")  # the game is closed for the final reports
            (self.workspace / "world_model.md").write_text("ACTION4 moves right.")
        elif instruction.startswith("Last task"):
            (self.workspace / "solver.py").write_text("def next_action(grid, levels_completed):\n    return 'ACTION4'\n")
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
    assert result["solver"] and "def next_action" in (tmp_path / "out" / "solver.py").read_text()


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


def test_notes_option_adds_the_notes_instruction_and_mirrors_notes_live(tmp_path, monkeypatch):
    class NoteTaker(ScriptedSession):
        def turn(self, instruction, images=(), timeout=None):
            if not instruction.startswith(("The game session has ended", "Last task")):
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
    assert "notes/strategy.md" in session.system_prompt and "notes/strategy.md" not in player.SYSTEM_PROMPT
    assert (tmp_path / "out" / "workspace" / "notes" / "strategy.md").read_text() == "ACTION4 = right"
