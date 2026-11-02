import json
import tempfile
import unittest
from dataclasses import dataclass, field

from client.arc.types import ActionInput, FrameData, GameAction, GameState
from frameworks.avo.legacy.runner import AvoAgentRunner


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    levels_completed: int = 0,
    win_levels: int = 1,
    action: GameAction = GameAction.RESET,
) -> FrameData:
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=levels_completed,
        game_id="ps_secret_solution_name-v1",
        win_levels=win_levels,
        guid="secret-guid",
        full_reset=action == GameAction.RESET,
        available_actions=[
            GameAction.ACTION1,
            GameAction.ACTION2,
            GameAction.ACTION3,
            GameAction.ACTION4,
            GameAction.ACTION5,
            GameAction.ACTION7,
        ],
        action_input=ActionInput(action=action),
    )


@dataclass
class FakeEnv:
    reset_frame: FrameData
    step_frames: list[FrameData]
    step_actions: list[GameAction] = field(default_factory=list)
    reset_calls: int = 0

    def reset(self) -> FrameData:
        self.reset_calls += 1
        if self.reset_calls == 1:
            return self.reset_frame
        self.step_actions.append(GameAction.RESET)
        return self.step_frames[len(self.step_actions) - 1]

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        return self.step_frames[len(self.step_actions) - 1]


class FakeSession:
    def __init__(self, plans: list[dict], reviews: list[dict] | None = None) -> None:
        self.plans = list(plans)
        self.reviews = list(reviews or [])
        self.plan_calls: list[dict] = []
        self.supervisor_calls: list[str] = []

    def next_plan(self, prompt: str, image_path=None) -> dict:
        self.plan_calls.append({"prompt": prompt, "image_path": image_path})
        return self.plans.pop(0)

    def supervise(self, prompt: str) -> dict[str, str]:
        self.supervisor_calls.append(prompt)
        return self.reviews.pop(0)


def _plan(*actions: str, prediction: str = "move") -> dict:
    return {
        "actions": list(actions),
        "prediction": prediction,
        "note": "test plan",
        "confidence": "high",
    }


class AvoAgentTests(unittest.TestCase):
    def test_executes_batch_and_keeps_game_identity_out_of_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0, 0]]),
                step_frames=[
                    _frame([[0, 2, 0]], action=GameAction.ACTION4),
                    _frame(
                        [[0, 0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    ),
                ],
            )
            session = FakeSession([_plan("ACTION4", "ACTION4")])

            result = AvoAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION4])
            state = json.loads(
                result.output_dir.joinpath("workspace", "current_state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["game"], "unknown-game")
            self.assertNotIn("game_id", state)
            self.assertNotIn("ps_secret_solution_name", session.plan_calls[0]["prompt"])
            self.assertTrue(result.trajectory_path.exists())
            self.assertTrue(
                result.output_dir.joinpath("workspace", "KNOWLEDGE.md").exists()
            )
            self.assertTrue(
                result.output_dir.joinpath("workspace", "helpers", "solver.py").exists()
            )

    def test_level_completion_cancels_remaining_batch_and_replans(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0]], win_levels=2),
                step_frames=[
                    _frame(
                        [[2, 0]],
                        levels_completed=1,
                        win_levels=2,
                        action=GameAction.ACTION4,
                    ),
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=2,
                        win_levels=2,
                        action=GameAction.ACTION4,
                    ),
                ],
            )
            session = FakeSession(
                [
                    _plan("ACTION4", "ACTION1", prediction="finish level one"),
                    _plan("ACTION4", prediction="finish level two"),
                ]
            )

            result = AvoAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(env.step_actions, [GameAction.ACTION4, GameAction.ACTION4])
            self.assertEqual(result.decisions, 2)
            self.assertIn("finish level one", session.plan_calls[1]["prompt"])

    def test_repeated_noops_trigger_independent_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0]]),
                step_frames=[
                    _frame([[2, 0]], action=GameAction.ACTION1),
                    _frame([[2, 0]], action=GameAction.ACTION1),
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    ),
                ],
            )
            session = FakeSession(
                [
                    _plan("ACTION1", "ACTION1", prediction="test upward movement"),
                    _plan("ACTION4", prediction="follow supervisor redirect"),
                ],
                reviews=[
                    {
                        "diagnosis": "The same blocked action was repeated.",
                        "advice": "Test a different legal direction.",
                    }
                ],
            )

            result = AvoAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
                supervise_after_stalls=2,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(result.supervisor_calls, 1)
            self.assertEqual(len(session.supervisor_calls), 1)
            self.assertIn("Test a different legal direction", session.plan_calls[1]["prompt"])
            supervisor_prompt = session.supervisor_calls[0]
            self.assertNotIn("ps_secret_solution_name", supervisor_prompt)

    def test_reset_uses_environment_reset_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0]]),
                step_frames=[
                    _frame([[2, 0]], action=GameAction.RESET),
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    ),
                ],
            )
            session = FakeSession(
                [
                    _plan("RESET", prediction="restart the level"),
                    _plan("ACTION4", prediction="finish after restart"),
                ]
            )

            result = AvoAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(env.reset_calls, 2)
            self.assertEqual(env.step_actions, [GameAction.RESET, GameAction.ACTION4])


if __name__ == "__main__":
    unittest.main()
