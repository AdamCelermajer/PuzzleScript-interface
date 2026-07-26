import base64
import json
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from client.arc.types import ActionInput, FrameData, GameAction, GameState, RenderedFrame
from studies.codex_agent.runner import CodexAgentRunner


def _frame(
    grid: list[list[int]],
    *,
    state: GameState = GameState.PLAYING,
    levels_completed: int = 0,
    action: GameAction = GameAction.RESET,
    image: bool = False,
) -> FrameData:
    rendered = None
    if image:
        rendered = RenderedFrame(
            mime_type="image/png",
            data_url="data:image/png;base64," + base64.b64encode(b"png").decode(),
        )
    return FrameData(
        frame=[grid],
        state=state,
        levels_completed=levels_completed,
        game_id="codex-test-world",
        win_levels=1,
        guid="codex-test-world",
        full_reset=(action == GameAction.RESET),
        available_actions=[
            GameAction.ACTION1,
            GameAction.ACTION2,
            GameAction.ACTION3,
            GameAction.ACTION4,
        ],
        action_input=ActionInput(action=action),
        rendered_frame=rendered,
    )


@dataclass
class FakeEnv:
    reset_frame: FrameData
    step_frames: list[FrameData]
    step_actions: list[GameAction] = field(default_factory=list)

    def reset(self) -> FrameData:
        return self.reset_frame

    def step(self, action: GameAction) -> FrameData:
        self.step_actions.append(action)
        return self.step_frames[len(self.step_actions) - 1]


class FakeSession:
    def __init__(self, responses: list[dict[str, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def next_action(self, prompt: str, image_path=None) -> dict[str, str]:
        self.calls.append({"prompt": prompt, "image_path": image_path})
        return self.responses.pop(0)


class CodexAgentTests(unittest.TestCase):
    def test_one_persistent_session_receives_each_frame_and_solves(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0, 0]], image=True),
                step_frames=[
                    _frame([[0, 2, 0]], action=GameAction.ACTION4, image=True),
                    _frame(
                        [[0, 0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                        image=True,
                    ),
                ],
            )
            session = FakeSession(
                [
                    {"action": "ACTION4", "note": "move right"},
                    {"action": "ACTION4", "note": "continue right"},
                ]
            )

            result = CodexAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=5,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(
                result.actions,
                [GameAction.ACTION4, GameAction.ACTION4],
            )
            self.assertEqual(len(session.calls), 2)
            self.assertIn("Solve this unknown puzzle game", session.calls[0]["prompt"])
            self.assertNotIn("Solve this unknown puzzle game", session.calls[1]["prompt"])
            self.assertIn("Previous action ACTION4", session.calls[1]["prompt"])
            self.assertTrue(Path(session.calls[0]["image_path"]).exists())
            self.assertTrue(Path(session.calls[1]["image_path"]).exists())

            transcript = [
                json.loads(line)
                for line in result.transcript_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(transcript), 2)
            self.assertEqual(transcript[0]["response"]["action"], "ACTION4")
            self.assertTrue(transcript[0]["result"]["changed"])

    def test_finish_is_rejected_until_environment_reports_win(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = FakeEnv(
                reset_frame=_frame([[2, 0]]),
                step_frames=[
                    _frame(
                        [[0, 2]],
                        state=GameState.WIN,
                        levels_completed=1,
                        action=GameAction.ACTION4,
                    )
                ],
            )
            session = FakeSession(
                [
                    {"action": "FINISH", "note": "done"},
                    {"action": "ACTION4", "note": "move"},
                ]
            )

            result = CodexAgentRunner(
                env=env,
                session=session,
                output_dir=tmpdir,
                max_steps=2,
                max_decisions=2,
            ).run()

            self.assertTrue(result.solved)
            self.assertEqual(env.step_actions, [GameAction.ACTION4])
            self.assertIn("FINISH was rejected", session.calls[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
