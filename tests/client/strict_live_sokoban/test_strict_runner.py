import sys
import tempfile
import unittest
from pathlib import Path

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from client.strict_live_sokoban.model import RawFrame, RawGoal
from client.strict_live_sokoban.rules import StrictRuleModel
from client.strict_live_sokoban.runner import StrictLiveRunner


class LineWorldEnv:
    session_id = "line-world"

    def __init__(self) -> None:
        self.index = 0
        self.actions: list[GameAction] = []

    def reset(self) -> FrameData:
        self.index = 0
        return self._frame(GameAction.RESET)

    def step(self, action: GameAction) -> FrameData:
        self.actions.append(action)
        if action == GameAction.ACTION4:
            self.index = min(2, self.index + 1)
        if action == GameAction.ACTION3:
            self.index = max(0, self.index - 1)
        return self._frame(action)

    def _frame(self, action: GameAction) -> FrameData:
        row = [0, 0, 0]
        row[self.index] = 2
        solved = self.index == 2
        return FrameData(
            frame=[row and [row]],
            state=GameState.WIN if solved else GameState.PLAYING,
            levels_completed=1 if solved else 0,
            game_id="line-world",
            win_levels=1,
            guid="line-world-guid",
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


class StrictRunnerTests(unittest.TestCase):
    def test_runner_uses_parameterless_actions_and_goal_facts_without_llm(self) -> None:
        sys.modules.pop("client.engine.llm_client", None)
        env = LineWorldEnv()
        goal = RawGoal(required_cells=((2, 0, 2),))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strict_report.md"
            result = StrictLiveRunner(
                env,
                goal=goal,
                output_path=output_path,
                max_steps=12,
                event_sink=lambda _message: None,
            ).run()
            text = output_path.read_text(encoding="utf-8")

        self.assertTrue(result.goal_reached)
        self.assertIn(GameAction.ACTION4, result.actions)
        self.assertIn("Goal facts", text)
        self.assertIn("parameterless actions", text)
        self.assertIn("No action parameters were provided", text)
        self.assertNotIn("client.engine.llm_client", sys.modules)
        self.assertNotIn("Player", text)
        self.assertNotIn("Crate", text)

    def test_runner_reports_limitation_when_goal_is_not_reached(self) -> None:
        env = LineWorldEnv()
        impossible_goal = RawGoal(required_cells=((9, 9, 9),))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strict_report.md"
            result = StrictLiveRunner(
                env,
                goal=impossible_goal,
                output_path=output_path,
                max_steps=6,
                event_sink=lambda _message: None,
            ).run()
            text = output_path.read_text(encoding="utf-8")

        self.assertFalse(result.goal_reached)
        self.assertIn("Goal was not reached", text)
        self.assertIn("Limitations Observed", text)

    def test_later_experiment_reuses_persisted_rules(self) -> None:
        goal = RawGoal(required_cells=((2, 0, 2),))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strict_report.md"
            store_path = Path(tmpdir) / "strict_store.json"

            first_result = StrictLiveRunner(
                LineWorldEnv(),
                goal=goal,
                output_path=output_path,
                store_path=store_path,
                max_steps=12,
                event_sink=lambda _message: None,
            ).run()
            second_result = StrictLiveRunner(
                LineWorldEnv(),
                goal=goal,
                output_path=output_path,
                store_path=store_path,
                max_steps=2,
                event_sink=lambda _message: None,
            ).run()

        self.assertTrue(first_result.goal_reached)
        self.assertTrue(second_result.goal_reached)
        self.assertEqual(second_result.actions, [GameAction.ACTION4, GameAction.ACTION4])

    def test_runner_prefers_unseen_raw_interaction_context(self) -> None:
        class RawContextEnv:
            def __init__(self) -> None:
                self.actions: list[GameAction] = []

            def reset(self) -> FrameData:
                return self._frame(GameAction.RESET)

            def step(self, action: GameAction) -> FrameData:
                self.actions.append(action)
                return self._frame(action)

            def _frame(self, action: GameAction) -> FrameData:
                return FrameData(
                    frame=[[[2, 9]]],
                    state=GameState.PLAYING,
                    levels_completed=0,
                    game_id="raw-context",
                    win_levels=1,
                    guid="raw-context",
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
            model = StrictRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=journal,
                load_existing=False,
            )
            model.observe(
                RawFrame.from_grid([[2, 0]]),
                GameAction.ACTION4,
                RawFrame.from_grid([[0, 2]]),
            )
            env = RawContextEnv()
            StrictLiveRunner(
                env,
                goal=RawGoal(required_cells=((9, 9, 9),)),
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
            model = StrictRuleModel(
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=journal,
                load_existing=False,
            )
            center = RawFrame.from_grid([[0, 0, 0], [0, 2, 0], [0, 0, 0]])
            model.observe(center, GameAction.ACTION1, RawFrame.from_grid([[0, 2, 0], [0, 0, 0], [0, 0, 0]]))
            model.observe(center, GameAction.ACTION2, RawFrame.from_grid([[0, 0, 0], [0, 0, 0], [0, 2, 0]]))

            env = ProbeEnv()
            StrictLiveRunner(
                env,
                goal=RawGoal(required_cells=((9, 9, 9),)),
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
            result = StrictLiveRunner(
                env,
                goal=RawGoal(required_cells=((9, 9, 9),)),
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
            def __init__(self, start: RawFrame, target: RawFrame) -> None:
                self.start = start
                self.target = target
                self.selections: list[tuple[GameAction, str, tuple | None]] = []

            def action_has_delta(self, _action: GameAction) -> bool:
                return True

            def known_transition(
                self, frame: RawFrame, action: GameAction
            ) -> RawFrame | None:
                if frame == self.start and action == GameAction.ACTION4:
                    return self.target
                return None

            def unseen_context_action(
                self, frame: RawFrame, _actions: list[GameAction]
            ) -> tuple[GameAction, tuple] | None:
                if frame == self.target:
                    return GameAction.ACTION1, (2, "ACTION1", 0, -1, (2, 1))
                return None

            def record_explorer_selection(
                self, action: GameAction, reason: str, context: tuple | None = None
            ) -> None:
                self.selections.append((action, reason, context))

        start = RawFrame.from_grid([[2, 0]])
        target = RawFrame.from_grid([[0, 2]])
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
        runner = StrictLiveRunner(
            LineWorldEnv(),
            goal=RawGoal(required_cells=((9, 9, 9),)),
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
                    (2, "ACTION1", 0, -1, (2, 1)),
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
