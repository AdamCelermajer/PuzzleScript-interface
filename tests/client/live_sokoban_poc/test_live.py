import sys
import tempfile
import unittest
from pathlib import Path

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from client.live_sokoban_poc.live import LiveSokobanController
from client.live_sokoban_poc.model import BoardState


GRID = [
    [1, 1, 1, 1, 0, 0],
    [1, 0, 5, 1, 0, 0],
    [1, 0, 0, 1, 1, 1],
    [1, 4, 2, 0, 0, 1],
    [1, 0, 0, 3, 0, 1],
    [1, 0, 0, 1, 1, 1],
    [1, 1, 1, 1, 0, 0],
]


class FakeSokobanEnv:
    session_id = "fake-live-session"

    def __init__(self) -> None:
        self.initial = BoardState.from_grid(GRID)
        self.board = self.initial
        self.reset_calls = 0
        self.actions: list[GameAction] = []

    def reset(self) -> FrameData:
        self.reset_calls += 1
        self.board = self.initial
        return self._frame(GameAction.RESET)

    def step(self, action: GameAction) -> FrameData:
        self.actions.append(action)
        self.board = self.board.apply_sokoban_action(action)
        return self._frame(action)

    def _frame(self, action: GameAction) -> FrameData:
        return FrameData(
            frame=[self.board.to_grid()],
            state=GameState.WIN if self.board.is_goal() else GameState.PLAYING,
            levels_completed=1 if self.board.is_goal() else 0,
            game_id="ps_sokoban_basic-v1",
            win_levels=2,
            guid="fake-guid",
            full_reset=(action == GameAction.RESET),
            available_actions=[
                GameAction.ACTION1,
                GameAction.ACTION2,
                GameAction.ACTION3,
                GameAction.ACTION4,
            ],
            action_input=ActionInput(action=action),
            legend={},
        )


class LiveSokobanControllerTests(unittest.TestCase):
    def test_poc_loop_reaches_goal_and_writes_evolving_rule_file_without_llm(self) -> None:
        sys.modules.pop("client.engine.llm_client", None)
        env = FakeSokobanEnv()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "live_rules.md"
            result = LiveSokobanController(env, output_path=output_path).run(max_steps=80)
            text = output_path.read_text(encoding="utf-8")

        self.assertTrue(result.solved)
        self.assertGreaterEqual(env.reset_calls, 2)
        self.assertIn(GameAction.ACTION4, env.actions)
        self.assertIn("Prediction Failures", text)
        self.assertIn("R001", text)
        self.assertIn("Final Rule Set", text)
        self.assertNotIn("ANY_DIRECTION", text)
        self.assertNotIn("client.engine.llm_client", sys.modules)

    def test_controller_sleeps_after_each_executed_move_when_delay_is_set(self) -> None:
        env = FakeSokobanEnv()
        delays: list[float] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "live_rules.md"
            result = LiveSokobanController(
                env,
                output_path=output_path,
                step_delay=0.4,
                sleeper=delays.append,
                event_sink=lambda _message: None,
            ).run(max_steps=80)

        self.assertTrue(result.solved)
        self.assertEqual(delays, [0.4] * result.steps)

    def test_controller_announces_plain_english_explanation_for_new_rules(self) -> None:
        env = FakeSokobanEnv()
        events: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "live_rules.md"
            LiveSokobanController(
                env,
                output_path=output_path,
                event_sink=events.append,
            ).run(max_steps=8)

        self.assertTrue(
            any(
                event.startswith("Rule ")
                and "means:" in event
                and "the player moves one cell" in event
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
