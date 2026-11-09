from types import SimpleNamespace

from game.types import GameAction, GameState

from frameworks.baseline import prompt as baseline_prompt
from frameworks.baseline.framework import BASELINE, entry
from harnesses.opencode import opencode_config


def frame():
    return SimpleNamespace(frame=[[[1, 2]]], state=GameState.PLAYING, levels_completed=0, win_levels=4,
                           available_actions=[GameAction.ACTION1])


def spec(**options):
    return {"options": {"driver": "controller", "max_steps": 100, **options}, "harness": "opencode", "model": "m",
            "effort": "xhigh", "game_id": "g", "backend_url": "u", "max_wall_seconds": 0, "provider": "chutes"}


def test_a_hidden_budget_shows_only_the_count():
    shown = baseline_prompt.first_message(100, 1, frame())
    hidden = baseline_prompt.first_message(None, 1, frame())
    assert "You have 100 actions." in shown and "actions_used=0/100" in shown
    assert "100" not in hidden and "actions_used=0\n" in hidden
    assert "actions_used=7\n" in baseline_prompt.observation(frame(), 7, None)


def test_the_options_reach_the_player_command():
    from pathlib import Path
    for driver in ("controller", "agent"):
        argv = entry(spec(driver=driver, hide_budget=True, temperature="0"), False, Path("/results"), Path("/parent"))
        assert "--hide-budget" in argv and argv[argv.index("--temperature") + 1] == "0"
        plain = entry(spec(driver=driver), False, Path("/results"), Path("/parent"))
        assert "--hide-budget" not in plain and "--temperature" not in plain
    assert BASELINE.variant({"driver": "agent", "temperature": "0"}).endswith("temperature 0")


def test_temperature_zero_replaces_the_default_and_none_keeps_it(tmp_path):
    config = opencode_config("openrouter", "qwen/qwen3.8-27b", tmp_path / "p.md", temperature=0)
    assert config["agent"]["build"]["temperature"] == 0
    assert opencode_config("openrouter", "qwen/qwen3.8-27b", tmp_path / "p.md")["agent"]["build"]["temperature"] == 1.0


def carried_run(tmp_path, moves):
    """A parent with real-shaped moves on a fake game whose board is the count of moves since the last reset."""
    from frameworks.baseline.continuation import carry_over  # noqa: F401
    import json
    parent = tmp_path / "parent"
    (parent / "frames").mkdir(parents=True)
    (parent / "frames" / "000.png").write_bytes(b"png")
    (parent / "run_config.json").write_text(json.dumps({"max_steps": 800}), encoding="utf-8")
    side = lambda n: {"grid": [[n]], "state": "NOT_FINISHED", "levels_completed": 0, "win_levels": 4}
    count, lines = 0, []
    for index, action in enumerate(moves, 1):
        after = 0 if action == "RESET" else count + 1
        lines.append(json.dumps({"action_index": index, "decision": index + 1, "action": action, "before": side(count), "after": side(after)}))
        count = after
    (parent / "transitions.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return parent


class CountingEnv:
    game_id = "g"

    def __init__(self):
        self.count, self.resets, self.steps = 0, 0, 0

    def _frame(self):
        return SimpleNamespace(frame=[[[self.count]]], state=SimpleNamespace(value="NOT_FINISHED"), levels_completed=0, win_levels=4,
                               available_actions=[GameAction.ACTION1], rendered_frame=None)

    def reset(self):
        self.count, self.resets = 0, self.resets + 1
        return self._frame()

    def step(self, action):
        self.count, self.steps = self.count + 1, self.steps + 1
        return self._frame()


def test_a_replay_presses_reset_as_a_reset(tmp_path):
    from frameworks.baseline.continuation import load_moves, restore_game
    parent = carried_run(tmp_path, ["ACTION1", "ACTION1", "RESET", "ACTION1"])
    env = CountingEnv()
    frame = restore_game(env, env.reset(), load_moves(parent))
    assert frame.frame == [[[1]]] and env.resets == 2 and env.steps == 3


def test_a_game_with_no_moves_left_is_not_carried_on(tmp_path):
    import json
    import pytest
    from frameworks.baseline.continuation import load_moves
    parent = carried_run(tmp_path, ["ACTION1"])
    (parent / "run_config.json").write_text(json.dumps({"max_steps": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="no moves left"):
        load_moves(parent)


def test_the_agent_carries_on_the_same_board_count_and_record(tmp_path):
    from frameworks.baseline.agentic import GameServer
    parent = carried_run(tmp_path, ["ACTION1", "RESET", "ACTION1", "ACTION1"])
    output, folder = tmp_path / "child", tmp_path / "folder"
    output.mkdir()
    folder.mkdir()
    server = GameServer(CountingEnv(), folder, output, 800, parent=parent)
    assert len(server.actions) == 4 and server.frame.frame == [[[2]]]
    assert (output / "transitions.jsonl").read_text(encoding="utf-8") == (parent / "transitions.jsonl").read_text(encoding="utf-8")
    assert (output / "frames" / "000.png").is_file()
    assert "actions_used=4/800" in server._status()
    assert server.handle("do", "ACTION1")[0] and server.actions[-1] == "ACTION1" and len(server.actions) == 5
    server.home.exists() and __import__("shutil").rmtree(server.home, ignore_errors=True)


def test_carrying_moves_reaches_both_players_commands():
    from pathlib import Path
    results, source = Path("/results"), Path("/parent")
    agent = entry({**spec(driver="agent", carry_moves=True), "continued_from": "/runs/p"}, False, results, source)
    assert agent[agent.index("--continue-from") + 1] == str(source)
    controller = entry({**spec(carry_moves=True), "continued_from": "/runs/p"}, False, results, source)
    assert "--carry-moves" in controller and controller[controller.index("--continue-from") + 1] == str(source)
    assert "resumed" in BASELINE.variant_label({"driver": "agent", "carry_moves": True})
