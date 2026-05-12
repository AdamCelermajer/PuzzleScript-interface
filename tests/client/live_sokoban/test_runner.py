import tempfile
import unittest
from pathlib import Path

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from client.live_sokoban.model import SymbolFrame, SymbolGoal
from client.live_sokoban.rules import LiveRuleModel
from client.live_sokoban.runner import LiveRunner


class LineWorldEnv:
    def __init__(self) -> None:
        self.index = 0

    def reset(self) -> FrameData:
        self.index = 0
        return self._frame(GameAction.RESET)

    def step(self, action: GameAction) -> FrameData:
        if action == GameAction.ACTION4:
            self.index = min(2, self.index + 1)
        if action == GameAction.ACTION3:
            self.index = max(0, self.index - 1)
        return self._frame(action)

    def _frame(self, action: GameAction) -> FrameData:
        row = [0, 0, 0]
        row[self.index] = 2
        return FrameData(
            frame=[[row]],
            state=GameState.PLAYING,
            levels_completed=0,
            game_id="line-world",
            win_levels=1,
            guid="line-world",
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


class LiveRunnerTests(unittest.TestCase):
    def test_runner_seeds_hidden_target_positions_from_at_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                load_existing=False,
            )

            LiveRunner(
                LineWorldEnv(),
                goal=SymbolGoal(required_cells=((1, 0, "@"), (2, 0, "@"))),
                model=model,
                event_sink=lambda _message: None,
            )

        self.assertEqual(model.target_positions, {(1, 0), (2, 0)})

    def test_later_episode_reuses_symbol_rules_to_plan_to_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            store = Path(tmpdir) / "rules.json"
            journal = Path(tmpdir) / "journal.md"
            goal = SymbolGoal(required_cells=((2, 0, "P"),))

            first = LiveRunner(
                LineWorldEnv(),
                goal=goal,
                output_path=output,
                store_path=store,
                journal_path=journal,
                max_steps=12,
                event_sink=lambda _message: None,
            ).run()
            second = LiveRunner(
                LineWorldEnv(),
                goal=goal,
                output_path=output,
                store_path=store,
                journal_path=journal,
                max_steps=2,
                event_sink=lambda _message: None,
            ).run()

        self.assertTrue(first.goal_reached)
        self.assertTrue(second.goal_reached)
        self.assertEqual(second.actions, [GameAction.ACTION4, GameAction.ACTION4])

    def test_runner_prefers_unseen_symbol_interaction_context(self) -> None:
        class SymbolContextEnv:
            def __init__(self) -> None:
                self.actions: list[GameAction] = []

            def reset(self) -> FrameData:
                return self._frame(GameAction.RESET)

            def step(self, action: GameAction) -> FrameData:
                self.actions.append(action)
                return self._frame(action)

            def _frame(self, action: GameAction) -> FrameData:
                return FrameData(
                    frame=[[[2, 1]]],
                    state=GameState.PLAYING,
                    levels_completed=0,
                    game_id="symbol-context",
                    win_levels=1,
                    guid="symbol-context",
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

        with tempfile.TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.md"
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=journal,
                load_existing=False,
            )
            model.observe(
                SymbolFrame.from_rows(["P."]),
                GameAction.ACTION4,
                SymbolFrame.from_rows([".P"]),
            )
            env = SymbolContextEnv()
            LiveRunner(
                env,
                goal=SymbolGoal(required_cells=((9, 9, "P"),)),
                model=model,
                max_steps=1,
                event_sink=lambda _message: None,
            ).run()
            journal_text = journal.read_text(encoding="utf-8")

        self.assertEqual(env.actions, [GameAction.ACTION4])
        self.assertIn("selected ACTION4: current_unseen_context", journal_text)

    def test_runner_probes_opaque_actions_before_reachable_context_planning(self) -> None:
        class ProbeEnv:
            def __init__(self) -> None:
                self.actions: list[GameAction] = []

            def reset(self) -> FrameData:
                return self._frame(GameAction.RESET)

            def step(self, action: GameAction) -> FrameData:
                self.actions.append(action)
                return self._frame(action)

            def _frame(self, action: GameAction) -> FrameData:
                return FrameData(
                    frame=[[[0, 0, 0], [0, 2, 0], [0, 0, 0]]],
                    state=GameState.PLAYING,
                    levels_completed=0,
                    game_id="probe-actions",
                    win_levels=1,
                    guid="probe-actions",
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

        with tempfile.TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.md"
            model = LiveRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=journal,
                load_existing=False,
            )
            center = SymbolFrame.from_rows(["...", ".P.", "..."])
            model.observe(center, GameAction.ACTION1, SymbolFrame.from_rows([".P.", "...", "..."]))
            model.observe(center, GameAction.ACTION2, SymbolFrame.from_rows(["...", "...", ".P."]))

            env = ProbeEnv()
            LiveRunner(
                env,
                goal=SymbolGoal(required_cells=((9, 9, "P"),)),
                model=model,
                max_steps=1,
                event_sink=lambda _message: None,
            ).run()
            journal_text = journal.read_text(encoding="utf-8")

        self.assertEqual(env.actions, [GameAction.ACTION3])
        self.assertIn("selected ACTION3: unprobed_action", journal_text)

    def test_runner_caps_experiment_at_forty_steps(self) -> None:
        env = LineWorldEnv()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = LiveRunner(
                env,
                goal=SymbolGoal(required_cells=((9, 9, "P"),)),
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                max_steps=200,
                event_sink=lambda _message: None,
            ).run()

        self.assertFalse(result.goal_reached)
        self.assertEqual(result.steps, 40)
        self.assertEqual(len(result.actions), 40)

    def test_reachable_unseen_context_logs_target_context(self) -> None:
        class FakeModel:
            def __init__(self, start: SymbolFrame, target: SymbolFrame) -> None:
                self.start = start
                self.target = target
                self.selections: list[tuple[GameAction, str, tuple | None]] = []

            def action_has_delta(self, _action: GameAction) -> bool:
                return True

            def predict(self, frame: SymbolFrame, action: GameAction) -> list[SymbolFrame]:
                if frame == self.start and action == GameAction.ACTION4:
                    return [self.target]
                return []

            def unseen_context_action(
                self, frame: SymbolFrame, _actions: list[GameAction]
            ) -> tuple[GameAction, tuple] | None:
                if frame == self.target:
                    return GameAction.ACTION1, ("P", "ACTION1", 0, -1, ("P", "#"))
                return None

            def record_explorer_selection(
                self, action: GameAction, reason: str, context: tuple | None = None
            ) -> None:
                self.selections.append((action, reason, context))

        start = SymbolFrame.from_rows(["P."])
        target = SymbolFrame.from_rows([".P"])
        model = FakeModel(start, target)
        frame_data = FrameData(
            frame=[[[2, 0]]],
            state=GameState.PLAYING,
            levels_completed=0,
            game_id="reachable-context",
            win_levels=1,
            guid="reachable-context",
            full_reset=False,
            available_actions=[
                GameAction.ACTION1,
                GameAction.ACTION2,
                GameAction.ACTION3,
                GameAction.ACTION4,
            ],
            action_input=ActionInput(action=GameAction.RESET),
            legend={},
        )
        runner = LiveRunner(
            LineWorldEnv(),
            goal=SymbolGoal(required_cells=((9, 9, "P"),)),
            model=model,  # type: ignore[arg-type]
            event_sink=lambda _message: None,
        )

        selected = runner._choose_action(start, frame_data)

        self.assertEqual(selected, GameAction.ACTION4)
        self.assertEqual(
            model.selections,
            [
                (
                    GameAction.ACTION4,
                    "reachable_unseen_context",
                    ("P", "ACTION1", 0, -1, ("P", "#")),
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
