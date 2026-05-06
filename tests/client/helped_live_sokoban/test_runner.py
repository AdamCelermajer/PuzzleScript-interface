import tempfile
import unittest
from pathlib import Path

from client.engine.types import ActionInput, FrameData, GameAction, GameState
from client.helped_live_sokoban.model import HelpedFrame, HelpedGoal
from client.helped_live_sokoban.runner import HelpedLiveRunner, PLANNING_NODE_LIMIT


class LineWorldEnv:
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
        return FrameData(
            frame=[[row]],
            state=GameState.PLAYING,
            levels_completed=0,
            game_id="helped-line-world",
            win_levels=1,
            guid="helped-line-world",
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


class HelpedRunnerTests(unittest.TestCase):
    def test_later_episode_reuses_helped_rules_to_plan_to_goal(self) -> None:
        goal = HelpedGoal.from_cells([(2, 0, "P")])

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "rules.md"
            store = Path(tmpdir) / "rules.json"
            journal = Path(tmpdir) / "journal.md"

            first = HelpedLiveRunner(
                LineWorldEnv(),
                goal=goal,
                output_path=output,
                store_path=store,
                journal_path=journal,
                max_steps=12,
                event_sink=lambda _message: None,
            ).run()
            second = HelpedLiveRunner(
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

    def test_runner_caps_experiment_at_forty_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = HelpedLiveRunner(
                LineWorldEnv(),
                goal=HelpedGoal.from_cells([(9, 9, "P")]),
                output_path=Path(tmpdir) / "rules.md",
                store_path=Path(tmpdir) / "rules.json",
                journal_path=Path(tmpdir) / "journal.md",
                max_steps=200,
                event_sink=lambda _message: None,
            ).run()

        self.assertFalse(result.goal_reached)
        self.assertEqual(result.steps, 40)
        self.assertEqual(len(result.actions), 40)

    def test_goal_planning_stops_at_node_budget(self) -> None:
        class BranchingModel:
            def __init__(self) -> None:
                self.calls = 0

            def predict(
                self, frame: HelpedFrame, action: GameAction
            ) -> list[HelpedFrame]:
                self.calls += 1
                token = f"state_{self.calls}_{action.name}"
                return [HelpedFrame.from_signatures([[token]])]

        frame_data = LineWorldEnv().reset()
        model = BranchingModel()
        runner = HelpedLiveRunner(
            LineWorldEnv(),
            goal=HelpedGoal.from_cells([(9, 9, "P")]),
            model=model,  # type: ignore[arg-type]
            event_sink=lambda _message: None,
        )

        plan = runner._known_plan_to_goal(
            HelpedFrame.from_signatures([["state_start"]]),
            frame_data,
        )

        self.assertIsNone(plan)
        self.assertLessEqual(model.calls, PLANNING_NODE_LIMIT * 4)


if __name__ == "__main__":
    unittest.main()
